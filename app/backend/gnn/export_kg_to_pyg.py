"""
Export Neo4j movie knowledge graph to a PyTorch Geometric HeteroData object.

This script is the bridge between:
- your existing Neo4j database (already synced from SQLite via Neo4jManager),
- the GNN training pipeline (train_gnn.py using HeteroData).

High-level flow:
1. Connect to Neo4j via Neo4jManager (reusing existing config).
2. Query all relevant nodes and relationships:
   - Nodes: Movie, Genre, Person (as Director / Actor)
   - Rels: HAS_GENRE, DIRECTED_BY, STARRED_BY, (optionally) SIMILAR_TO
3. Build typed node index spaces and simple numeric features.
4. Create a torch_geometric.data.HeteroData object and save it as data_kg.pt.
5. Save a movie_id -> node_index map for later embedding export.

NOTE:
- This is a skeleton implementation. You should refine:
  - which properties to turn into features (year, rating, popularity, etc.),
  - whether to split Person into Director / Actor node types,
  - whether to include SIMILAR_TO edges or others.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional, Set

import numpy as np
import pandas as pd
import torch

try:
    from torch_geometric.data import HeteroData
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "torch_geometric is required to run this export script. "
        "Install it in your backend environment."
    ) from exc

# 保證可以像在 backend 目錄下執行腳本一樣匯入現有模組（database, services 等）
BACKEND_ROOT = Path(__file__).resolve().parents[1]  # app/backend
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.neo4j_manager import Neo4jManager


def load_train_movie_ids(train_csv_path: str = None) -> Optional[Set[int]]:
    """Load movie IDs from train.csv to filter the KG export."""
    if train_csv_path is None:
        # Try multiple possible paths
        possible_paths = [
            Path(__file__).resolve().parents[1] / "data" / "ml-1m" / "splits" / "train.csv",  # from gnn/
            Path(__file__).resolve().parents[2] / "data" / "ml-1m" / "splits" / "train.csv",  # from backend/
            Path(__file__).resolve().parents[3] / "data" / "ml-1m" / "splits" / "train.csv",  # from fyp/
        ]

        train_csv_path = None
        for p in possible_paths:
            if p.exists():
                train_csv_path = p
                break

        if train_csv_path is None:
            print(f"[Warning] train.csv not found in any of: {possible_paths}")
            print("[Warning] Exporting all movies (not filtered to train set)")
            return None

    train_csv_path = Path(train_csv_path)
    if not train_csv_path.exists():
        print(f"[Warning] train.csv not found at {train_csv_path}, exporting all movies")
        return None

    train_df = pd.read_csv(train_csv_path)
    # 重要：轉成原生 Python int，避免 Cypher 裡出現 np.int64(...)
    train_movie_ids = {int(x) for x in train_df["movie_id"].dropna().unique().tolist()}
    print(f"[Info] Loaded {len(train_movie_ids)} movie IDs from train.csv at {train_csv_path}")
    return train_movie_ids


def fetch_basic_graph(
    manager: Neo4jManager,
    train_movie_ids: Optional[Set[int]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Fetch nodes and edges from Neo4j in a JSON-serializable form.

    If train_movie_ids is provided, only export movies in that set.

    Returns:
        nodes: list of dicts with keys: id, label, properties
        edges: list of dicts with keys: start_id, end_id, type
    """
    if not manager.driver:
        raise RuntimeError("Neo4jManager is not connected. Call connect() first.")

    movie_ids_list: Optional[List[int]] = None
    if train_movie_ids:
        movie_ids_list = sorted(int(x) for x in train_movie_ids)
        print(f"[Info] Filtering to {len(movie_ids_list)} movies from train.csv")

    # 用參數化，不要直接把 Python list 拼進 Cypher
    if movie_ids_list is not None:
        node_cypher = """
        MATCH (m:Movie)
        WHERE m.movie_id IN $movie_ids
        OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
        OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d:Person)
        OPTIONAL MATCH (m)-[:STARRED_BY]->(a:Person)
        RETURN
            collect(DISTINCT {
                id: id(m),
                label: 'Movie',
                movie_id: m.movie_id,
                title: m.title,
                year: m.year,
                average_rating: m.average_rating,
                rating_count: m.rating_count,
                view_count: m.view_count
            }) AS movies,
            collect(DISTINCT {
                id: id(g),
                label: 'Genre',
                name: g.name
            }) AS genres,
            collect(DISTINCT {
                id: id(d),
                label: 'Person',
                name: d.name,
                role: 'director'
            }) AS directors,
            collect(DISTINCT {
                id: id(a),
                label: 'Person',
                name: a.name,
                role: 'actor'
            }) AS actors
        """

        rel_cypher = """
        MATCH (m:Movie)-[r:HAS_GENRE]->(g:Genre)
        WHERE m.movie_id IN $movie_ids
        RETURN id(m) AS start_id, id(g) AS end_id, type(r) AS type
        UNION ALL
        MATCH (m:Movie)-[r:DIRECTED_BY]->(d:Person)
        WHERE m.movie_id IN $movie_ids
        RETURN id(m) AS start_id, id(d) AS end_id, type(r) AS type
        UNION ALL
        MATCH (m:Movie)-[r:STARRED_BY]->(a:Person)
        WHERE m.movie_id IN $movie_ids
        RETURN id(m) AS start_id, id(a) AS end_id, type(r) AS type
        UNION ALL
        MATCH (m1:Movie)-[r:SIMILAR_TO]->(m2:Movie)
        WHERE m1.movie_id IN $movie_ids AND m2.movie_id IN $movie_ids
        RETURN id(m1) AS start_id, id(m2) AS end_id, type(r) AS type
        """

        params = {"movie_ids": movie_ids_list}
    else:
        node_cypher = """
        MATCH (m:Movie)
        OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
        OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d:Person)
        OPTIONAL MATCH (m)-[:STARRED_BY]->(a:Person)
        RETURN
            collect(DISTINCT {
                id: id(m),
                label: 'Movie',
                movie_id: m.movie_id,
                title: m.title,
                year: m.year,
                average_rating: m.average_rating,
                rating_count: m.rating_count,
                view_count: m.view_count
            }) AS movies,
            collect(DISTINCT {
                id: id(g),
                label: 'Genre',
                name: g.name
            }) AS genres,
            collect(DISTINCT {
                id: id(d),
                label: 'Person',
                name: d.name,
                role: 'director'
            }) AS directors,
            collect(DISTINCT {
                id: id(a),
                label: 'Person',
                name: a.name,
                role: 'actor'
            }) AS actors
        """

        rel_cypher = """
        MATCH (m:Movie)-[r:HAS_GENRE]->(g:Genre)
        RETURN id(m) AS start_id, id(g) AS end_id, type(r) AS type
        UNION ALL
        MATCH (m:Movie)-[r:DIRECTED_BY]->(d:Person)
        RETURN id(m) AS start_id, id(d) AS end_id, type(r) AS type
        UNION ALL
        MATCH (m:Movie)-[r:STARRED_BY]->(a:Person)
        RETURN id(m) AS start_id, id(a) AS end_id, type(r) AS type
        UNION ALL
        MATCH (m1:Movie)-[r:SIMILAR_TO]->(m2:Movie)
        RETURN id(m1) AS start_id, id(m2) AS end_id, type(r) AS type
        """

        params = {}

    with manager.driver.session() as session:
        try:
            rec = session.run(node_cypher, **params).single()
        except Exception as e:
            print("=== NODE CYPHER FAILED ===")
            print(node_cypher)
            print("=== PARAMS PREVIEW ===")
            if movie_ids_list is not None:
                print({"movie_ids_first10": movie_ids_list[:10], "count": len(movie_ids_list)})
            else:
                print(params)
            raise RuntimeError(f"Neo4j node query failed: {e}") from e

        if not rec:
            raise RuntimeError("No movies found in Neo4j.")

        movies = [m for m in rec["movies"] if m and m.get("id") is not None]
        genres = [g for g in rec["genres"] if g and g.get("id") is not None]
        directors = [d for d in rec["directors"] if d and d.get("id") is not None]
        actors = [a for a in rec["actors"] if a and a.get("id") is not None]

        # Deduplicate persons that may appear in both director/actor collections
        persons_map: Dict[int, Dict[str, Any]] = {}
        for p in directors + actors:
            pid = int(p["id"])
            if pid not in persons_map:
                persons_map[pid] = p

        nodes: List[Dict[str, Any]] = []
        nodes.extend(movies)
        nodes.extend(genres)
        nodes.extend(list(persons_map.values()))

        try:
            rel_records = session.run(rel_cypher, **params)
        except Exception as e:
            print("=== REL CYPHER FAILED ===")
            print(rel_cypher)
            print("=== PARAMS PREVIEW ===")
            if movie_ids_list is not None:
                print({"movie_ids_first10": movie_ids_list[:10], "count": len(movie_ids_list)})
            else:
                print(params)
            raise RuntimeError(f"Neo4j relationship query failed: {e}") from e

        edges: List[Dict[str, Any]] = []
        for r in rel_records:
            if r["start_id"] is None or r["end_id"] is None or r["type"] is None:
                continue
            edges.append(
                {
                    "start_id": int(r["start_id"]),
                    "end_id": int(r["end_id"]),
                    "type": r["type"],
                }
            )

    return nodes, edges


