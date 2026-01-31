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

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

from nexus.core.config import DeduplicationConfig
from nexus.core.models import Author, Document, DocumentCluster, ExternalIds


class UnionFind:
    """Simple Union-Find (Disjoint Set Union) data structure."""

    def __init__(self, elements):
        self.parent = {e: e for e in elements}

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x != root_y:
            self.parent[root_x] = root_y


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
        
        # Remove non-alphanumeric characters (keep spaces)
        title = re.sub(r"[^\w\s]", "", title)

        return title.strip()

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
            representative: Representative document (if None, fuses best data)

        Returns:
            DocumentCluster instance
        """
        if not documents:
            raise ValueError("Cannot create cluster with no documents")

        # Fuse documents if not provided
        if representative is None:
            representative = DeduplicationStrategy._fuse_documents(documents)

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
    def _fuse_documents(documents: List[Document]) -> Document:
        """Create a 'Golden Record' by fusing data from all documents.

        Strategy:
        1. Base: Start with the document from the most authoritative provider (e.g. Crossref).
        2. Abstract: Pick the longest valid abstract.
        3. Authors: Use base list, but try to enrich with ORCIDs from others.
        4. External IDs: Union of all IDs found.
        5. Metrics: Maximize.

        Args:
            documents: List of documents in the cluster.

        Returns:
            A new Document instance representing the best data.
        """
        # 1. Determine priority and pick base document
        # Provider priority (higher is better)
        provider_priority = {
            "crossref": 5,
            "pubmed": 4,
            "openalex": 3,
            "semantic_scholar": 2,
            "s2": 2,
            "arxiv": 1,
        }

        def get_priority(doc: Document) -> int:
            return provider_priority.get(doc.provider.lower(), 0)

        # Sort by priority desc, then citation count desc
        sorted_docs = sorted(
            documents, 
            key=lambda d: (get_priority(d), d.cited_by_count or 0), 
            reverse=True
        )
        base_doc = sorted_docs[0]
        
        # Create a deep copy of the base doc to modify
        fused = base_doc.model_copy(deep=True)
        
        # 2. Fuse Abstract (Longest valid wins)
        best_abstract = fused.abstract
        
        def is_valid_abstract(text: Optional[str]) -> bool:
            if not text:
                return False
            text = text.strip()
            if len(text) < 20: # Too short
                return False
            if text.lower() in ["no abstract available", "abstract not available"]:
                return False
            return True

        for doc in documents:
            curr = doc.abstract
            if is_valid_abstract(curr):
                if not is_valid_abstract(best_abstract) or len(curr) > len(best_abstract):
                    best_abstract = curr
        
        fused.abstract = best_abstract

        # 3. Fuse External IDs (Union)
        # We start with base IDs and fill in missing ones
        for doc in documents:
            if not fused.external_ids.doi and doc.external_ids.doi:
                fused.external_ids.doi = doc.external_ids.doi
            if not fused.external_ids.arxiv_id and doc.external_ids.arxiv_id:
                fused.external_ids.arxiv_id = doc.external_ids.arxiv_id
            if not fused.external_ids.pubmed_id and doc.external_ids.pubmed_id:
                fused.external_ids.pubmed_id = doc.external_ids.pubmed_id
            if not fused.external_ids.openalex_id and doc.external_ids.openalex_id:
                fused.external_ids.openalex_id = doc.external_ids.openalex_id
            if not fused.external_ids.s2_id and doc.external_ids.s2_id:
                fused.external_ids.s2_id = doc.external_ids.s2_id

        # 4. Enrich Authors (ORCID filling)
        # We rely on the base_doc's author list structure (order/names) as truth.
        # But we check if other docs have ORCIDs for matching names.
        
        if fused.authors:
            for i, author in enumerate(fused.authors):
                if not author.orcid:
                    # Look for this author in other docs
                    target_name = author.family_name.lower()
                    for doc in documents:
                        for other_author in doc.authors:
                            if other_author.orcid and other_author.family_name.lower() == target_name:
                                # Simple check: if given name first char matches (if available)
                                if author.given_name and other_author.given_name:
                                    if author.given_name[0].lower() == other_author.given_name[0].lower():
                                        fused.authors[i].orcid = other_author.orcid
                                        break
                                # If no given name, strict family name match might be risky, but acceptable if list length matches?
                                # Let's be conservative: only match if given name partial match or exact full name match
                                elif author.full_name.lower() == other_author.full_name.lower():
                                    fused.authors[i].orcid = other_author.orcid
                                    break
        
        # 5. Fuse Metrics (Max)
        max_citations = 0
        for doc in documents:
            if doc.cited_by_count and doc.cited_by_count > max_citations:
                max_citations = doc.cited_by_count
        fused.cited_by_count = max_citations
        
        # 6. Fuse Year/Date (Most specific/authoritative)
        # Base doc usually wins, but if base is Arxiv (preprint) and others are published, take published year
        # Actually, sorted_docs[0] is already the most authoritative provider.
        # But if base has no year, fill it.
        if not fused.year:
             for doc in documents:
                 if doc.year:
                     fused.year = doc.year
                     break

        # 7. URL Handling
        # If base is NOT Crossref but we found a DOI, ensure URL is DOI link
        if fused.external_ids.doi and "doi.org" not in (fused.url or ""):
             fused.url = f"https://doi.org/{fused.external_ids.doi}"
        
        # 8. Add provenance note (in raw_data if needed, or just implicitly)
        # We assume fused object is self-sufficient.
        
        return fused


class ConservativeStrategy(DeduplicationStrategy):
    """Conservative deduplication strategy with transitive closure.

    This strategy uses exact identifier matching (DOI, arXiv ID) and fuzzy title matching
    to minimize false positives. It uses a disjoint-set data structure to ensure
    transitive relationships are captured (A=B, B=C => A=C).

    Matching rules:
    1. Exact DOI match
    2. Exact arXiv ID match
    3. Fuzzy title matching (>95% similarity) + same year (within gap)
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

        # Map objects to unique integers for UnionFind
        doc_ids = list(range(len(documents)))
        uf = UnionFind(doc_ids)

        # Build indices
        doi_index: Dict[str, List[int]] = defaultdict(list)
        arxiv_index: Dict[str, List[int]] = defaultdict(list)
        
        # Pre-normalize titles for performance
        norm_titles = [self.normalize_title(d.title) for d in documents]

        for idx, doc in enumerate(documents):
            # Index by DOI
            if doc.external_ids.doi:
                doi = self.normalize_doi(doc.external_ids.doi)
                if doi:
                    doi_index[doi].append(idx)

            # Index by arXiv ID
            if doc.external_ids.arxiv_id:
                arxiv_id = doc.external_ids.arxiv_id.lower().strip()
                if arxiv_id:
                    arxiv_index[arxiv_id].append(idx)

        # Phase 1: Exact DOI matches
        for doi, indices in doi_index.items():
            if len(indices) > 1:
                base = indices[0]
                for other in indices[1:]:
                    uf.union(base, other)

        # Phase 2: Exact arXiv ID matches
        for arxiv_id, indices in arxiv_index.items():
            if len(indices) > 1:
                base = indices[0]
                for other in indices[1:]:
                    uf.union(base, other)

        # Phase 3: Fuzzy title matching
        # Strategy:
        # 1. Block by year to reduce search space.
        # 2. Within blocks, compare titles using rapidfuzz (if available) or strict equality.
        
        # Helper to get the canonical root of a document
        def get_root(i):
            return uf.find(i)

        # Group document indices by year
        docs_by_year: Dict[Optional[int], List[int]] = defaultdict(list)
        for idx, doc in enumerate(documents):
            docs_by_year[doc.year].append(idx)

        years = sorted([y for y in docs_by_year.keys() if y is not None])
        
        # If rapidfuzz is available, we do O(N^2) within blocks
        if fuzz:
            # We can process each year and look at year + gap
            for i, year in enumerate(years):
                # Determine range of years to check against
                # We only need to check forward to avoid duplicate checks
                check_years = [y for y in years[i:] if y - year <= self.config.max_year_gap]
                
                # Collect all candidate documents in this window
                candidates = []
                for y in check_years:
                    candidates.extend(docs_by_year[y])
                
                # Compare all pairs
                for idx_a_pos in range(len(docs_by_year[year])):
                    idx_a = docs_by_year[year][idx_a_pos]
                    
                    for idx_b in candidates:
                        if idx_a >= idx_b: # Avoid self-compare and duplicates
                            continue
                            
                        root_a = uf.find(idx_a)
                        root_b = uf.find(idx_b)
                        
                        if root_a == root_b:
                            continue
                            
                        # Compare titles
                        title_a = norm_titles[idx_a]
                        title_b = norm_titles[idx_b]
                        
                        if not title_a or not title_b:
                            continue

                        # Quick check: exact match
                        if title_a == title_b:
                            uf.union(idx_a, idx_b)
                            continue
                            
                        # Fuzzy check
                        # Normalized titles are already lowercased and cleaned.
                        # rapidfuzz.fuzz.ratio works well on them.
                        score = fuzz.ratio(title_a, title_b)
                        if score >= self.config.fuzzy_threshold:
                            uf.union(idx_a, idx_b)

        else:
            # Fallback: strict normalized title match (O(N) with dict)
            # This is much faster but less powerful
            title_blocks: Dict[str, List[int]] = defaultdict(list)
            for idx, nt in enumerate(norm_titles):
                if nt:
                    title_blocks[nt].append(idx)
            
            for nt, indices in title_blocks.items():
                if len(indices) < 2:
                    continue
                
                # Check year constraints
                for i in range(len(indices)):
                    for j in range(i + 1, len(indices)):
                        idx_a = indices[i]
                        idx_b = indices[j]
                        
                        doc_a = documents[idx_a]
                        doc_b = documents[idx_b]
                        
                        if doc_a.year and doc_b.year:
                            if abs(doc_a.year - doc_b.year) <= self.config.max_year_gap:
                                uf.union(idx_a, idx_b)
                        elif doc_a.year == doc_b.year:
                            uf.union(idx_a, idx_b)

        # Collect clusters
        clusters_map: Dict[int, List[Document]] = defaultdict(list)
        for idx in doc_ids:
            root = uf.find(idx)
            clusters_map[root].append(documents[idx])

        # Create DocumentCluster objects
        results = []
        for i, (root_idx, cluster_docs) in enumerate(clusters_map.items()):
            results.append(self.create_cluster(i, cluster_docs))

        return results


