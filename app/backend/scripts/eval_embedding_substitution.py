#!/usr/bin/env python3
"""
Quick embedding substitution evaluation.
Compares 'full' mode with different GNN embedding sources:
  - our_gnn: current GNN (movie_subgraph_embeddings.npy)
  - kgin:    KGIN embeddings (kgin_movie_embeddings.npy)

Usage (from app/backend/scripts):
  python eval_embedding_substitution.py \
    --train train.csv --valid valid.csv --test test.csv \
    --split test --max-users 200 --output results_embedding_subst.json
"""
from __future__ import annotations

import sys, json, math, argparse
from pathlib import Path
from typing import List, Dict, Set, Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib

matplotlib.rcParams['font.family'] = ['DejaVu Sans', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent

for p in [BACKEND_DIR, BACKEND_DIR.parent.parent]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Embedding configs: name -> (emb_path, id_map_path)
EMBEDDING_CONFIGS = {
    "our_gnn": (
        str(BACKEND_DIR / "embeddings" / "embeddings1" / "movie_subgraph_embeddings.npy"),
        str(BACKEND_DIR / "embeddings" / "embeddings1" / "movie_subgraph_id_map.json"),
    ),
    "kgin": (
        str(BACKEND_DIR / "Kgin" / "Embedding" / "kgin_movie_embeddings.npy"),
        str(BACKEND_DIR / "Kgin" / "Embedding" / "kgin_movie_id_map.json"),
    ),
    "kgat": (
        str(BACKEND_DIR / "Kgat" / "Embedding" / "kgat_movie_embeddings.npy"),
        str(BACKEND_DIR / "Kgat" / "Embedding" / "kgat_movie_id_map.json"),
    ),
}


def recall_at_k(recommended: List[int], gt: List[int], k: int) -> float:
    if not gt:
        return 0.0
    return sum(1 for x in gt if x in recommended[:k]) / max(1, len(gt))


def ndcg_at_k(recommended: List[int], gt: List[int], k: int) -> float:
    if not gt:
        return 0.0
    gt_set = set(gt)
    dcg = sum(1.0 / math.log2(r + 1) for r, x in enumerate(recommended[:k], 1) if x in gt_set)
    idcg = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(gt_set), k) + 1))
    return dcg / idcg if idcg > 0 else 0.0


