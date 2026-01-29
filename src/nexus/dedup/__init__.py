"""
Deduplication module for Simple SLR.

This module provides functionality for identifying and merging duplicate
documents from multiple academic databases.

Main classes:
    - Deduplicator: Main deduplication coordinator
    - ConservativeStrategy: Conservative exact-matching strategy
    - SemanticStrategy: Semantic embedding-based strategy (future)
    - HybridStrategy: Hybrid approach (future)

Example:
    >>> from nexus.core.config import DeduplicationConfig
    >>> from nexus.dedup import Deduplicator
    >>>
    >>> config = DeduplicationConfig(strategy="conservative")
    >>> deduplicator = Deduplicator(config)
    >>> clusters = deduplicator.deduplicate(documents)
    >>> unique_docs = [cluster.representative for cluster in clusters]
"""

from nexus.dedup.deduplicator import Deduplicator
from nexus.dedup.strategies import (
    ConservativeStrategy,
    DeduplicationStrategy,
    HybridStrategy,
    SemanticStrategy,
)

__all__ = [
    "Deduplicator",
    "DeduplicationStrategy",
    "ConservativeStrategy",
    "SemanticStrategy",
    "HybridStrategy",
]
