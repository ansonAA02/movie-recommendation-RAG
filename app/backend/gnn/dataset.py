"""
Datasets and augmentations for NeoRAGRec GNN training.

This module is intentionally conservative and focuses on providing a clean
interface. You are expected to refine the subgraph extraction and
augmentation strategies as needed for experiments.
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, List

import torch
from torch import Tensor
from torch.utils.data import Dataset

try:
    from torch_geometric.data import HeteroData
except ImportError:  # pragma: no cover
    HeteroData = object  # type: ignore


class KGSubgraphPairDataset(Dataset):
    """Return two augmented views of the same movie-centric subgraph.

    This is designed for self-supervised contrastive training (InfoNCE):
    - For each movie node, we construct a k-hop subgraph around it.
    - For each subgraph we apply two independent augmentations -> (view1, view2).

    Current implementation (v1):
    - For each anchor movie, we build a small 1-hop ego-subgraph consisting of:
        * the anchor movie node
        * its genres (HAS_GENRE neighbors)
        * its directors/actors (DIRECTED_BY/STARRED_BY neighbors)
    - We then create two augmented views of this subgraph via:
        * random edge dropout
        * random node feature masking for non-movie nodes

    This already避免了「整張大圖 + view1=view2」的退化情況，
    之後若需要，可以再擴展為真正的 k-hop 子圖。
    """

    def __init__(
        self,
        data: "HeteroData",
        movie_node_indices: Tensor,
        num_hops: int = 2,
        device: Optional[torch.device] = None,
    ):
        """
        Args:
            data: Full heterogeneous graph exported from Neo4j.
            movie_node_indices: 1D tensor of indices for movie nodes to be used
                                as contrastive anchors.
            num_hops: Intended k-hop radius for subgraph extraction (TODO).
            device: Optionally move returned subgraphs to this device.
        """
        super().__init__()
        self.data = data
        self.movie_node_indices = movie_node_indices.long()
        self.num_hops = num_hops
        self.device = device

    def __len__(self) -> int:
        return self.movie_node_indices.numel()

    def __getitem__(self, idx: int) -> Tuple["HeteroData", "HeteroData"]:
        movie_idx = int(self.movie_node_indices[idx])

        # 1) 構建以該電影為中心的局部子圖（只包含這一個 movie 節點）
        base_subgraph = self._build_movie_ego_subgraph(movie_idx)

        # 2) 建立兩個不同的增強視角
        subgraph_1 = self._augment_subgraph(base_subgraph)
        subgraph_2 = self._augment_subgraph(base_subgraph)

        if self.device is not None:
            subgraph_1 = subgraph_1.to(self.device)
            subgraph_2 = subgraph_2.to(self.device)

        return subgraph_1, subgraph_2

    # ------------------------------------------------------------------
    #  子圖構建與增強
    # ------------------------------------------------------------------
    def _build_movie_ego_subgraph(self, movie_idx: int) -> "HeteroData":
        """Build a 1-hop ego-subgraph around a given movie.

        Node types included:
        - movie: only the anchor movie (index 0 in the subgraph)
        - genre: all genres directly connected via HAS_GENRE
        - person: all persons connected via DIRECTED_BY or STARRED_BY

        This keeps每個樣本只含一個 movie 節點，方便與 DataLoader 批次化，
        也讓 InfoNCE 學到「以該電影為中心的局部結構與語意」。
        """
        full: HeteroData = self.data
        sub = HeteroData()

        # --- collect 1-hop neighbors from edge_index_dict ---
        movie_idx_t = torch.tensor([movie_idx], dtype=torch.long)

        # HAS_GENRE: (movie -> genre)
        genre_neighbors: List[int] = []
        if ("movie", "HAS_GENRE", "genre") in full.edge_index_dict:
            edge_hg = full[("movie", "HAS_GENRE", "genre")].edge_index
            mask = edge_hg[0] == movie_idx
            if mask.any():
                genre_neighbors = edge_hg[1, mask].unique().tolist()

        # DIRECTED_BY: (movie -> person)
        dir_persons: List[int] = []
        if ("movie", "DIRECTED_BY", "person") in full.edge_index_dict:
            edge_dir = full[("movie", "DIRECTED_BY", "person")].edge_index
            mask = edge_dir[0] == movie_idx
            if mask.any():
                dir_persons = edge_dir[1, mask].unique().tolist()

        # STARRED_BY: (movie -> person)
        act_persons: List[int] = []
        if ("movie", "STARRED_BY", "person") in full.edge_index_dict:
            edge_star = full[("movie", "STARRED_BY", "person")].edge_index
            mask = edge_star[0] == movie_idx
            if mask.any():
                act_persons = edge_star[1, mask].unique().tolist()

        # unique person set
        all_persons = sorted(set(dir_persons + act_persons))
        genre_neighbors = sorted(set(genre_neighbors))

        # --- build node index mappings (old -> new) ---
        movie_old_to_new = {int(movie_idx): 0}

        genre_old_to_new: Dict[int, int] = {
            int(g): i for i, g in enumerate(genre_neighbors)
        }
        person_old_to_new: Dict[int, int] = {
            int(p): i for i, p in enumerate(all_persons)
        }

        # --- slice node features ---
        sub["movie"].x = full["movie"].x[movie_idx_t]

        if genre_neighbors:
            g_idx = torch.tensor(genre_neighbors, dtype=torch.long)
            sub["genre"].x = full["genre"].x[g_idx]
        else:
            sub["genre"].x = torch.zeros(
                (0, full["genre"].x.size(1)), dtype=full["genre"].x.dtype
            )

        if all_persons:
            p_idx = torch.tensor(all_persons, dtype=torch.long)
            sub["person"].x = full["person"].x[p_idx]
        else:
            sub["person"].x = torch.zeros(
                (0, full["person"].x.size(1)), dtype=full["person"].x.dtype
            )

        # --- build edges in local index space ---
        # movie index is always 0 in subgraph
        movie_local_idx = 0

        # HAS_GENRE edges
        if genre_neighbors:
            src = torch.full(
                (len(genre_neighbors),), movie_local_idx, dtype=torch.long
            )
            dst = torch.arange(len(genre_neighbors), dtype=torch.long)
            sub[("movie", "HAS_GENRE", "genre")].edge_index = torch.stack(
                [src, dst], dim=0
            )

        # DIRECTED_BY edges
        if dir_persons:
            dst_local = torch.tensor(
                [person_old_to_new[int(p)] for p in dir_persons], dtype=torch.long
            )
            src = torch.full((len(dst_local),), movie_local_idx, dtype=torch.long)
            sub[("movie", "DIRECTED_BY", "person")].edge_index = torch.stack(
                [src, dst_local], dim=0
            )

        # STARRED_BY edges
        if act_persons:
            dst_local = torch.tensor(
                [person_old_to_new[int(p)] for p in act_persons], dtype=torch.long
            )
            src = torch.full((len(dst_local),), movie_local_idx, dtype=torch.long)
            sub[("movie", "STARRED_BY", "person")].edge_index = torch.stack(
                [src, dst_local], dim=0
            )

        return sub

    @staticmethod
    def _augment_subgraph(
        subgraph: "HeteroData",
        edge_drop_prob: float = 0.2,
        feature_mask_prob: float = 0.1,
    ) -> "HeteroData":
        """Apply simple random augmentations to a subgraph.

        - Randomly drop a fraction of edges for each relation type.
        - Randomly zero-out some node features (genre/person) to simulate noise.
        """
        sg = subgraph.clone()

        # Edge dropout
        for edge_type in list(sg.edge_index_dict.keys()):
            edge_index = sg[edge_type].edge_index
            if edge_index.numel() == 0:
                continue
            num_edges = edge_index.size(1)
            keep_mask = torch.rand(num_edges) > edge_drop_prob
            # 保證至少保留一條邊（如果原本有）
            if not keep_mask.any():
                keep_mask[torch.randint(0, num_edges, (1,))] = True
            sg[edge_type].edge_index = edge_index[:, keep_mask]

        # Feature masking（不動 movie，自然保留 anchor 表示）
        for node_type in ["genre", "person"]:
            if node_type not in sg.node_types:
                continue
            x = sg[node_type].x
            if x.numel() == 0:
                continue
            num_nodes = x.size(0)
            mask = torch.rand(num_nodes) < feature_mask_prob
            if mask.any():
                x[mask] = 0.0
                sg[node_type].x = x

        return sg


def build_movie_node_indices(data: "HeteroData") -> Tensor:
    """Utility to build a default list of movie node indices.

    Here we simply take all movie nodes (0..N-1). You can later customize
    this to sample only well-connected / frequent movies.
    """
    num_movies = data["movie"].x.size(0)
    return torch.arange(num_movies, dtype=torch.long)


__all__ = [
    "KGSubgraphPairDataset",
    "build_movie_node_indices",
]



