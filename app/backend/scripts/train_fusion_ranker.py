#!/usr/bin/env python3
"""
Train a simple learning-to-rank fusion model for ANN/KG/GNN scores.

Output:
  app/backend/embeddings/hybrid_ltr_weights.json

Usage:
  cd app/backend
  python train_fusion_ranker.py --max-users 400 --top-k 120 --epochs 250
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from typing import List, Dict, Tuple

import numpy as np
from sqlalchemy.orm import Session

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # app/backend/scripts
BACKEND_DIR = os.path.dirname(CURRENT_DIR)                 # app/backend
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Force manual fusion during training-data construction.
# This avoids circular dependency on previously learned weights.
os.environ["HYBRID_FUSION_MODE"] = "manual"

from database import SessionLocal  # type: ignore
from models import User, Rating, Favorite, Like  # type: ignore
from services.retrieval import HybridRetriever  # type: ignore


DEFAULT_OUT = os.path.join(BACKEND_DIR, "embeddings", "hybrid_ltr_weights.json")


def _build_features(a: float, k: float, g: float) -> np.ndarray:
    return np.array([1.0, a, k, g, a * k, a * g, k * g], dtype=np.float64)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -50.0, 50.0)
    return 1.0 / (1.0 + np.exp(-x))


def _collect_positive_movie_ids(db: Session, user_id: int) -> set[int]:
    positives: set[int] = set()
    for r in db.query(Rating).filter(Rating.user_id == user_id).all():
        if float(r.rating) >= 4.0:
            positives.add(int(r.movie_id))
    for f in db.query(Favorite).filter(Favorite.user_id == user_id).all():
        positives.add(int(f.movie_id))
    for l in db.query(Like).filter(Like.user_id == user_id).all():
        positives.add(int(l.movie_id))
    return positives


def build_training_data(db: Session, max_users: int, top_k: int) -> Tuple[np.ndarray, np.ndarray]:
    retriever = HybridRetriever(db=db)
    users = db.query(User).limit(max_users).all()

    x_rows: List[np.ndarray] = []
    y_rows: List[float] = []

    for u in users:
        uid = int(u.id)
        positives = _collect_positive_movie_ids(db, uid)
        if not positives:
            continue

        try:
            results = retriever.recommend(
                user_id=uid,
                top_k=top_k,
                ann_k=max(80, top_k),
                mode="full",
            )
        except Exception:
            continue

        for row in results:
            mid = int(row.get("movie_id", -1))
            if mid < 0:
                continue
            ann = float(row.get("ann_score", 0.0))
            kg = float(row.get("kg_score", 0.0))
            gnn = float(row.get("gnn_score", 0.0))
            y = 1.0 if mid in positives else 0.0
            x_rows.append(_build_features(ann, kg, gnn))
            y_rows.append(y)

    if not x_rows:
        return np.zeros((0, 7), dtype=np.float64), np.zeros((0,), dtype=np.float64)
    return np.vstack(x_rows), np.array(y_rows, dtype=np.float64)


def train_logistic_regression(
    x: np.ndarray,
    y: np.ndarray,
    epochs: int,
    lr: float,
    l2: float,
) -> np.ndarray:
    if x.size == 0:
        return np.array([-1.2, 2.4, 1.6, 1.8, 0.8, 1.0, 0.6], dtype=np.float64)

    w = np.zeros((x.shape[1],), dtype=np.float64)

    pos = max(1.0, float(y.sum()))
    neg = max(1.0, float(len(y) - y.sum()))
    pos_weight = neg / pos
    sample_weight = np.where(y > 0.5, pos_weight, 1.0)

    for _ in range(max(1, int(epochs))):
        logits = x @ w
        p = _sigmoid(logits)
        grad = (x.T @ ((p - y) * sample_weight)) / float(len(y))
        grad += l2 * w
        w -= lr * grad

    # Enforce monotonic contributions for ANN/KG/GNN features and interactions.
    # We do not constrain bias.
    w[1:] = np.maximum(0.0, w[1:])

    # If training collapses to near-zero signal, fall back to conservative defaults.
    if float(np.sum(np.abs(w[1:]))) < 1e-6:
        return np.array([-1.2, 2.4, 1.6, 1.8, 0.8, 1.0, 0.6], dtype=np.float64)

    return w


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--max-users", type=int, default=400)
    p.add_argument("--top-k", type=int, default=120)
    p.add_argument("--epochs", type=int, default=250)
    p.add_argument("--lr", type=float, default=0.05)
    p.add_argument("--l2", type=float, default=1e-4)
    p.add_argument("--out", type=str, default=DEFAULT_OUT)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    db: Session = SessionLocal()
    try:
        x, y = build_training_data(db, max_users=args.max_users, top_k=args.top_k)
        print(f"Training rows: {len(y)}")
        if len(y) == 0:
            raise RuntimeError("No training samples built. Check database interactions first.")

        w = train_logistic_regression(x, y, epochs=args.epochs, lr=args.lr, l2=args.l2)
        out_obj: Dict[str, float] = {
            "bias": float(w[0]),
            "ann": float(w[1]),
            "kg": float(w[2]),
            "gnn": float(w[3]),
            "ann_kg": float(w[4]),
            "ann_gnn": float(w[5]),
            "kg_gnn": float(w[6]),
        }

        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out_obj, f, ensure_ascii=False, indent=2)
        print(f"Saved fusion weights to: {args.out}")
        print(json.dumps(out_obj, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
