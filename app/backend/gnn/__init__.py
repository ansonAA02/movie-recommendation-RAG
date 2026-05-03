"""
GNN package for NeoRAGRec.

This package contains:
- model definitions (see `model.NeoRAGRecGNN`)
- datasets and augmentation utilities for self-supervised training
- training scripts for producing movie subgraph embeddings
"""

from .model import NeoRAGRecGNN

__all__ = ["NeoRAGRecGNN"]