def load_split(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["user_id"] = pd.to_numeric(df["user_id"], errors="raise").astype(int)
    df["movie_id"] = pd.to_numeric(df["movie_id"], errors="raise").astype(int)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    return df


def build_history(df: pd.DataFrame) -> Dict[int, List[int]]:
    hist: Dict[int, List[int]] = {}
    work = df.copy()
    if "timestamp" in work.columns:
        work = work.sort_values(["user_id", "timestamp"])
    for uid, grp in work.groupby("user_id"):
        hist[int(uid)] = list(dict.fromkeys(grp["movie_id"].astype(int).tolist()))
    return hist


def build_gt(df: pd.DataFrame) -> Dict[int, List[int]]:
    gt: Dict[int, List[int]] = {}
    work = df.copy()
    if "timestamp" in work.columns:
        work = work.sort_values(["user_id", "timestamp"])
    for uid, grp in work.groupby("user_id"):
        gt[int(uid)] = list(dict.fromkeys(grp["movie_id"].astype(int).tolist()))
    return gt


def evaluate_with_embedding(
    emb_name: str,
    emb_path: str,
    id_map_path: str,
    db,
    history_map: Dict[int, List[int]],
    ground_truth: Dict[int, List[int]],
    seen_dict: Dict[int, Set[int]],
    ks: List[int],
    max_users: int = 0,
    candidate_multiplier: int = 5,
) -> Dict[str, Any]:
    import services.retrieval as ret_mod

    # Patch GNN embedding paths and reset cached globals
    ret_mod.GNN_EMB_PATH = emb_path
    ret_mod.GNN_ID_LIST_PATH = id_map_path
    ret_mod._gnn_embs = None
    ret_mod._gnn_movie_ids = None
    ret_mod._gnn_id_to_idx = None

    from services.retrieval import HybridRetriever
    retriever = HybridRetriever(db=db)

    def fixed_history(user_id: int):
        return history_map.get(user_id, [])

    retriever.user_history_movie_ids = fixed_history

    recalls: Dict[int, List[float]] = {k: [] for k in ks}
    ndcgs: Dict[int, List[float]] = {k: [] for k in ks}
    rec_set: Set[int] = set()
    users_failed = 0

    eval_users = list(ground_truth.keys())
    if max_users > 0:
        eval_users = eval_users[:max_users]

    request_top_k = max(ks) * max(1, candidate_multiplier)

    for idx, uid in enumerate(eval_users, 1):
        gt_items = ground_truth.get(uid, [])
        seen = seen_dict.get(uid, set())
        try:
            raw = retriever.recommend(user_id=uid, top_k=request_top_k, mode="full")
        except Exception as e:
            users_failed += 1
            if idx <= 3:
                print(f"  [Warning] {emb_name} user {uid}: {e}")
            raw = []

        movie_ids: List[int] = []
        seen_local: Set[int] = set()
        for row in raw:
            mid = row.get("movie_id") if isinstance(row, dict) else None
            if mid is None:
                continue
            mid = int(mid)
            if mid in seen or mid in seen_local:
                continue
            seen_local.add(mid)
            movie_ids.append(mid)

        rec_set.update(movie_ids)
        for k in ks:
            recalls[k].append(recall_at_k(movie_ids, gt_items, k))
            ndcgs[k].append(ndcg_at_k(movie_ids, gt_items, k))

        if idx % 50 == 0:
            print(f"  [{emb_name}] {idx}/{len(eval_users)} users")

    from models import Movie
    total_movies = db.query(Movie).count()

    summary: Dict[str, Any] = {
        "embedding": emb_name,
        "num_users": len(eval_users),
        "users_failed": users_failed,
        "coverage": float(len(rec_set) / max(1, total_movies)),
    }
    for k in ks:
        summary[f"recall@{k}"] = float(np.mean(recalls[k])) if recalls[k] else 0.0
        summary[f"ndcg@{k}"] = float(np.mean(ndcgs[k])) if ndcgs[k] else 0.0
    return summary


def plot_embedding_results(payload: Dict[str, Any], output_json_path: Path) -> None:
    results = payload.get("results", [])
    ks = payload.get("config", {}).get("ks", [])
    if not results or not ks:
        print("[Plot] Skip plotting: empty results or ks")
        return

    output_dir = output_json_path.parent
    stem = output_json_path.stem

    embeddings = ["my_gnn" if r["embedding"] == "kgin" else r["embedding"] for r in results]
    colors = plt.cm.Set2.colors[:len(embeddings)]

    # Figure 1: Recall / NDCG vs K
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    for i, r in enumerate(results):
        recall_vals = [r.get(f"recall@{k}", 0.0) for k in ks]
        ndcg_vals = [r.get(f"ndcg@{k}", 0.0) for k in ks]
        ax1.plot(ks, recall_vals, "o-", linewidth=2, markersize=7, color=colors[i], label=r["embedding"])
        ax2.plot(ks, ndcg_vals, "o-", linewidth=2, markersize=7, color=colors[i], label=r["embedding"])

    ax1.set_title("Recall@K by Embedding")
    ax1.set_xlabel("K")
    ax1.set_ylabel("Recall@K")
    ax1.set_xticks(ks)
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax2.set_title("NDCG@K by Embedding")
    ax2.set_xlabel("K")
    ax2.set_ylabel("NDCG@K")
    ax2.set_xticks(ks)
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    plt.tight_layout()
    out1 = output_dir / f"{stem}_lines.png"
    plt.savefig(out1, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"[Plot] Saved: {out1}")

    # Figure 2: bar overview at first K + coverage
    first_k = ks[0]
    x = np.arange(len(embeddings))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 5))
    recall_vals = [r.get(f"recall@{first_k}", 0.0) for r in results]
    ndcg_vals = [r.get(f"ndcg@{first_k}", 0.0) for r in results]
    coverage_vals = [r.get("coverage", 0.0) for r in results]

    ax.bar(x - width, recall_vals, width, label=f"Recall@{first_k}", color="#60a5fa")
    ax.bar(x, ndcg_vals, width, label=f"NDCG@{first_k}", color="#34d399")
    ax.bar(x + width, coverage_vals, width, label="Coverage", color="#f59e0b")

    ax.set_xticks(x)
    ax.set_xticklabels(embeddings)
    ax.set_ylabel("Score")
    ax.set_title("Embedding Substitution Overview")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()

    plt.tight_layout()
    out2 = output_dir / f"{stem}_overview.png"
    plt.savefig(out2, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"[Plot] Saved: {out2}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train", required=True)
    p.add_argument("--valid", required=True)
    p.add_argument("--test", required=True)
    p.add_argument("--split", default="test", choices=["valid", "test"])
    p.add_argument("--max-users", type=int, default=200)
    p.add_argument("--ks", default="10,20")
    p.add_argument("--candidate-multiplier", type=int, default=5)
    p.add_argument("--output", default="results_embedding_subst.json")
    p.add_argument("--plot-only", default="", help="Path to an existing results JSON; if provided, only generate charts")
    p.add_argument(
        "--embeddings",
        default="our_gnn,kgin,kgat",
        help="Comma-separated embedding names to test (our_gnn, kgin, kgat)",
    )
    args = p.parse_args()

    if args.plot_only:
        plot_path = Path(args.plot_only)
        payload = json.loads(plot_path.read_text(encoding="utf-8"))
        plot_embedding_results(payload, plot_path)
        print(f"[Plot-only] Done for: {plot_path}")
        return

    ks = sorted(int(k) for k in args.ks.split(",") if k.strip())
    emb_names = [e.strip() for e in args.embeddings.split(",") if e.strip()]

    train_df = load_split(args.train)
    valid_df = load_split(args.valid)
    test_df = load_split(args.test)

    train_hist = build_history(train_df)
    valid_hist = build_history(valid_df)

    if args.split == "test":
        eval_df = test_df
        history_map: Dict[int, List[int]] = {}
        for uid, items in train_hist.items():
            history_map.setdefault(uid, []).extend(items)
        for uid, items in valid_hist.items():
            history_map.setdefault(uid, []).extend(items)
        for uid in history_map:
            history_map[uid] = list(dict.fromkeys(history_map[uid]))
        seen_source = pd.concat(
            [train_df[["user_id", "movie_id"]], valid_df[["user_id", "movie_id"]]],
            ignore_index=True,
        )
    else:
        eval_df = valid_df
        history_map = dict(train_hist)
        seen_source = train_df

    seen_dict: Dict[int, Set[int]] = {}
    for uid, grp in seen_source.groupby("user_id"):
        seen_dict[int(uid)] = set(grp["movie_id"].astype(int).tolist())

    gt = build_gt(eval_df)
    print(f"[Config] split={args.split}, max_users={args.max_users}, ks={ks}")
    print(f"[Config] embeddings={emb_names}")
    print(f"[Data] GT users={len(gt)}")

    from database import SessionLocal
    db = SessionLocal()

    results = []
    try:
        for emb_name in emb_names:
            if emb_name not in EMBEDDING_CONFIGS:
                print(f"[Skip] unknown embedding: {emb_name}")
                continue
            emb_path, id_map_path = EMBEDDING_CONFIGS[emb_name]
            print(f"\n=== Evaluating embedding: {emb_name} ===")
            print(f"    emb: {emb_path}")
            print(f"    id_map: {id_map_path}")
            summary = evaluate_with_embedding(
                emb_name=emb_name,
                emb_path=emb_path,
                id_map_path=id_map_path,
                db=db,
                history_map=history_map,
                ground_truth=gt,
                seen_dict=seen_dict,
                ks=ks,
                max_users=args.max_users,
                candidate_multiplier=args.candidate_multiplier,
            )
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            results.append(summary)
    finally:
        db.close()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": {
            "split": args.split,
            "max_users": args.max_users,
            "ks": ks,
            "embeddings": emb_names,
            "candidate_multiplier": args.candidate_multiplier,
        },
        "results": results,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[Output] Saved to: {out}")
    plot_embedding_results(payload, out)

    # Print summary table
    print("\n" + "=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)
    for r in results:
        recall_str = " | ".join(f"R@{k}={r.get(f'recall@{k}', 0):.4f}" for k in ks)
        ndcg_str = " | ".join(f"NDCG@{k}={r.get(f'ndcg@{k}', 0):.4f}" for k in ks)
        print(f"emb={r['embedding']:15s} | {recall_str} | {ndcg_str} | coverage={r['coverage']:.4f} | failed={r['users_failed']}")


if __name__ == "__main__":
    main()
