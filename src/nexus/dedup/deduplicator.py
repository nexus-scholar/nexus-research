"""
Main deduplicator class for Simple SLR.

This module provides the main Deduplicator class that coordinates
deduplication across different strategies.
"""

from typing import List

from nexus.core.config import DeduplicationConfig, DeduplicationStrategy as StrategyEnum
from nexus.core.models import Document, DocumentCluster
from nexus.dedup.strategies import ConservativeStrategy, HybridStrategy, SemanticStrategy


class Deduplicator:
    """Main deduplicator class.

    This class coordinates deduplication of documents using various strategies.
    It supports conservative (exact matching), semantic (embedding-based), and
    hybrid approaches.

    Example:
        >>> from nexus.core.config import DeduplicationConfig, DeduplicationStrategy
        >>> from nexus.dedup import Deduplicator
        >>>
        >>> config = DeduplicationConfig(strategy=DeduplicationStrategy.CONSERVATIVE)
        >>> deduplicator = Deduplicator(config)
        >>> clusters = deduplicator.deduplicate(documents)
    """

    def __init__(self, config: DeduplicationConfig):
        """Initialize deduplicator with configuration.

        Args:
            config: Deduplication configuration
        """
        self.config = config
        self._strategy = self._create_strategy()

    def _create_strategy(self):
        """Create deduplication strategy based on configuration.

        Returns:
            Strategy instance

        Raises:
            ValueError: If strategy is not recognized
        """
        if self.config.strategy == StrategyEnum.CONSERVATIVE:
            return ConservativeStrategy(self.config)
        elif self.config.strategy == StrategyEnum.SEMANTIC:
            return SemanticStrategy(self.config)
        elif self.config.strategy == StrategyEnum.HYBRID:
            return HybridStrategy(self.config)
        else:
            raise ValueError(f"Unknown deduplication strategy: {self.config.strategy}")

    def deduplicate(self, documents: List[Document]) -> List[DocumentCluster]:
        """Deduplicate a list of documents.

        Args:
            documents: List of documents to deduplicate

        Returns:
            List of document clusters, where each cluster contains documents
            identified as duplicates. Each cluster has a representative document
            and aggregated metadata.

        Example:
            >>> clusters = deduplicator.deduplicate(documents)
            >>> unique_docs = [cluster.representative for cluster in clusters]
            >>> print(f"Found {len(unique_docs)} unique documents from {len(documents)}")
        """
        if not documents:
            return []

        # Assign cluster IDs to documents
        clusters = self._strategy.deduplicate(documents)

        # Update documents with their cluster IDs
        for cluster in clusters:
            for doc in cluster.members:
                doc.cluster_id = cluster.cluster_id

        return clusters

    def get_unique_documents(self, documents: List[Document]) -> List[Document]:
        """Get unique documents by deduplicating and returning representatives.

        This is a convenience method that deduplicates and returns only the
        representative document from each cluster.

        Args:
            documents: List of documents to deduplicate

        Returns:
            List of unique documents (one representative per cluster)

        Example:
            >>> unique_docs = deduplicator.get_unique_documents(documents)
            >>> print(f"Reduced {len(documents)} to {len(unique_docs)} unique documents")
        """
        clusters = self.deduplicate(documents)
        return [cluster.representative for cluster in clusters]

    def get_statistics(self, clusters: List[DocumentCluster]) -> dict:
        """Get deduplication statistics.

        Args:
            clusters: List of document clusters

        Returns:
            Dictionary with statistics about the deduplication results

        Example:
            >>> clusters = deduplicator.deduplicate(documents)
            >>> stats = deduplicator.get_statistics(clusters)
            >>> print(f"Duplicate rate: {stats['duplicate_rate']:.1%}")
        """
        total_documents = sum(cluster.size for cluster in clusters)
        unique_documents = len(clusters)
        duplicates = total_documents - unique_documents

        # Count clusters by size
        cluster_sizes = {}
        for cluster in clusters:
            size = cluster.size
            cluster_sizes[size] = cluster_sizes.get(size, 0) + 1

        # Count by provider
        provider_counts = {}
        for cluster in clusters:
            for provider, count in cluster.provider_counts.items():
                provider_counts[provider] = provider_counts.get(provider, 0) + count

        return {
            "total_documents": total_documents,
            "unique_documents": unique_documents,
            "duplicates": duplicates,
            "duplicate_rate": duplicates / total_documents if total_documents > 0 else 0.0,
            "avg_cluster_size": total_documents / unique_documents if unique_documents > 0 else 0.0,
            "max_cluster_size": max((c.size for c in clusters), default=0),
            "cluster_size_distribution": cluster_sizes,
            "provider_counts": provider_counts,
            "strategy": self.config.strategy.value,
        }