class SemanticStrategy(DeduplicationStrategy):
    """Semantic deduplication strategy.

    This strategy uses embedding-based similarity for fuzzy matching.
    It functions as a second pass after Conservative deduplication:
    1. Run Conservative strategy to group obvious matches.
    2. Embed representatives of each cluster.
    3. Compute cosine similarity between embeddings.
    4. Merge clusters exceeding the semantic threshold.
    """

    def deduplicate(self, documents: List[Document]) -> List[DocumentCluster]:
        """Deduplicate documents using semantic strategy.

        Args:
            documents: List of documents to deduplicate

        Returns:
            List of document clusters
        """
        # 1. Initial pass with Conservative Strategy
        conservative = ConservativeStrategy(self.config)
        initial_clusters = conservative.deduplicate(documents)
        
        if len(initial_clusters) < 2:
            return initial_clusters

        # 2. Setup semantic model
        try:
            from sentence_transformers import SentenceTransformer, util
        except ImportError:
            raise ImportError(
                "Semantic deduplication requires 'sentence-transformers'. "
                "Install with: pip install sentence-transformers"
            )

        # Load model (lazy load could be implemented in a wrapper, but fine here)
        model_name = self.config.embedding_model
        try:
            model = SentenceTransformer(model_name)
        except Exception as e:
            # Fallback to a small, default model if configured one fails
            print(f"Warning: Failed to load {model_name}: {e}. Falling back to 'all-MiniLM-L6-v2'")
            model = SentenceTransformer("all-MiniLM-L6-v2")

        # 3. Embed representatives
        # We use Title + Abstract for better semantic representation
        texts = []
        for cluster in initial_clusters:
            rep = cluster.representative
            text = rep.title
            if rep.abstract:
                text += " " + rep.abstract
            texts.append(text)

        embeddings = model.encode(texts, convert_to_tensor=True, show_progress_bar=True)

        # 4. Compute Similarity Matrix
        cosine_scores = util.cos_sim(embeddings, embeddings)

        # 5. Merge based on threshold
        # We treat initial clusters as nodes in a graph and merge them
        num_clusters = len(initial_clusters)
        uf = UnionFind(range(num_clusters))
        
        threshold = self.config.semantic_threshold
        
        # O(N^2) comparison of clusters
        # Since N here is number of *unique* documents after conservative dedup, 
        # it's much smaller than total documents.
        for i in range(num_clusters):
            for j in range(i + 1, num_clusters):
                score = cosine_scores[i][j].item()
                if score >= threshold:
                    uf.union(i, j)

        # 6. Reconstruct Clusters
        merged_groups: Dict[int, List[DocumentCluster]] = defaultdict(list)
        for i in range(num_clusters):
            root = uf.find(i)
            merged_groups[root].append(initial_clusters[i])

        final_clusters = []
        cluster_id_counter = 0
        
        for group in merged_groups.values():
            if len(group) == 1:
                # No merge needed, just re-assign ID
                cluster = group[0]
                cluster.cluster_id = cluster_id_counter
                final_clusters.append(cluster)
            else:
                # Merge multiple clusters
                all_members = []
                for old_cluster in group:
                    all_members.extend(old_cluster.members)
                
                # Create new merged cluster
                # We pass None as representative to let logic pick the best one from ALL members
                new_cluster = self.create_cluster(cluster_id_counter, all_members)
                final_clusters.append(new_cluster)
            
            cluster_id_counter += 1

        return final_clusters