"""
Training script skeleton for NeoRAGRecGNN.

This script wires together:
- a heterogeneous graph (HeteroData) exported from Neo4j,
- KGSubgraphPairDataset for self-supervised contrastive training,
- NeoRAGRecGNN encoder,
- InfoNCE-style loss to learn 256-d movie embeddings.

You are expected to:
- implement/plug in your own graph export pipeline (producing HeteroData),
- tune hyperparameters (batch size, epochs, temperature, etc.),
- run this script to generate `movie_subgraph_embeddings.npy`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import torch
from torch import Tensor
from torch import nn
from torch.optim import Adam

try:
    from torch_geometric.data import HeteroData
    from torch_geometric.data.storage import BaseStorage
    from torch_geometric.loader import DataLoader
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "torch_geometric is required to run GNN training. "
        "Install it in your backend environment."
    ) from exc

try:
    # PyTorch 2.6+ 安全反序列化機制：顯式允許 HeteroData 相關的 BaseStorage
    from torch.serialization import add_safe_globals

    add_safe_globals([BaseStorage])
except Exception:
    # 舊版 PyTorch 沒有此 API，就忽略，維持舊行為
    pass

from .model import NeoRAGRecGNN
from .dataset import KGSubgraphPairDataset, build_movie_node_indices


def contrastive_loss(z1: Tensor, z2: Tensor, temperature: float = 0.2) -> Tensor:
    """InfoNCE loss between two batches of embeddings.

    Args:
        z1, z2: [batch_size, dim], positive pairs are (z1[i], z2[i]).
        temperature: softmax temperature.
    """
    # Normalize
    z1 = nn.functional.normalize(z1, dim=-1)
    z2 = nn.functional.normalize(z2, dim=-1)

    batch_size = z1.size(0)

    # Compute similarity matrix: [2B, 2B]
    reps = torch.cat([z1, z2], dim=0)
    sim_matrix = reps @ reps.t()  # cosine since normalized
    sim_matrix = sim_matrix / temperature

    # Mask out self-similarity
    mask = torch.eye(2 * batch_size, dtype=torch.bool, device=sim_matrix.device)
    sim_matrix = sim_matrix.masked_fill(mask, float("-inf"))

    # For each sample i, its positive index j is i+B (mod 2B)
    labels = torch.arange(2 * batch_size, device=z1.device)
    labels = (labels + batch_size) % (2 * batch_size)

    loss = nn.functional.cross_entropy(sim_matrix, labels)
    return loss


def build_in_dims(data: HeteroData) -> Dict[str, int]:
    """Infer input feature dims from HeteroData.x_dict."""
    in_dims: Dict[str, int] = {}
    for node_type, x in data.x_dict.items():
        in_dims[node_type] = x.size(-1)
    return in_dims


def train_epoch(
    model: NeoRAGRecGNN,
    loader: DataLoader,
    optimizer: Adam,
    device: torch.device,
    temperature: float,
) -> float:
    model.train()
    total_loss = 0.0

    for batch_idx, (g1, g2) in enumerate(loader):
        g1 = g1.to(device)
        g2 = g2.to(device)

        # 使用 SimCLR-style projection head:
        # movie_emb 用於下游，proj 用於 InfoNCE 對比學習。
        _, proj1, _ = model(g1, return_projection=True)
        _, proj2, _ = model(g2, return_projection=True)

        # Here we assume each subgraph contains exactly one anchor movie,
        # and model returns embeddings in the same order.
        loss = contrastive_loss(proj1, proj2, temperature=temperature)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += float(loss.item())

    return total_loss / max(len(loader), 1)


@torch.no_grad()
def export_movie_embeddings(
    model: NeoRAGRecGNN,
    data: HeteroData,
    device: torch.device,
    output_dir: Path,
    movie_id_map_path: Path,
) -> None:
    """Run encoder over all movie nodes and save embeddings + id map."""
    model.eval()
    data = data.to(device)

    movie_emb, _ = model(data)
    movie_emb = movie_emb.cpu().numpy()

    # Load movie id map (should be produced by your Neo4j export script)
    with movie_id_map_path.open("r", encoding="utf-8") as f:
        movie_id_map = json.load(f)  # dict: movie_id(str or int) -> node_index

    # Invert map to ensure correct ordering if needed
    index_to_movie_id = {int(v): int(k) for k, v in movie_id_map.items()}

    # Reorder embeddings so that row i corresponds to movie_id index_to_movie_id[i]
    max_index = max(index_to_movie_id.keys())
    if max_index + 1 != movie_emb.shape[0]:
        # Basic sanity check; you may need to adapt this if your mapping differs
        raise ValueError(
            f"Embedding rows ({movie_emb.shape[0]}) do not match id map max index ({max_index})."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    emb_path = output_dir / "movie_subgraph_embeddings.npy"
    np.save(emb_path, movie_emb)

    # Also save an ordered list of movie IDs for convenience
    ordered_movie_ids = [index_to_movie_id[i] for i in range(movie_emb.shape[0])]
    ids_path = output_dir / "movie_subgraph_id_map.json"
    with ids_path.open("w", encoding="utf-8") as f:
        json.dump(ordered_movie_ids, f, ensure_ascii=False, indent=2)

    print(f"Saved movie subgraph embeddings to: {emb_path}")
    print(f"Saved movie id list to: {ids_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train NeoRAGRecGNN on KG subgraphs")
    parser.add_argument(
        "--data-path",
        type=str,
        required=True,
        help="Path to a saved HeteroData object (e.g., data_kg.pt).",
    )
    parser.add_argument(
        "--movie-id-map",
        type=str,
        required=True,
        help="Path to movie_id -> node_index JSON produced by Neo4j export.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="app/backend/embeddings",
        help="Directory to store trained embeddings.",
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--out-dim", type=int, default=256)
    parser.add_argument("--num-gnn-layers", type=int, default=2)
    parser.add_argument("--num-attn-layers", type=int, default=1)
    parser.add_argument(
        "--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    device = torch.device(args.device)
    output_dir = Path(args.output_dir)

    # 1) Load heterogeneous graph (preprocessed from Neo4j)
    # PyTorch 2.6+ 默認 weights_only=True，會導致自定義類型（如 HeteroData）反序列化失敗。
    # 這裡我們明確設定 weights_only=False，因為 data_kg.pt 是你本地生成且可信的檔案。
    try:
        data: HeteroData = torch.load(args.data_path, weights_only=False)
    except TypeError:
        # 舊版 PyTorch 沒有 weights_only 參數時退回舊用法
        data: HeteroData = torch.load(args.data_path)

    # 2) Build movie node indices for contrastive anchors
    movie_indices = build_movie_node_indices(data)

    # 3) Dataset & DataLoader
    dataset = KGSubgraphPairDataset(
        data=data,
        movie_node_indices=movie_indices,
        num_hops=2,
        device=device,
    )

    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
    )

    # 4) Build model
    in_dims = build_in_dims(data)
    model = NeoRAGRecGNN(
        in_dims=in_dims,
        hidden_dim=args.hidden_dim,
        out_dim=args.out_dim,
        num_gnn_layers=args.num_gnn_layers,
        num_attention_layers=args.num_attn_layers,
    ).to(device)

    optimizer = Adam(model.parameters(), lr=args.lr)

    # 5) Training loop
    for epoch in range(1, args.epochs + 1):
        loss = train_epoch(
            model=model,
            loader=loader,
            optimizer=optimizer,
            device=device,
            temperature=args.temperature,
        )
        print(f"Epoch {epoch:03d} | Loss = {loss:.4f}")

    # 6) Export embeddings
    movie_id_map_path = Path(args.movie_id_map)
    export_movie_embeddings(
        model=model,
        data=data,
        device=device,
        output_dir=output_dir,
        movie_id_map_path=movie_id_map_path,
    )


if __name__ == "__main__":
    main()


