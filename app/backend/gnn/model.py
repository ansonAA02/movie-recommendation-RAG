"""
GNN models for NeoRAGRec.

This module defines the core graph encoder used to learn self-supervised
movie subgraph embeddings from the Neo4j knowledge graph.

Design goals:
- Work with heterogeneous graphs (movie / genre / director / actor).
- Combine local relational modeling (GCN / GAT) with global attention.
- Expose a clean interface for training + inference:
  - input: a PyG HeteroData subgraph (or batch of subgraphs)
  - output: a dense embedding for each target movie node.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import torch
from torch import nn, Tensor

try:
    # These imports are optional at runtime – training scripts will require them.
    from torch_geometric.nn import (
        GraphConv,
        GATConv,
        global_mean_pool,
    )
except ImportError:  # pragma: no cover - allow backend to import without PyG installed
    GraphConv = object  # type: ignore
    GATConv = object  # type: ignore

    def global_mean_pool(x, batch):  # type: ignore
        raise RuntimeError("torch_geometric is required to use NeoRAGRecGNN.")


class MultiHeadSelfAttentionBlock(nn.Module):
    """A lightweight Transformer-style block over node embeddings.

    This is applied after message passing to capture long-range interactions
    within a subgraph (e.g., between different neighbors of the same movie).
    """

    def __init__(self, dim: int, num_heads: int = 4, dropout: float = 0.1):
        super().__init__()
        self.attn = nn.MultiheadAttention(dim, num_heads, dropout=dropout, batch_first=True)
        self.ffn = nn.Sequential(
            nn.Linear(dim, dim * 4),
            nn.ReLU(),
            nn.Linear(dim * 4, dim),
        )
        self.norm1 = nn.LayerNorm(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: Tensor) -> Tensor:
        # x: (batch, seq_len, dim)
        attn_out, _ = self.attn(x, x, x)
        x = self.norm1(x + self.dropout(attn_out))

        ffn_out = self.ffn(x)
        x = self.norm2(x + self.dropout(ffn_out))
        return x


class NeoRAGRecGNN(nn.Module):
    """Enhanced Graph Transformer encoder for movie subgraph embeddings.

    High-level idea (aligned with proposal):
    - Heterogeneous message passing with a mix of GCNConv and GATConv.
    - Optional global self-attention over the movie-centric subgraph.
    - Self-supervised training with contrastive objectives is implemented
      separately (e.g., in train_gnn.py), using this encoder as backbone.

    Expected input (PyTorch Geometric style):
    - data: HeteroData containing (at least) node types:
        "movie", "genre", "director", "actor"
      and edge types such as:
        ("movie", "HAS_GENRE", "genre"),
        ("movie", "DIRECTED_BY", "director"),
        ("movie", "ACTED_IN", "actor"), ...
    - Each node type should have:
        data[node_type].x: Tensor [num_nodes, in_channels[node_type]]
    - Batch information:
        data["movie"].batch: Tensor [num_movie_nodes]  (for pooling)

    Forward interface:
    --------
    def forward(
        self,
        data: "HeteroData",
        return_node_embeddings: bool = False,
    ) -> Tuple[Tensor, Optional[Dict[str, Tensor]]]:
        \"\"\"Encode a (batched) movie-centric subgraph.

        Returns:
            movie_emb: Tensor [num_movies_in_batch, emb_dim]
            node_embs (optional): dict[node_type] -> Tensor of node embeddings
        \"\"\"
    """

    def __init__(
        self,
        in_dims: Dict[str, int],
        hidden_dim: int = 128,
        out_dim: int = 256,
        num_gnn_layers: int = 2,
        num_attention_layers: int = 1,
        num_heads: int = 4,
        dropout: float = 0.1,
    ):
        """
        Args:
            in_dims: Mapping from node_type to input feature dimension.
                     Example: {"movie": 64, "genre": 32, "director": 32, "actor": 32}
            hidden_dim: Hidden size used inside the GNN.
            out_dim: Final embedding dimension for movie nodes.
            num_gnn_layers: Number of hetero GNN layers (GCN/GAT mix).
            num_attention_layers: How many self-attention blocks to apply.
            num_heads: Attention heads for GAT and Transformer block.
            dropout: Dropout rate.
        """
        super().__init__()

        self.hidden_dim = hidden_dim
        self.out_dim = out_dim

        # 1) Type-specific input projections to a common hidden_dim
        self.input_proj = nn.ModuleDict(
            {
                node_type: nn.Linear(in_dim, hidden_dim)
                for node_type, in_dim in in_dims.items()
            }
        )

        # 2) Heterogeneous GNN stack (manual message passing per relation)
        # 我們顯式為每種關係維護一組 conv，並在 forward 中手動做 message passing，
        # 這樣可以避免 HeteroConv 對 add_self_loops / bipartite 的限制，同時更直觀。
        self.num_gnn_layers = num_gnn_layers
        self.conv_has_genre_layers = nn.ModuleList()
        self.conv_directed_by_layers = nn.ModuleList()
        self.conv_starred_by_layers = nn.ModuleList()

        for _ in range(num_gnn_layers):
            self.conv_has_genre_layers.append(
                GATConv(
                    in_channels=hidden_dim,
                    out_channels=hidden_dim,
                    heads=num_heads,
                    concat=False,
                    dropout=dropout,
                    add_self_loops=False,
                )
            )
            # 使用 GraphConv 支援 bipartite message passing（Person -> Movie）
            self.conv_directed_by_layers.append(
                GraphConv(
                    in_channels=hidden_dim,
                    out_channels=hidden_dim,
                )
            )
            self.conv_starred_by_layers.append(
                GATConv(
                    in_channels=hidden_dim,
                    out_channels=hidden_dim,
                    heads=num_heads,
                    concat=False,
                    dropout=dropout,
                    add_self_loops=False,
                )
            )

        self.gnn_norms = nn.ModuleList(
            [nn.ModuleDict() for _ in range(num_gnn_layers)]
        )
        for layer_idx in range(num_gnn_layers):
            for node_type in in_dims.keys():
                self.gnn_norms[layer_idx][node_type] = nn.LayerNorm(hidden_dim)

        self.dropout = nn.Dropout(dropout)
        self.activation = nn.ReLU()

        # 3) Optional Transformer-style self-attention over movie nodes
        self.attention_layers = nn.ModuleList(
            [
                MultiHeadSelfAttentionBlock(hidden_dim, num_heads=num_heads, dropout=dropout)
                for _ in range(num_attention_layers)
            ]
        )

        # 4) Output projection for movie embeddings (representation for downstream tasks)
        self.output_proj = nn.Sequential(
            nn.Linear(hidden_dim, out_dim),
            nn.LayerNorm(out_dim),
        )

        # 5) Projection head for contrastive learning (SimCLR-style MLP)
        # This maps the representation into a space more suitable for InfoNCE,
        # while keeping movie_emb (after output_proj) for downstream usage.
        self.projection_head = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
        )

    def forward(
        self,
        data,  # "HeteroData"
        return_node_embeddings: bool = False,
        return_projection: bool = False,
    ) -> Tuple[Tensor, Optional[Dict[str, Tensor]]]:
        """Encode a (batched) movie-centric subgraph into dense embeddings.

        Args:
            data: A PyG HeteroData object with node features and edge_index.
            return_node_embeddings: If True, also return per-node-type embeddings.

        Returns:
            movie_emb: Tensor [num_movies_in_batch, out_dim]
            node_embs (optional): dict[node_type] -> Tensor [num_nodes_of_type, hidden_dim]
        """
        x_dict: Dict[str, Tensor] = {}

        # 1) Project raw features to common hidden_dim
        for node_type, x in data.x_dict.items():
            if node_type not in self.input_proj:
                raise KeyError(f"Missing input_proj for node type: {node_type}")
            x_dict[node_type] = self.input_proj[node_type](x)

        # 2) Heterogeneous GNN layers（手動 message passing）
        for layer_idx in range(self.num_gnn_layers):
            # 殘差初始化：先複製當前節點表示
            new_x_dict: Dict[str, Tensor] = {
                node_type: x.clone() for node_type, x in x_dict.items()
            }

            # (a) Genre -> Movie via HAS_GENRE^(-1)
            edge_type_hg = ("movie", "HAS_GENRE", "genre")
            if edge_type_hg in data.edge_index_dict:
                edge_index = data.edge_index_dict[edge_type_hg]
                if edge_index.numel() > 0:
                    # 反向邊：genre -> movie
                    edge_index_rev = torch.stack(
                        [edge_index[1], edge_index[0]], dim=0
                    )
                    out_movie_from_genre = self.conv_has_genre_layers[layer_idx](
                        (x_dict["genre"], x_dict["movie"]), edge_index_rev
                    )
                    new_x_dict["movie"] = new_x_dict["movie"] + out_movie_from_genre

            # (b) Person(director) -> Movie via DIRECTED_BY^(-1)
            edge_type_dir = ("movie", "DIRECTED_BY", "person")
            if edge_type_dir in data.edge_index_dict:
                edge_index = data.edge_index_dict[edge_type_dir]
                if edge_index.numel() > 0:
                    edge_index_rev = torch.stack(
                        [edge_index[1], edge_index[0]], dim=0
                    )
                    out_movie_from_dir = self.conv_directed_by_layers[layer_idx](
                        (x_dict["person"], x_dict["movie"]), edge_index_rev
                    )
                    new_x_dict["movie"] = new_x_dict["movie"] + out_movie_from_dir

            # (c) Person(actor) -> Movie via STARRED_BY^(-1)
            edge_type_star = ("movie", "STARRED_BY", "person")
            if edge_type_star in data.edge_index_dict:
                edge_index = data.edge_index_dict[edge_type_star]
                if edge_index.numel() > 0:
                    edge_index_rev = torch.stack(
                        [edge_index[1], edge_index[0]], dim=0
                    )
                    out_movie_from_actor = self.conv_starred_by_layers[layer_idx](
                        (x_dict["person"], x_dict["movie"]), edge_index_rev
                    )
                    new_x_dict["movie"] = new_x_dict["movie"] + out_movie_from_actor

            # 更新節點表示並加上非線性、LayerNorm
            x_dict = new_x_dict
            for node_type, x in x_dict.items():
                x = self.activation(x)
                x = self.dropout(x)
                x = self.gnn_norms[layer_idx][node_type](x)
                x_dict[node_type] = x

        # 3) (Optional) self-attention over movie nodes
        movie_x = x_dict["movie"]

        # data["movie"].batch should exist for batched subgraphs
        movie_batch: Optional[Tensor] = getattr(data["movie"], "batch", None)
        if movie_batch is None:
            # If no batch info, treat entire set as a single sequence
            seq = movie_x.unsqueeze(0)  # [1, num_movies, hidden_dim]
            for attn in self.attention_layers:
                seq = attn(seq)
            movie_x = seq.squeeze(0)
        else:
            # Group movie nodes by batch index and apply attention within each group.
            # To avoid heavy Python loops, we approximate by using global_mean_pool
            # as a simple pooling; training script can later refine this if needed.
            # (Alternative: pack padded sequences per batch_id.)
            pass  # For now we skip extra attention when batch info is present.

        # 4) Project to final movie embedding
        movie_emb = self.output_proj(movie_x)
        proj = self.projection_head(movie_emb)

        if return_projection:
            # 用於訓練：同時返回表徵和投影向量
            if return_node_embeddings:
                return movie_emb, proj, x_dict
            return movie_emb, proj, None

        if return_node_embeddings:
            return movie_emb, x_dict
        return movie_emb, None


__all__ = [
    "NeoRAGRecGNN",
    "MultiHeadSelfAttentionBlock",
]


