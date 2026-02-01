"""
Deduplication strategies for Simple SLR.

This module provides different strategies for identifying and merging duplicate
documents from multiple academic databases.
"""

import re
import unicodedata
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Any

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

from nexus.core.config import DeduplicationConfig
from nexus.core.models import Author, Document, DocumentCluster, ExternalIds

logger = logging.getLogger(__name__)


class UnionFind:
    """Disjoint Set Union with Path Compression and Union by Rank."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, i: int) -> int:
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i: int, j: int):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            if self.rank[root_i] < self.rank[root_j]:
                self.parent[root_i] = root_j
            elif self.rank[root_i] > self.rank[root_j]:
                self.parent[root_j] = root_i
            else:
                self.parent[root_i] = root_j
                self.rank[root_j] += 1


class DeduplicationStrategy(ABC):
    """Base class for deduplication strategies."""

    def __init__(self, config: DeduplicationConfig):
        """Initialize strategy with configuration.

        Args:
            config: Deduplication configuration
        """
        self.config = config

    @abstractmethod
    def deduplicate(self, documents: List[Document], progress_callback=None) -> List[DocumentCluster]:
        """Deduplicate a list of documents.

        Args:
            documents: List of documents to deduplicate
            progress_callback: Optional callable for reporting progress

        Returns:
            List of document clusters, one cluster per unique document
        """
        pass

    @staticmethod
    def normalize_title(title: Optional[str]) -> str:
        """Normalize a title for comparison."""
        if not title:
            return ""
        nfd = unicodedata.normalize("NFD", title)
        title = "".join(c for c in nfd if not unicodedata.combining(c))
        title = title.lower()
        title = re.sub(r"\s+", " ", title).strip()
        title = re.sub(r"[^\w\s]", "", title)
        return title.strip()

    @staticmethod
    def normalize_doi(doi: Optional[str]) -> str:
        """Normalize a DOI for comparison."""
        if not doi:
            return ""
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
        doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
        return doi.strip().lower()

    @staticmethod
    def create_cluster(
        cluster_id: int, documents: List[Document], representative: Optional[Document] = None
    ) -> DocumentCluster:
        """Create a document cluster."""
        if not documents:
            raise ValueError("Cannot create cluster with no documents")

        if representative is None:
            representative = ConservativeStrategy._fuse_documents(documents)

        all_dois = []
        all_arxiv_ids = []
        provider_counts: Dict[str, int] = defaultdict(int)

        for doc in documents:
            if doc.external_ids.doi:
                normalized_doi = ConservativeStrategy.normalize_doi(doc.external_ids.doi)
                if normalized_doi and normalized_doi not in all_dois:
                    all_dois.append(normalized_doi)
            if doc.external_ids.arxiv_id:
                arxiv_id = doc.external_ids.arxiv_id.lower().strip()
                if arxiv_id and arxiv_id not in all_arxiv_ids:
                    all_arxiv_ids.append(arxiv_id)
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
    def _fuse_documents(documents: List[Document]) -> Document:
        """Create a 'Golden Record' by fusing data from all documents."""
        provider_priority = {
            "crossref": 5, "pubmed": 4, "openalex": 3, "semantic_scholar": 2, "s2": 2, "arxiv": 1,
        }
        def get_priority(doc: Document) -> int:
            return provider_priority.get(doc.provider.lower(), 0)

        sorted_docs = sorted(documents, key=lambda d: (get_priority(d), d.cited_by_count or 0), reverse=True)
        base_doc = sorted_docs[0]
        fused = base_doc.model_copy(deep=True)
        
        # Fuse Abstract
        best_abstract = fused.abstract
        def is_valid_abstract(text: Optional[str]) -> bool:
            if not text or len(text.strip()) < 20: return False
            if text.lower() in ["no abstract available", "abstract not available"]: return False
            return True

        for doc in documents:
            if is_valid_abstract(doc.abstract):
                if not is_valid_abstract(best_abstract) or len(doc.abstract) > len(best_abstract):
                    best_abstract = doc.abstract
        fused.abstract = best_abstract

        # Fuse IDs
        for doc in documents:
            if not fused.external_ids.doi: fused.external_ids.doi = doc.external_ids.doi
            if not fused.external_ids.arxiv_id: fused.external_ids.arxiv_id = doc.external_ids.arxiv_id
            if not fused.external_ids.pubmed_id: fused.external_ids.pubmed_id = doc.external_ids.pubmed_id
            if not fused.external_ids.openalex_id: fused.external_ids.openalex_id = doc.external_ids.openalex_id
            if not fused.external_ids.s2_id: fused.external_ids.s2_id = doc.external_ids.s2_id

        # Enrich Authors
        if fused.authors:
            for i, author in enumerate(fused.authors):
                if not author.orcid:
                    target_name = author.family_name.lower()
                    for doc in documents:
                        for other in doc.authors:
                            if other.orcid and other.family_name.lower() == target_name:
                                if author.given_name and other.given_name:
                                    if author.given_name[0].lower() == other.given_name[0].lower():
                                        fused.authors[i].orcid = other.orcid
                                        break
                                elif author.full_name.lower() == other.full_name.lower():
                                    fused.authors[i].orcid = other.orcid
                                    break
        
        # Max Metrics
        fused.cited_by_count = max((d.cited_by_count or 0 for d in documents), default=0)
        if not fused.year:
             for doc in documents:
                 if doc.year: fused.year = doc.year; break
        if fused.external_ids.doi and "doi.org" not in (fused.url or ""):
             fused.url = f"https://doi.org/{fused.external_ids.doi}"
        
        return fused


class ConservativeStrategy(DeduplicationStrategy):
    """Optimized conservative deduplication strategy."""

    def deduplicate(self, documents: List[Document], progress_callback=None) -> List[DocumentCluster]:
        if not documents:
            return []

        n = len(documents)
        uf = UnionFind(n)

        # Build indices
        doi_index = defaultdict(list)
        arxiv_index = defaultdict(list)
        title_index = defaultdict(list)
        
        norm_titles = []
        title_word_sets = []

        if progress_callback: progress_callback("Preprocessing titles...", 5)

        for idx, doc in enumerate(documents):
            if doc.external_ids.doi:
                doi = self.normalize_doi(doc.external_ids.doi)
                if doi: doi_index[doi].append(idx)
            if doc.external_ids.arxiv_id:
                arxiv_id = doc.external_ids.arxiv_id.lower().strip()
                if arxiv_id: arxiv_index[arxiv_id].append(idx)
            
            nt = self.normalize_title(doc.title)
            norm_titles.append(nt)
            title_word_sets.append(set(nt.split()) if nt else set())
            if nt: title_index[nt].append(idx)

        # Phase 1: Exact matches
        if progress_callback: progress_callback("Matching exact identifiers...", 10)
        for indices in doi_index.values():
            for i in range(1, len(indices)): uf.union(indices[0], indices[i])
        for indices in arxiv_index.values():
            for i in range(1, len(indices)): uf.union(indices[0], indices[i])

        # Phase 2: Exact Title Blocking
        if progress_callback: progress_callback("Matching exact titles...", 15)
        for indices in title_index.values():
            for i in range(1, len(indices)): uf.union(indices[0], indices[i])

        # Phase 3: Fuzzy matching
        docs_by_year = defaultdict(list)
        for idx, doc in enumerate(documents):
            docs_by_year[doc.year].append(idx)

        years = sorted([y for y in docs_by_year.keys() if y is not None])
        total_years = len(years)

        if fuzz:
            for i, year in enumerate(years):
                if progress_callback:
                    percent = 20 + int(70 * (i / total_years))
                    progress_callback(f"Fuzzy matching year {year}...", percent)

                check_years = [y for y in years[i:] if y - year <= self.config.max_year_gap]
                candidates = []
                for y in check_years: candidates.extend(docs_by_year[y])
                
                for idx_a in docs_by_year[year]:
                    words_a = title_word_sets[idx_a]
                    if not words_a: continue
                    
                    for idx_b in candidates:
                        if idx_a >= idx_b: continue
                        if uf.find(idx_a) == uf.find(idx_b): continue
                        
                        words_b = title_word_sets[idx_b]
                        if not words_b: continue
                        
                        # Set-intersection pruning
                        common = len(words_a & words_b)
                        if common < 2: continue
                        
                        score = fuzz.ratio(norm_titles[idx_a], norm_titles[idx_b])
                        if score >= self.config.fuzzy_threshold:
                            uf.union(idx_a, idx_b)

        # Finalize clusters
        if progress_callback: progress_callback("Generating final clusters...", 95)
        clusters_map = defaultdict(list)
        for idx in range(n):
            root = uf.find(idx)
            clusters_map[root].append(documents[idx])

        results = []
        for i, (root_idx, cluster_docs) in enumerate(clusters_map.items()):
            results.append(self.create_cluster(i, cluster_docs))

        return results


class SemanticStrategy(DeduplicationStrategy):
    """Semantic deduplication strategy."""

    def deduplicate(self, documents: List[Document], progress_callback=None) -> List[DocumentCluster]:
        conservative = ConservativeStrategy(self.config)
        initial_clusters = conservative.deduplicate(documents, progress_callback=progress_callback)
        
        if len(initial_clusters) < 2:
            return initial_clusters

        try:
            from sentence_transformers import SentenceTransformer, util
        except ImportError:
            raise ImportError("Semantic deduplication requires 'sentence-transformers'.")

        if progress_callback: progress_callback("Loading semantic model...", 30)
        model_name = self.config.embedding_model
        try:
            model = SentenceTransformer(model_name)
        except Exception:
            model = SentenceTransformer("all-MiniLM-L6-v2")

        if progress_callback: progress_callback("Embedding clusters...", 50)
        texts = []
        for cluster in initial_clusters:
            rep = cluster.representative
            text = rep.title
            if rep.abstract: text += " " + rep.abstract
            texts.append(text)

        embeddings = model.encode(texts, convert_to_tensor=True, show_progress_bar=False)
        cosine_scores = util.cos_sim(embeddings, embeddings)

        num_clusters = len(initial_clusters)
        uf = UnionFind(num_clusters)
        threshold = self.config.semantic_threshold
        
        for i in range(num_clusters):
            for j in range(i + 1, num_clusters):
                if cosine_scores[i][j].item() >= threshold:
                    uf.union(i, j)

        merged_groups = defaultdict(list)
        for i in range(num_clusters):
            root = uf.find(i)
            merged_groups[root].append(initial_clusters[i])

        final_clusters = []
        for i, group in enumerate(merged_groups.values()):
            all_members = []
            for old_cluster in group: all_members.extend(old_cluster.members)
            final_clusters.append(self.create_cluster(i, all_members))

        return final_clusters
