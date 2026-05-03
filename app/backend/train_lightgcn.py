#!/usr/bin/env python3
"""
Train LightGCN on MovieLens-1M using RecBole API directly.
Avoids using quick_start CLI which imports `ray` (not available on Windows pip).

Usage:
    cd app/backend
    python train_lightgcn.py

Outputs:
    outputs/lightgcn/lightgcn_results.txt  - Recall@10, NDCG@10
    outputs/lightgcn/saved/LightGCN-*.pth  - trained model checkpoint
"""

from __future__ import annotations
import os
import sys
import csv
import shutil
from pathlib import Path

# ------------------------------------------------------------------ #
# Paths
# ------------------------------------------------------------------ #
BACKEND_DIR = Path(__file__).resolve().parent          # app/backend
PROJECT_DIR = BACKEND_DIR.parent.parent                # fyp/
ML1M_DIR    = PROJECT_DIR / "data" / "ml-1m"
SPLITS_DIR  = ML1M_DIR / "splits"

DATASET_NAME = "ml1m_lightgcn"
DATASET_DIR  = BACKEND_DIR / "dataset" / DATASET_NAME  # recbole dataset folder
OUTPUT_DIR   = BACKEND_DIR / "outputs" / "lightgcn"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ #
# Step 1: Convert train/valid/test CSV -> RecBole .inter format
# RecBole expects: user_id:token\titem_id:token\trating:float\n
# For implicit feedback (no rating column) use rating=1.0
# ------------------------------------------------------------------ #
INTERACTIONS_CSV = ML1M_DIR / "interactions.csv"  # user_id,movie_id,rating
MIN_RATING = 4  # only keep ratings >= 4 as positive implicit feedback


def convert_interactions_to_inter(out_inter: Path) -> int:
    """
    Convert interactions.csv -> RecBole .inter format.
    Only keeps ratings >= MIN_RATING as implicit positive feedback.
    Format: user_id:token\titem_id:token\n
    """
    count = 0
    skipped = 0
    with open(INTERACTIONS_CSV, encoding="utf-8") as fin, \
         open(out_inter, "w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        fout.write("user_id:token\titem_id:token\n")
        for row in reader:
            rating = float(row.get("rating", 5))
            if rating < MIN_RATING:
                skipped += 1
                continue
            uid = row["user_id"].strip()
            mid = row["movie_id"].strip()
            fout.write(f"{uid}\t{mid}\n")
            count += 1
    print(f"  Kept {count} interactions (rating>={MIN_RATING}), skipped {skipped} low-rating rows")
    return count


def prepare_dataset() -> None:
    """Create RecBole dataset directory from interactions.csv."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    out_inter = DATASET_DIR / f"{DATASET_NAME}.inter"
    if out_inter.exists():
        print(f"  {out_inter.name} already exists, skipping conversion")
        return
    print(f"  Converting {INTERACTIONS_CSV.name} -> {out_inter.name}")
    convert_interactions_to_inter(out_inter)


# ------------------------------------------------------------------ #
# Step 2: Build RecBole config dict
# ------------------------------------------------------------------ #
def build_config_dict() -> dict:
    return {
        # Dataset
        "dataset":          DATASET_NAME,
        "data_path":        str(BACKEND_DIR / "dataset"),

        # Model
        "model":            "LightGCN",
        "embedding_size":   64,
        "n_layers":         3,

        # Training
        "epochs":           50,
        "train_batch_size": 2048,
        "eval_batch_size":  1024,
        "learning_rate":    1e-3,
        "train_neg_sample_args": {"distribution": "uniform", "sample_num": 1},

        # Evaluation — RS split: 80/10/10 ratio
        "eval_args": {
            "split":    {"RS": [0.8, 0.1, 0.1]},
            "group_by": "user",
            "order":    "RO",
            "mode":     "full",
        },
        "metrics":       ["Recall", "NDCG", "Hit"],
        "topk":          [10],
        "valid_metric":  "Recall@10",

        # Logging / saving
        "checkpoint_dir": str(OUTPUT_DIR / "saved"),
        "log_wandb":      False,
        "show_progress":  True,

        # Reproducibility
        "seed":           42,
        "reproducibility": True,

        # Data format flags — no rating column in merged file
        "load_col":        {"inter": ["user_id", "item_id"]},
        "USER_ID_FIELD":   "user_id",
        "ITEM_ID_FIELD":   "item_id",
        "field_separator": "\t",
    }


# ------------------------------------------------------------------ #
# Step 3: Train with RecBole API (no quick_start, no ray)
# ------------------------------------------------------------------ #
def train() -> None:
    print("Importing RecBole (may take a moment)...")
    from recbole.config import Config
    from recbole.data import create_dataset, data_preparation
    # Import LightGCN directly from its module to avoid __init__.py
    # importing LDiffRec which requires kmeans_pytorch (unavailable on Windows)
    from recbole.model.general_recommender.lightgcn import LightGCN
    from recbole.trainer import Trainer
    from recbole.utils import init_seed, init_logger, get_trainer
    import logging

    cfg_dict = build_config_dict()

    print("Building RecBole Config...")
    config = Config(
        model="LightGCN",
        dataset=DATASET_NAME,
        config_dict=cfg_dict,
    )

    init_seed(config["seed"], config["reproducibility"])
    init_logger(config)
    logger = logging.getLogger()

    print("Creating dataset...")
    dataset = create_dataset(config)
    print(f"  Users: {dataset.user_num}, Items: {dataset.item_num}, Interactions: {dataset.inter_num}")

    print("Preparing data splits...")
    train_data, valid_data, test_data = data_preparation(config, dataset)

    print("Building LightGCN model...")
    import torch
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}")

    model = LightGCN(config, train_data.dataset).to(device)
    print(f"  Parameters: {sum(p.numel() for p in model.parameters()):,}")

    trainer = get_trainer(config["MODEL_TYPE"], config["model"])(config, model)

    print("\nStarting training...")
    best_valid_score, best_valid_result = trainer.fit(
        train_data,
        valid_data,
        saved=True,
        show_progress=True,
    )

    print("\nEvaluating on test set...")
    test_result = trainer.evaluate(test_data, load_best_model=True, show_progress=True)

    # ---- Print & save results ----
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Best validation: {best_valid_result}")
    print(f"Test result    : {test_result}")

    results_txt = OUTPUT_DIR / "lightgcn_results.txt"
    with open(results_txt, "w", encoding="utf-8") as f:
        f.write("LightGCN on MovieLens-1M\n")
        f.write("=" * 60 + "\n")
        f.write(f"Best validation score : {best_valid_score}\n")
        f.write(f"Best validation result: {best_valid_result}\n")
        f.write(f"Test result           : {test_result}\n")
    print(f"\nSaved results to: {results_txt}")


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #
def main() -> None:
    print("=" * 60)
    print("LightGCN Training on MovieLens-1M")
    print("=" * 60)

    print("\n[1/3] Preparing dataset files...")
    prepare_dataset()

    print("\n[2/3] Starting training...")
    train()

    print("\n[3/3] Done.")


if __name__ == "__main__":
    main()
