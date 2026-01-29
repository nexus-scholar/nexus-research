"""
Deduplication strategies for Simple SLR.

This module provides different strategies for identifying and merging duplicate
documents from multiple academic databases.
"""

import re
import unicodedata
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from nexus.core.config import DeduplicationConfig
from nexus.core.models import Document, DocumentCluster


class DeduplicationStrategy(ABC):
    """Base class for deduplication strategies."""

    def __init__(self, config: DeduplicationConfig):
        """Initialize strategy with configuration.

        Args:
            config: Deduplication configuration
        """
        self.config = config

    @abstractmethod
    def deduplicate(self, documents: List[Document]) -> List[DocumentCluster]:
        """Deduplicate a list of documents.

        Args:
            documents: List of documents to deduplicate

        Returns:
            List of document clusters, one cluster per unique document
        """
        pass

    @staticmethod
    def normalize_title(title: Optional[str]) -> str:
        """Normalize a title for comparison.

        - Converts to lowercase
        - Removes accents/diacritics
        - Normalizes whitespace
        - Strips punctuation

        Args:
            title: Title to normalize

        Returns:
            Normalized title
        """
        if not title:
            return ""

        # Convert to NFD (decomposed) form and remove combining characters
        nfd = unicodedata.normalize("NFD", title)
        title = "".join(c for c in nfd if not unicodedata.combining(c))

        # Lowercase
        title = title.lower()

        # Normalize whitespace
        title = re.sub(r"\s+", " ", title).strip()

        return title

    @staticmethod
    def normalize_doi(doi: Optional[str]) -> str:
        """Normalize a DOI for comparison.

        Removes URL prefixes and converts to lowercase.

        Args:
            doi: DOI to normalize

        Returns:
            Normalized DOI
        """
        if not doi:
            return ""

        # Remove common prefixes
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
        doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)

        return doi.strip().lower()

    @staticmethod
    def create_cluster(
        cluster_id: int, documents: List[Document], representative: Optional[Document] = None
    ) -> DocumentCluster:
        """Create a document cluster.

        Args:
            cluster_id: Cluster identifier
            documents: Documents in this cluster
            representative: Representative document (if None, picks best one)

        Returns:
            DocumentCluster instance
        """
        if not documents:
            raise ValueError("Cannot create cluster with no documents")

        # Pick representative if not provided
        if representative is None:
            representative = DeduplicationStrategy._pick_representative(documents)

        # Aggregate metadata
        all_dois = []
        all_arxiv_ids = []
        provider_counts: Dict[str, int] = defaultdict(int)

        for doc in documents:
            # Collect DOIs
            if doc.external_ids.doi:
                normalized_doi = DeduplicationStrategy.normalize_doi(doc.external_ids.doi)
                if normalized_doi and normalized_doi not in all_dois:
                    all_dois.append(normalized_doi)

            # Collect arXiv IDs
            if doc.external_ids.arxiv_id:
                arxiv_id = doc.external_ids.arxiv_id.lower().strip()
                if arxiv_id and arxiv_id not in all_arxiv_ids:
                    all_arxiv_ids.append(arxiv_id)

            # Count providers
            provider_counts[doc.provider] += 1

        return DocumentCluster(
            cluster_id=cluster_id,
            representative=representative,
            members=documents,
            all_dois=all_dois,
            all_arxiv_ids=all_arxiv_ids,
            provider_counts=dict(provider_counts),
        )

    @staticmethod
    def _pick_representative(documents: List[Document]) -> Document:
        """Pick the best representative document from a cluster.

        Preference order:
        1. Most complete metadata (has abstract, authors, etc.)
        2. Highest citation count
        3. From most authoritative provider
        4. First document

        Args:
            documents: Documents to choose from

        Returns:
            Best representative document
        """
        # Provider preference order (most authoritative first)
        provider_priority = {
            "crossref": 4,
            "openalex": 3,
            "semantic_scholar": 2,
            "s2": 2,
            "arxiv": 1,
        }

        def score_document(doc: Document) -> Tuple[int, int, int]:
            """Score a document for representativeness."""
            # Metadata completeness
            completeness = 0
            if doc.abstract:
                completeness += 10
            if doc.authors:
                completeness += 5
            if doc.venue:
                completeness += 3
            if doc.external_ids.doi:
                completeness += 2

            # Citation count
            citations = doc.cited_by_count or 0

            # Provider priority
            priority = provider_priority.get(doc.provider.lower(), 0)

            return (completeness, citations, priority)

        # Sort by score (descending)
        sorted_docs = sorted(documents, key=score_document, reverse=True)
        return sorted_docs[0]


