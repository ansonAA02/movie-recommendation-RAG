#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export KGAT item embeddings to NeoRAGRec evaluation format"
    )
    parser.add_argument(
        "--checkpoint",
        default=str(Path(__file__).resolve().parent / "best_model.pth"),
        help="Path to KGAT state_dict checkpoint",
    )
    parser.add_argument(
        "--item-map",
        default=str(Path(__file__).resolve().parent.parent / "Kgin" / "item_id_map.json"),
        help="Path to item_id_map.json (movie_id -> remap_idx)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "Embedding"),
        help="Output directory for kgat_movie_embeddings.npy and kgat_movie_id_map.json",
    )
    parser.add_argument(
        "--weight-key",
        default="entity_user_embed.weight",
        help="State dict key for entity/user embedding matrix",
    )
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint).resolve()
    item_map_path = Path(args.item_map).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    item_map = json.loads(item_map_path.read_text(encoding="utf-8"))
    if not isinstance(item_map, dict) or not item_map:
        raise ValueError(f"Invalid item map: {item_map_path}")

    n_items = len(item_map)

    state = torch.load(str(checkpoint_path), map_location="cpu")
    if not isinstance(state, dict):
        raise ValueError(f"Checkpoint is not a state_dict: {checkpoint_path}")
    if args.weight_key not in state:
        keys = list(state.keys())
        raise KeyError(f"Missing key '{args.weight_key}'. Available keys (first 20): {keys[:20]}")

    emb = state[args.weight_key]
    if not isinstance(emb, torch.Tensor):
        raise ValueError(f"State key '{args.weight_key}' is not a tensor")
    if emb.ndim != 2:
        raise ValueError(f"Expected 2D tensor, got shape {tuple(emb.shape)}")
    if emb.shape[0] < n_items:
        raise ValueError(f"Embedding rows {emb.shape[0]} < item map size {n_items}")

    # By construction of item/entity remap, item entities are expected in [0, n_items).
    item_emb = emb[:n_items].detach().cpu().numpy().astype("float32")

    emb_out = output_dir / "kgat_movie_embeddings.npy"
    id_map_out = output_dir / "kgat_movie_id_map.json"

    np.save(emb_out, item_emb)
    id_map_out.write_text(json.dumps(item_map, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] Saved: {emb_out}")
    print(f"[OK] Saved: {id_map_out}")
    print(f"[Info] item_emb_shape={item_emb.shape}")
    print(f"[Info] n_items={n_items}")


if __name__ == "__main__":
    main()
