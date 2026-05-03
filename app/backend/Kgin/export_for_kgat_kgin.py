#!/usr/bin/env python3
from __future__ import annotations

"""
Export KGAT/KGIN dataset files using:
- interactions from split CSV files (train/eval)
- knowledge graph triples from Neo4j

Output files:
- train.txt
- test.txt
- user_list.txt
- item_list.txt
- entity_list.txt
- relation_list.txt
- kg_final.txt
- item_id_map.json
- stats.json

Design choice:
- train/test interactions come DIRECTLY from CSV splits
- KG triples come DIRECTLY from Neo4j
- only static relations are exported by default:
    HAS_GENRE, DIRECTED_BY, STARRED_BY
- SIMILAR_TO is excluded by default to avoid label leakage from full interactions
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Set

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.neo4j_manager import Neo4jManager

STATIC_RELATIONS = ["HAS_GENRE", "DIRECTED_BY", "STARRED_BY"]
OPTIONAL_RELATIONS = ["SIMILAR_TO"]


def load_interactions(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = {"user_id", "movie_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} missing required columns: {sorted(missing)}")

    df = df.copy()
    df["user_id"] = pd.to_numeric(df["user_id"], errors="raise").astype(int)
    df["movie_id"] = pd.to_numeric(df["movie_id"], errors="raise").astype(int)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
        df = df.sort_values(["user_id", "timestamp"], ascending=[True, True])
    else:
        df = df.sort_values(["user_id", "movie_id"], ascending=[True, True])
    return df


def write_interaction_txt(df: pd.DataFrame, output_path: Path) -> Dict[int, List[int]]:
    grouped: Dict[int, List[int]] = {}
    for uid, grp in df.groupby("user_id"):
        items = grp["movie_id"].astype(int).tolist()
        items = list(dict.fromkeys(items))
        if items:
            grouped[int(uid)] = items

    with output_path.open("w", encoding="utf-8") as f:
        for uid in sorted(grouped.keys()):
            row = [str(uid)] + [str(mid) for mid in grouped[uid]]
            f.write(" ".join(row) + "\n")

    return grouped


def fetch_neo4j_kg(
    manager: Neo4jManager,
    item_ids: Set[int],
    include_similar_to: bool = False,
) -> Tuple[List[Tuple[int, str]], List[Tuple[str, str, str]], Dict[str, int]]:
    """
    Returns:
    - items: list of (movie_id, movie_entity_key)
    - triples: list of (head_entity_key, relation_name, tail_entity_key)
    - relation_counts
    """
    if not manager.driver:
        raise RuntimeError("Neo4jManager is not connected")

    rels = list(STATIC_RELATIONS)
    if include_similar_to:
        rels += OPTIONAL_RELATIONS

    item_ids_list = sorted(int(x) for x in item_ids)
    relation_counts: Dict[str, int] = {r: 0 for r in rels}

    item_query = """
    MATCH (m:Movie)
    WHERE m.movie_id IN $movie_ids
    RETURN DISTINCT m.movie_id AS movie_id
    ORDER BY movie_id
    """

    triple_queries = {
        "HAS_GENRE": """
            MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre)
            WHERE m.movie_id IN $movie_ids
            RETURN DISTINCT m.movie_id AS movie_id, g.name AS tail_name
        """,
        "DIRECTED_BY": """
            MATCH (m:Movie)-[:DIRECTED_BY]->(p:Person)
            WHERE m.movie_id IN $movie_ids
            RETURN DISTINCT m.movie_id AS movie_id, p.name AS tail_name
        """,
        "STARRED_BY": """
            MATCH (m:Movie)-[:STARRED_BY]->(p:Person)
            WHERE m.movie_id IN $movie_ids
            RETURN DISTINCT m.movie_id AS movie_id, p.name AS tail_name
        """,
        "SIMILAR_TO": """
            MATCH (m1:Movie)-[:SIMILAR_TO]->(m2:Movie)
            WHERE m1.movie_id IN $movie_ids AND m2.movie_id IN $movie_ids
            RETURN DISTINCT m1.movie_id AS movie_id, m2.movie_id AS tail_movie_id
        """,
    }

    items: List[Tuple[int, str]] = []
    triples: List[Tuple[str, str, str]] = []

    with manager.driver.session() as session:
        item_rows = session.run(item_query, movie_ids=item_ids_list)
        seen_items = set()
        for row in item_rows:
            mid = int(row["movie_id"])
            ent_key = f"movie::{mid}"
            items.append((mid, ent_key))
            seen_items.add(mid)

        # if some item ids are not present in Neo4j, still keep them as items with no KG edges
        for mid in item_ids_list:
            if mid not in seen_items:
                items.append((mid, f"movie::{mid}"))

        for rel in rels:
            q = triple_queries[rel]
            rows = session.run(q, movie_ids=item_ids_list)
            if rel == "SIMILAR_TO":
                for row in rows:
                    h = f"movie::{int(row['movie_id'])}"
                    t = f"movie::{int(row['tail_movie_id'])}"
                    triples.append((h, rel, t))
                    relation_counts[rel] += 1
            else:
                for row in rows:
                    movie_id = int(row["movie_id"])
                    tail_name = str(row["tail_name"] or "").strip()
                    if not tail_name:
                        continue
                    if rel == "HAS_GENRE":
                        tail = f"genre::{tail_name}"
                    elif rel == "DIRECTED_BY":
                        tail = f"person::{tail_name}::director"
                    elif rel == "STARRED_BY":
                        tail = f"person::{tail_name}::actor"
                    else:
                        continue
                    head = f"movie::{movie_id}"
                    triples.append((head, rel, tail))
                    relation_counts[rel] += 1

    return items, triples, relation_counts


def build_mappings(
    user_ids: List[int],
    items: List[Tuple[int, str]],
    triples: List[Tuple[str, str, str]],
) -> Tuple[
    Dict[int, int],
    Dict[int, int],
    Dict[str, int],
    Dict[str, int],
]:
    user_remap = {uid: idx for idx, uid in enumerate(sorted(set(user_ids)))}

    sorted_items = sorted(items, key=lambda x: x[0])
    item_remap = {movie_id: idx for idx, (movie_id, _) in enumerate(sorted_items)}

    entity_keys: List[str] = []
    for _, ent in sorted_items:
        entity_keys.append(ent)
    for h, _, t in triples:
        entity_keys.append(h)
        entity_keys.append(t)
    entity_keys = sorted(set(entity_keys))

    # make item entities occupy the first block and align with item remap ids
    entity_remap: Dict[str, int] = {}
    next_idx = 0
    for movie_id, ent in sorted_items:
        entity_remap[ent] = next_idx
        next_idx += 1
    for ent in entity_keys:
        if ent not in entity_remap:
            entity_remap[ent] = next_idx
            next_idx += 1

    relation_names = sorted(set(r for _, r, _ in triples))
    relation_remap = {rel: idx for idx, rel in enumerate(relation_names)}

    return user_remap, item_remap, entity_remap, relation_remap


def write_mapping_files(
    out_dir: Path,
    user_remap: Dict[int, int],
    item_remap: Dict[int, int],
    entity_remap: Dict[str, int],
    relation_remap: Dict[str, int],
) -> None:
    with (out_dir / "user_list.txt").open("w", encoding="utf-8") as f:
        f.write("org_id remap_id\n")
        for uid in sorted(user_remap.keys()):
            f.write(f"{uid} {user_remap[uid]}\n")

    with (out_dir / "item_list.txt").open("w", encoding="utf-8") as f:
        f.write("org_id remap_id freebase_id\n")
        for mid in sorted(item_remap.keys()):
            f.write(f"{mid} {item_remap[mid]} movie::{mid}\n")

    with (out_dir / "entity_list.txt").open("w", encoding="utf-8") as f:
        f.write("freebase_id remap_id\n")
        for ent, rid in sorted(entity_remap.items(), key=lambda x: x[1]):
            f.write(f"{ent} {rid}\n")

    with (out_dir / "relation_list.txt").open("w", encoding="utf-8") as f:
        f.write("freebase_id remap_id\n")
        for rel, rid in sorted(relation_remap.items(), key=lambda x: x[1]):
            f.write(f"{rel} {rid}\n")

    with (out_dir / "item_id_map.json").open("w", encoding="utf-8") as f:
        json.dump(item_remap, f, ensure_ascii=False, indent=2)


def write_kg_final(
    out_dir: Path,
    triples: List[Tuple[str, str, str]],
    entity_remap: Dict[str, int],
    relation_remap: Dict[str, int],
) -> None:
    with (out_dir / "kg_final.txt").open("w", encoding="utf-8") as f:
        for h, r, t in triples:
            f.write(f"{entity_remap[h]} {relation_remap[r]} {entity_remap[t]}\n")


def write_stats(
    out_dir: Path,
    train_grouped: Dict[int, List[int]],
    eval_grouped: Dict[int, List[int]],
    item_remap: Dict[int, int],
    entity_remap: Dict[str, int],
    relation_remap: Dict[str, int],
    triples: List[Tuple[str, str, str]],
    relation_counts: Dict[str, int],
    include_similar_to: bool,
    eval_name: str,
) -> None:
    stats = {
        "num_train_users": len(train_grouped),
        f"num_{eval_name}_users": len(eval_grouped),
        "num_items": len(item_remap),
        "num_entities": len(entity_remap),
        "num_relations": len(relation_remap),
        "num_kg_triples": len(triples),
        "relation_counts": relation_counts,
        "include_similar_to": include_similar_to,
    }
    with (out_dir / "stats.json").open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export KGAT/KGIN dataset using CSV interactions + Neo4j KG")
    parser.add_argument("--train", required=True, help="Path to train.csv")
    parser.add_argument("--eval", required=True, help="Path to valid.csv or test.csv")
    parser.add_argument("--eval-name", default="valid", choices=["valid", "test"], help="Name for eval split")
    parser.add_argument("--out-dir", required=True, help="Output dataset directory")
    parser.add_argument("--include-similar-to", action="store_true", help="Include SIMILAR_TO edges from Neo4j")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_df = load_interactions(args.train)
    eval_df = load_interactions(args.eval)

    train_grouped = write_interaction_txt(train_df, out_dir / "train.txt")
    eval_grouped = write_interaction_txt(eval_df, out_dir / "test.txt")

    user_ids = sorted(set(train_df["user_id"].tolist()) | set(eval_df["user_id"].tolist()))
    item_ids = set(train_df["movie_id"].tolist()) | set(eval_df["movie_id"].tolist())

    manager = Neo4jManager()
    if not manager.connect():
        raise RuntimeError("Failed to connect to Neo4j. Check NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD")

    try:
        items, triples, relation_counts = fetch_neo4j_kg(
            manager=manager,
            item_ids=item_ids,
            include_similar_to=args.include_similar_to,
        )
    finally:
        manager.close()

    user_remap, item_remap, entity_remap, relation_remap = build_mappings(
        user_ids=user_ids,
        items=items,
        triples=triples,
    )

    write_mapping_files(out_dir, user_remap, item_remap, entity_remap, relation_remap)
    write_kg_final(out_dir, triples, entity_remap, relation_remap)
    write_stats(
        out_dir,
        train_grouped,
        eval_grouped,
        item_remap,
        entity_remap,
        relation_remap,
        triples,
        relation_counts,
        include_similar_to=args.include_similar_to,
        eval_name=args.eval_name,
    )

    print(f"[OK] Dataset exported to: {out_dir}")
    print(f"[OK] train users: {len(train_grouped)}")
    print(f"[OK] {args.eval_name} users: {len(eval_grouped)}")
    print(f"[OK] items: {len(item_remap)}")
    print(f"[OK] entities: {len(entity_remap)}")
    print(f"[OK] relations: {len(relation_remap)}")
    print(f"[OK] triples: {len(triples)}")
    print(f"[OK] SIMILAR_TO included: {args.include_similar_to}")


if __name__ == "__main__":
    main()
