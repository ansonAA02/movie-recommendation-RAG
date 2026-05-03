#!/usr/bin/env python3
"""
Unified evaluation script for NeoRAGRec modes using train/valid/test split.

Modes:
- popular: popularity baseline
- content_only: ANN only (text embeddings)
- hybrid_no_gnn: ANN + KG (no GNN)
- full: ANN + KG + GNN (complete system)

Metrics:
- Recall@10, Recall@20
- NDCG@10, NDCG@20
- Coverage

Protocol:
- Train: history for training graph / embeddings
- Valid: tune weights/parameters
- Test: final evaluation (run once)

IMPORTANT:
- When evaluating VALID, history/seen come from TRAIN only
- When evaluating TEST, history/seen come from TRAIN + VALID
- Supports multiple ground-truth items per user
"""

#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Set, Tuple, Any
import math

import numpy as np
import pandas as pd

# ============================================================
# Path setup
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent          # app/backend/scripts
BACKEND_DIR = SCRIPT_DIR.parent                       # app/backend
PROJECT_ROOT = BACKEND_DIR.parent.parent              # project root

for p in [BACKEND_DIR, PROJECT_ROOT]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from database import SessionLocal
from services.retrieval import HybridRetriever


# ============================================================
# Data Loading
# ============================================================
def load_split_data(train_path: str, valid_path: str, test_path: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load split CSV files and normalize key columns."""
    train_df = pd.read_csv(train_path)
    valid_df = pd.read_csv(valid_path)
    test_df = pd.read_csv(test_path)

    for name, df in [("train", train_df), ("valid", valid_df), ("test", test_df)]:
        if "user_id" not in df.columns or "movie_id" not in df.columns:
            raise ValueError(f"{name}.csv must contain columns: user_id, movie_id")
        df["user_id"] = pd.to_numeric(df["user_id"], errors="raise").astype(int)
        df["movie_id"] = pd.to_numeric(df["movie_id"], errors="raise").astype(int)

        # Optional timestamp normalization if present
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")

    return train_df, valid_df, test_df


def build_history_map(df: pd.DataFrame) -> Dict[int, List[int]]:
    """
    Build user -> ordered movie_ids list from dataframe.
    If timestamp exists, sort by timestamp first.
    Deduplicate while preserving order.
    """
    hist: Dict[int, List[int]] = {}

    work_df = df.copy()
    if "timestamp" in work_df.columns:
        work_df = work_df.sort_values(["user_id", "timestamp"], ascending=[True, True])

    for uid, grp in work_df.groupby("user_id"):
        vals = grp["movie_id"].astype(int).tolist()
        hist[int(uid)] = list(dict.fromkeys(vals))  # deduplicate, preserve order

    return hist


def concat_history_maps(*maps: Dict[int, List[int]]) -> Dict[int, List[int]]:
    """Concatenate multiple history maps, deduplicating while preserving order."""
    out: Dict[int, List[int]] = {}
    for mp in maps:
        for uid, items in mp.items():
            out.setdefault(uid, [])
            out[uid].extend(items)
            out[uid] = list(dict.fromkeys(out[uid]))
    return out


def build_seen_from_df(df: pd.DataFrame) -> Dict[int, Set[int]]:
    """Build user -> seen items set from a dataframe."""
    seen: Dict[int, Set[int]] = {}
    for uid, grp in df.groupby("user_id"):
        seen[int(uid)] = set(grp["movie_id"].astype(int).tolist())
    return seen


def build_ground_truth(df: pd.DataFrame) -> Dict[int, List[int]]:
    """
    Build user -> list of ground-truth items.
    Supports one or multiple positives per user.
    If timestamp exists, preserve chronological order.
    """
    gt: Dict[int, List[int]] = {}

    work_df = df.copy()
    if "timestamp" in work_df.columns:
        work_df = work_df.sort_values(["user_id", "timestamp"], ascending=[True, True])

    for uid, grp in work_df.groupby("user_id"):
        items = grp["movie_id"].astype(int).tolist()
        gt[int(uid)] = list(dict.fromkeys(items))

    return gt


# ============================================================
# Metrics
# ============================================================
def recall_at_k(recommended: List[int], ground_truth_items: List[int], k: int) -> float:
    """Recall@K for one user with potentially multiple positives."""
    if not ground_truth_items:
        return 0.0
    topk = recommended[:k]
    hits = sum(1 for item in ground_truth_items if item in topk)
    return hits / max(1, len(ground_truth_items))


def ndcg_at_k(recommended: List[int], ground_truth_items: List[int], k: int) -> float:
    """NDCG@K for one user with binary relevance and multiple positives."""
    if not ground_truth_items:
        return 0.0

    gt_set = set(ground_truth_items)
    topk = recommended[:k]

    dcg = 0.0
    for rank, item in enumerate(topk, start=1):
        if item in gt_set:
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(len(gt_set), k)
    if ideal_hits == 0:
        return 0.0

    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


# ============================================================
# Evaluation
# ============================================================
def evaluate_mode(
    db,
    mode: str,
    history_map: Dict[int, List[int]],
    ground_truth: Dict[int, List[int]],
    seen_dict: Dict[int, Set[int]],
    ks: List[int],
    max_users: int = 0,
    candidate_multiplier: int = 5,
) -> Dict[str, Any]:
    """Evaluate one mode on ground truth."""
    retriever = HybridRetriever(db=db)

    # Override history function to use CSV split history
    original_history_fn = retriever.user_history_movie_ids

    def fixed_history(user_id: int):
        return history_map.get(user_id, [])

    retriever.user_history_movie_ids = fixed_history

    recalls: Dict[int, List[float]] = {k: [] for k in ks}
    ndcgs: Dict[int, List[float]] = {k: [] for k in ks}
    rec_lengths: List[int] = []
    recommended_set: Set[int] = set()

    users_evaluated = 0
    users_failed = 0

    eval_users = list(ground_truth.keys())
    if max_users > 0:
        eval_users = eval_users[:max_users]

    request_top_k = max(ks) * max(1, candidate_multiplier)

    for idx, user_id in enumerate(eval_users, start=1):
        gt_items = ground_truth.get(user_id, [])
        seen = seen_dict.get(user_id, set())

        try:
            raw_recs = retriever.recommend(user_id=user_id, top_k=request_top_k, mode=mode)
        except Exception as e:
            users_failed += 1
            if idx <= 5:
                print(f"[Warning] {mode} failed for user {user_id}: {e}")
            raw_recs = []

        # Extract movie IDs and filter out seen items
        movie_ids: List[int] = []
        seen_local: Set[int] = set()
        for row in raw_recs:
            mid = row.get("movie_id") if isinstance(row, dict) else None
            if mid is None:
                continue
            mid = int(mid)
            if mid in seen:
                continue
            if mid in seen_local:
                continue
            seen_local.add(mid)
            movie_ids.append(mid)

        rec_lengths.append(len(movie_ids))
        recommended_set.update(movie_ids)

        for k in ks:
            recalls[k].append(recall_at_k(movie_ids, gt_items, k))
            ndcgs[k].append(ndcg_at_k(movie_ids, gt_items, k))

        users_evaluated += 1

        if idx % 100 == 0:
            print(f"  [{mode}] Processed {idx}/{len(eval_users)} users")

    # Restore original history function
    retriever.user_history_movie_ids = original_history_fn

    summary: Dict[str, Any] = {
        "mode": mode,
        "num_users": users_evaluated,
        "num_test_cases": users_evaluated,
        "users_failed": users_failed,
        "avg_rec_len": float(np.mean(rec_lengths)) if rec_lengths else 0.0,
    }

    for k in ks:
        summary[f"recall@{k}"] = float(np.mean(recalls[k])) if recalls[k] else 0.0
        summary[f"ndcg@{k}"] = float(np.mean(ndcgs[k])) if ndcgs[k] else 0.0

    from models import Movie
    total_movies = db.query(Movie).count()
    summary["coverage"] = float(len(recommended_set) / max(1, total_movies))

    return summary


# ============================================================
# CLI
# ============================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Unified evaluation for NeoRAGRec modes")
    p.add_argument("--train", type=str, required=True, help="Path to train.csv")
    p.add_argument("--valid", type=str, required=True, help="Path to valid.csv")
    p.add_argument("--test", type=str, required=True, help="Path to test.csv")
    p.add_argument(
        "--modes",
        type=str,
        default="popular,content_only,hybrid_no_gnn,full",
        help="Comma-separated modes to evaluate",
    )
    p.add_argument("--ks", type=str, default="10,20", help="Comma-separated K values")
    p.add_argument(
        "--split",
        type=str,
        default="valid",
        choices=["valid", "test"],
        help="Which split to evaluate on (valid for tuning, test for final)",
    )
    p.add_argument("--max-users", type=int, default=0, help="Max users to evaluate (0=all)")
    p.add_argument(
        "--candidate-multiplier",
        type=int,
        default=5,
        help="Request top_k = max(ks) * candidate_multiplier before seen filtering",
    )
    p.add_argument("--output", type=str, default="evaluation_results.json", help="Output JSON path")
    return p.parse_args()


def print_summary_table(results: List[Dict[str, Any]], ks: List[int]) -> None:
    print("\n" + "=" * 110)
    print("SUMMARY TABLE")
    print("=" * 110)
    for r in results:
        recall_str = " | ".join([f"R@{k}={r.get(f'recall@{k}', 0):.4f}" for k in ks])
        ndcg_str = " | ".join([f"NDCG@{k}={r.get(f'ndcg@{k}', 0):.4f}" for k in ks])
        print(
            f"mode={r['mode']:18s} | users={r['num_users']:5d} | "
            f"{recall_str} | {ndcg_str} | "
            f"coverage={r['coverage']:.4f} | avg_len={r['avg_rec_len']:.2f} | failed={r['users_failed']}"
        )


def main() -> None:
    args = parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    ks = sorted([int(k.strip()) for k in args.ks.split(",") if k.strip()])

    print(f"[Config] modes={modes}, ks={ks}, split={args.split}, max_users={args.max_users}")

    # Load split data
    train_df, valid_df, test_df = load_split_data(args.train, args.valid, args.test)
    print(f"[Data] train={len(train_df)}, valid={len(valid_df)}, test={len(test_df)}")

    # Build histories
    train_history = build_history_map(train_df)
    valid_history = build_history_map(valid_df)

    # Select evaluation protocol
    if args.split == "valid":
        eval_df = valid_df
        history_map = train_history
        seen_dict = build_seen_from_df(train_df)
        print(f"[Eval] VALID split selected")
        print(f"[Eval] History source: TRAIN only")
        print(f"[Eval] Seen filter source: TRAIN only")
    else:
        eval_df = test_df
        history_map = concat_history_maps(train_history, valid_history)
        seen_source_df = pd.concat([train_df[["user_id", "movie_id"]], valid_df[["user_id", "movie_id"]]], ignore_index=True)
        seen_dict = build_seen_from_df(seen_source_df)
        print(f"[Eval] TEST split selected")
        print(f"[Eval] History source: TRAIN + VALID")
        print(f"[Eval] Seen filter source: TRAIN + VALID")

    ground_truth = build_ground_truth(eval_df)
    print(f"[Eval] Ground truth users: {len(ground_truth)}")

    db = SessionLocal()

    try:
        results = []
        for mode in modes:
            print(f"\n=== Evaluating mode: {mode} ===")
            summary = evaluate_mode(
                db=db,
                mode=mode,
                history_map=history_map,
                ground_truth=ground_truth,
                seen_dict=seen_dict,
                ks=ks,
                max_users=args.max_users,
                candidate_multiplier=args.candidate_multiplier,
            )
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            results.append(summary)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "config": {
                "modes": modes,
                "ks": ks,
                "split": args.split,
                "max_users": args.max_users,
                "candidate_multiplier": args.candidate_multiplier,
            },
            "results": results,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"\n[Output] Saved to: {output_path}")
        print_summary_table(results, ks)

    finally:
        db.close()


if __name__ == "__main__":
    main()