"""
Main deduplicator class for Simple SLR.

This module provides the main Deduplicator class that coordinates
deduplication across different strategies.
"""

from typing import List

from nexus.core.config import DeduplicationConfig, DeduplicationStrategy as StrategyEnum
from nexus.core.models import Document, DocumentCluster
from nexus.dedup.strategies import ConservativeStrategy, SemanticStrategy


class Deduplicator:
    """Main deduplicator class."""

    def __init__(self, config: DeduplicationConfig):
        """Initialize deduplicator with configuration.

        Args:
            config: Deduplication configuration
        """
        self.config = config
        self._strategy = self._create_strategy()
        self.removed_by_filters = 0

    def _create_strategy(self):
        """Create deduplication strategy based on configuration."""
        if self.config.strategy == StrategyEnum.CONSERVATIVE:
            return ConservativeStrategy(self.config)
        elif self.config.strategy == StrategyEnum.SEMANTIC:
            return SemanticStrategy(self.config)
        else:
            raise ValueError(f"Unknown deduplication strategy: {self.config.strategy}")

    def deduplicate(
        self, 
        documents: List[Document], 
        query_metadata: Optional[Dict[str, Any]] = None,
        progress_callback=None
    ) -> List[DocumentCluster]:
        """Deduplicate a list of documents.

        Args:
            documents: List of documents to deduplicate
            query_metadata: Optional map of QID -> {include_any, exclude_any}
            progress_callback: Optional callable(message, percentage)

        Returns:
            List of document clusters.
        """
        if not documents:
            return []

        # 1. Apply Quality Filters (Include/Exclude Keywords)
        if query_metadata:
            if progress_callback: progress_callback("Applying quality filters...", 0)
            filtered_docs, removed = self._apply_quality_filters(documents, query_metadata)
            self.removed_by_filters = removed
            documents = filtered_docs
        else:
            self.removed_by_filters = 0

        if not documents:
            return []

        # 2. Assign cluster IDs via Strategy
        clusters = self._strategy.deduplicate(documents, progress_callback=progress_callback)

        # Update documents with their cluster IDs
        for cluster in clusters:
            for doc in cluster.members:
                doc.cluster_id = cluster.cluster_id

        return clusters

    def _apply_quality_filters(
        self, documents: List[Document], query_metadata: Dict[str, Any]
    ) -> tuple[List[Document], int]:
        """Filter documents based on query-specific inclusion/exclusion criteria."""
        filtered = []
        removed = 0

        # Pre-process query_metadata for faster lookup
        # query_metadata format expected: { "Q01": {"metadata": {"include_any": [...], "exclude_any": [...]}} }
        # or simplified: { "Q01": {"include_any": [...], "exclude_any": [...]}}
        
        for doc in documents:
            # Get criteria for this document's query
            q_info = query_metadata.get(doc.query_id, {})
            # Handle both formats (full query object or just metadata)
            criteria = q_info.get("metadata", q_info) if isinstance(q_info, dict) else {}
            
            include_any = criteria.get("include_any")
            exclude_any = criteria.get("exclude_any")

            if not include_any and not exclude_any:
                filtered.append(doc)
                continue

            search_text = f"{doc.title or ''} {doc.abstract or ''} {doc.venue or ''}".lower()
            
            # Exclude check
            is_excluded = False
            if exclude_any:
                for word in exclude_any:
                    if word.lower() in search_text:
                        is_excluded = True
                        break
            
            if is_excluded:
                removed += 1
                continue

            # Include check
            if include_any:
                found = False
                for word in include_any:
                    if word.lower() in search_text:
                        found = True
                        break
                if not found:
                    removed += 1
                    continue

            filtered.append(doc)

        return filtered, removed

    def get_unique_documents(self, documents: List[Document], progress_callback=None) -> List[Document]:
        """Get unique documents by deduplicating and returning representatives.

        Args:
            documents: List of documents to deduplicate
            progress_callback: Optional callable(message, percentage)

        Returns:
            List of unique documents (one representative per cluster)
        """
        clusters = self.deduplicate(documents, progress_callback=progress_callback)
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