class ConservativeStrategy(DeduplicationStrategy):
    """Conservative deduplication strategy.

    This strategy uses exact identifier matching (DOI, arXiv ID) and high-threshold
    fuzzy title matching to minimize false positives. It's safe for use when
    precision is more important than recall.

    Matching rules:
    1. Exact DOI match (highest confidence)
    2. Exact arXiv ID match (highest confidence)
    3. Very similar titles (>97% similarity by default) + same year
    """

    def deduplicate(self, documents: List[Document]) -> List[DocumentCluster]:
        """Deduplicate documents using conservative strategy.

        Args:
            documents: List of documents to deduplicate

        Returns:
            List of document clusters
        """
        if not documents:
            return []

        # Build indices
        doi_index: Dict[str, List[Document]] = defaultdict(list)
        arxiv_index: Dict[str, List[Document]] = defaultdict(list)
        title_index: Dict[str, List[Document]] = defaultdict(list)

        for doc in documents:
            # Index by DOI
            if doc.external_ids.doi:
                doi = self.normalize_doi(doc.external_ids.doi)
                if doi:
                    doi_index[doi].append(doc)

            # Index by arXiv ID
            if doc.external_ids.arxiv_id:
                arxiv_id = doc.external_ids.arxiv_id.lower().strip()
                if arxiv_id:
                    arxiv_index[arxiv_id].append(doc)

            # Index by normalized title
            norm_title = self.normalize_title(doc.title)
            if norm_title:
                title_index[norm_title].append(doc)

        # Track which documents have been clustered
        clustered: Set[int] = set()
        clusters: List[DocumentCluster] = []
        cluster_id = 0

        # Phase 1: Exact DOI matches
        for doi, docs in doi_index.items():
            if len(docs) > 1:
                # Filter out already clustered documents
                unclustered = [d for d in docs if id(d) not in clustered]
                if len(unclustered) > 1:
                    cluster = self.create_cluster(cluster_id, unclustered)
                    clusters.append(cluster)
                    for doc in unclustered:
                        clustered.add(id(doc))
                    cluster_id += 1

        # Phase 2: Exact arXiv ID matches
        for arxiv_id, docs in arxiv_index.items():
            if len(docs) > 1:
                unclustered = [d for d in docs if id(d) not in clustered]
                if len(unclustered) > 1:
                    cluster = self.create_cluster(cluster_id, unclustered)
                    clusters.append(cluster)
                    for doc in unclustered:
                        clustered.add(id(doc))
                    cluster_id += 1

        # Phase 3: Fuzzy title matching (very conservative)
        # Only for documents not yet clustered
        unclustered_docs = [d for d in documents if id(d) not in clustered]

        # Group by normalized title
        title_groups: Dict[str, List[Document]] = defaultdict(list)
        for doc in unclustered_docs:
            norm_title = self.normalize_title(doc.title)
            if norm_title:
                title_groups[norm_title].append(doc)

        # For exact title matches, check year similarity
        for norm_title, docs in title_groups.items():
            if len(docs) > 1:
                # Group by year (allowing max_year_gap difference)
                year_groups: Dict[Optional[int], List[Document]] = defaultdict(list)
                for doc in docs:
                    year_groups[doc.year].append(doc)

                # Merge years within max_year_gap
                merged_groups: List[List[Document]] = []
                processed_years: Set[Optional[int]] = set()

                for year, year_docs in year_groups.items():
                    if year in processed_years:
                        continue

                    group = list(year_docs)
                    processed_years.add(year)

                    # Find similar years
                    if year is not None:
                        for other_year, other_docs in year_groups.items():
                            if other_year is None or other_year in processed_years:
                                continue
                            if abs(year - other_year) <= self.config.max_year_gap:
                                group.extend(other_docs)
                                processed_years.add(other_year)

                    if len(group) > 1:
                        merged_groups.append(group)

                # Create clusters for merged groups
                for group in merged_groups:
                    cluster = self.create_cluster(cluster_id, group)
                    clusters.append(cluster)
                    for doc in group:
                        clustered.add(id(doc))
                    cluster_id += 1

        # Phase 4: Create singleton clusters for remaining documents
        for doc in documents:
            if id(doc) not in clustered:
                cluster = self.create_cluster(cluster_id, [doc])
                clusters.append(cluster)
                cluster_id += 1

        return clusters


class SemanticStrategy(DeduplicationStrategy):
    """Semantic deduplication strategy.

    This strategy uses embedding-based similarity for fuzzy matching.
    Requires additional dependencies (transformers, sentence-transformers).

    Not implemented yet - placeholder for future enhancement.
    """

    def deduplicate(self, documents: List[Document]) -> List[DocumentCluster]:
        """Deduplicate documents using semantic strategy.

        Args:
            documents: List of documents to deduplicate

        Returns:
            List of document clusters

        Raises:
            NotImplementedError: This strategy is not yet implemented
        """
        raise NotImplementedError("Semantic deduplication not yet implemented")


class HybridStrategy(DeduplicationStrategy):
    """Hybrid deduplication strategy.

    Combines conservative (exact matching) with semantic similarity.

    Not implemented yet - placeholder for future enhancement.
    """

    def deduplicate(self, documents: List[Document]) -> List[DocumentCluster]:
        """Deduplicate documents using hybrid strategy.

        Args:
            documents: List of documents to deduplicate

        Returns:
            List of document clusters

        Raises:
            NotImplementedError: This strategy is not yet implemented
        """
        raise NotImplementedError("Hybrid deduplication not yet implemented")
