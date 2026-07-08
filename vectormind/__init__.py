"""vectormind — one space, three circles.

L1 the moving focus, L2 the vault, L3 the fixed doors — all of them
queries over a single Elasticsearch index, never schema.
"""

from .circles import Categories, Focus, Recall, VectorMind
from .search import Hit, HybridSearch, RRF_K, cosine
from .space import FieldMap, HINDSIGHT_FIELDS, Space

__all__ = ["VectorMind", "Focus", "Categories", "Recall",
           "Hit", "HybridSearch", "Space", "FieldMap", "HINDSIGHT_FIELDS", "cosine", "RRF_K"]
__version__ = "0.1.0"