def build_index_maps(
    nodes: List[Dict[str, Any]]
) -> Tuple[Dict[int, int], Dict[str, Dict[int, int]], Dict[int, int]]:
    """
    Build:
    - global neo4j_id -> global_index map,
    - per-type index maps: node_type -> (global_index -> type_index),
    - movie_id -> movie_type_index map (for later embedding export).
    """
    neo4j_to_global: Dict[int, int] = {}
    type_index_maps: Dict[str, Dict[int, int]] = defaultdict(dict)
    movie_id_to_type_index: Dict[int, int] = {}

    current_global = 0
    type_counters: Dict[str, int] = defaultdict(int)

    for n in nodes:
        neo_id = int(n["id"])
        label = n["label"]  # "Movie", "Genre", "Person"

        if neo_id in neo4j_to_global:
            continue

        neo4j_to_global[neo_id] = current_global
        type_idx = type_counters[label]
        type_index_maps[label][current_global] = type_idx

        if label == "Movie":
            movie_id = int(n["movie_id"])
            movie_id_to_type_index[movie_id] = type_idx

        current_global += 1
        type_counters[label] += 1

    return neo4j_to_global, type_index_maps, movie_id_to_type_index


def build_heterodata(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    neo4j_to_global: Dict[int, int],
    type_index_maps: Dict[str, Dict[int, int]],
) -> HeteroData:
    """Construct a HeteroData object from raw nodes/edges and index maps."""
    data = HeteroData()

    # 1) Node features (very simple numeric placeholders; refine as needed)
    # Movie
    movie_nodes = [n for n in nodes if n["label"] == "Movie"]
    num_movies = len(movie_nodes)
    movie_numeric = torch.zeros((num_movies, 4), dtype=torch.float32)  # [year, rating, log_rating_cnt, log_view_cnt]

    for n in movie_nodes:
        global_idx = neo4j_to_global[int(n["id"])]
        type_idx = type_index_maps["Movie"][global_idx]

        year = float(n.get("year") or 0.0)
        rating = float(n.get("average_rating") or 0.0)
        rating_cnt = float(n.get("rating_count") or 0.0)
        view_cnt = float(n.get("view_count") or 0.0)

        movie_numeric[type_idx, 0] = year / 2100.0  # simple normalization
        movie_numeric[type_idx, 1] = rating / 5.0
        movie_numeric[type_idx, 2] = torch.log1p(torch.tensor(rating_cnt, dtype=torch.float32))
        movie_numeric[type_idx, 3] = torch.log1p(torch.tensor(view_cnt, dtype=torch.float32))

    # Optionally augment movie features with precomputed text embeddings
    # from embeddings/movie_embeddings.npy + id_map.json if available.
    emb_dir = BACKEND_ROOT / "embeddings"
    text_emb_path = emb_dir / "movie_embeddings.npy"
    id_map_path = emb_dir / "id_map.json"

    if text_emb_path.exists() and id_map_path.exists():
        try:
            embs = np.load(text_emb_path).astype("float32")  # [N_text, D]
            with id_map_path.open("r", encoding="utf-8") as f:
                id_map = json.load(f)
            # id_map: {"idx_to_id": {"0": "movie_id", ...}, "id_to_idx": {...}}
            idx_to_id = {int(k): int(v) for k, v in id_map.get("idx_to_id", {}).items()}
            movie_id_to_emb_idx = {mid: idx for idx, mid in idx_to_id.items()}

            dim_text = embs.shape[1]
            movie_text = torch.zeros((num_movies, dim_text), dtype=torch.float32)
            for n in movie_nodes:
                neo_id = int(n["id"])
                global_idx = neo4j_to_global[neo_id]
                type_idx = type_index_maps["Movie"][global_idx]
                movie_id = int(n["movie_id"])
                emb_idx = movie_id_to_emb_idx.get(movie_id)
                if emb_idx is not None and 0 <= emb_idx < embs.shape[0]:
                    movie_text[type_idx] = torch.from_numpy(embs[emb_idx])

            movie_feats = torch.cat([movie_numeric, movie_text], dim=1)
        except Exception as e:
            print(f"[Warning] Failed to load movie text embeddings, fallback to numeric-only features: {e}")
            movie_feats = movie_numeric
    else:
        movie_feats = movie_numeric

    data["movie"].x = movie_feats

    # Genre
    genre_nodes = [n for n in nodes if n["label"] == "Genre"]
    num_genres = len(genre_nodes)
    data["genre"].x = (
        torch.eye(num_genres, dtype=torch.float32)
        if num_genres > 0
        else torch.zeros((0, 0), dtype=torch.float32)
    )

    # Person (director/actor)
    person_nodes = [n for n in nodes if n["label"] == "Person"]
    num_persons = len(person_nodes)
    data["person"].x = (
        torch.eye(num_persons, dtype=torch.float32)
        if num_persons > 0
        else torch.zeros((0, 0), dtype=torch.float32)
    )

    # 2) Edges: map Neo4j ids to per-type indices
    rel_type_map = {
        "HAS_GENRE": ("movie", "HAS_GENRE", "genre"),
        "DIRECTED_BY": ("movie", "DIRECTED_BY", "person"),
        "STARRED_BY": ("movie", "STARRED_BY", "person"),
        "SIMILAR_TO": ("movie", "SIMILAR_TO", "movie"),
    }

    edge_index_dict: Dict[Tuple[str, str, str], List[Tuple[int, int]]] = defaultdict(list)

    for e in edges:
        rel_type = e["type"]
        if rel_type not in rel_type_map:
            continue
        src_type, rel_name, dst_type = rel_type_map[rel_type]

        neo_src = int(e["start_id"])
        neo_dst = int(e["end_id"])

        if neo_src not in neo4j_to_global or neo_dst not in neo4j_to_global:
            continue

        g_src = neo4j_to_global[neo_src]
        g_dst = neo4j_to_global[neo_dst]

        def _type_key(t: str) -> str:
            if t == "movie":
                return "Movie"
            if t == "genre":
                return "Genre"
            if t == "person":
                return "Person"
            return t

        src_key = _type_key(src_type)
        dst_key = _type_key(dst_type)

        type_src = type_index_maps[src_key][g_src]
        type_dst = type_index_maps[dst_key][g_dst]

        edge_index_dict[(src_type, rel_name, dst_type)].append((type_src, type_dst))

    for (src_type, rel_name, dst_type), pairs in edge_index_dict.items():
        if not pairs:
            continue
        src_indices = torch.tensor([p[0] for p in pairs], dtype=torch.long)
        dst_indices = torch.tensor([p[1] for p in pairs], dtype=torch.long)
        data[(src_type, rel_name, dst_type)].edge_index = torch.stack([src_indices, dst_indices], dim=0)

    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Neo4j KG to PyG HeteroData")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="app/backend/embeddings",
        help="Directory to store data_kg.pt and movie_id_map.json",
    )
    parser.add_argument(
        "--train-csv-path",
        type=str,
        default=None,
        help="Optional explicit path to train.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_movie_ids = load_train_movie_ids(args.train_csv_path)

    manager = Neo4jManager()
    if not manager.connect():
        raise RuntimeError("Failed to connect to Neo4j. Check NEO4J_URI/USER/PASSWORD.")

    try:
        print("Fetching graph from Neo4j...")
        nodes, edges = fetch_basic_graph(manager, train_movie_ids=train_movie_ids)

        print(f"Fetched {len(nodes)} nodes and {len(edges)} edges.")

        neo4j_to_global, type_index_maps, movie_id_to_type_index = build_index_maps(nodes)
        data = build_heterodata(nodes, edges, neo4j_to_global, type_index_maps)

        data_path = output_dir / "data_kg.pt"
        torch.save(data, data_path)
        print(f"Saved HeteroData to: {data_path}")

        movie_id_map_path = output_dir / "movie_id_map.json"
        with movie_id_map_path.open("w", encoding="utf-8") as f:
            json.dump(movie_id_to_type_index, f, ensure_ascii=False, indent=2)
        print(f"Saved movie_id -> node_index map to: {movie_id_map_path}")

    finally:
        manager.close()


if __name__ == "__main__":
    main()