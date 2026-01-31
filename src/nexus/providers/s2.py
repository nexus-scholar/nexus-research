"""
Semantic Scholar provider implementation.

Semantic Scholar is a free, AI-powered research tool for scientific literature
developed by the Allen Institute for AI.

API Documentation: https://api.semanticscholar.org/
"""

import logging
from typing import Any, Dict, Iterator, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Author, Document, ExternalIds, Query
from nexus.normalization.standardizer import FieldExtractor
from nexus.providers.base import BaseProvider

logger = logging.getLogger(__name__)


def _to_bulk_query(text: str) -> str:
    """Convert human query to S2 bulk boolean syntax.

    Rewrites common boolean operators to the bulk endpoint symbols:
    - AND -> +
    - OR  -> |
    - NOT -> - (prefix)

    Preserves parentheses and quotes if present.
    If no operators are detected, returns the text as-is (bulk treats
    space-separated terms as all required by default).
    """
    if not text:
        return ""
    import re

    # Replace word-bound operators (case-insensitive)
    q = re.sub(r"\bAND\b", "+", text, flags=re.IGNORECASE)
    q = re.sub(r"\bOR\b", "|", q, flags=re.IGNORECASE)
    # For NOT, a simple prefix unary operator: replace leading NOT with '-'
    q = re.sub(r"\bNOT\b\s+", "-", q, flags=re.IGNORECASE)
    # Normalize multiple spaces
    q = re.sub(r"\s+", " ", q).strip()
    return q


class SemanticScholarProvider(BaseProvider):
    """Provider for Semantic Scholar API.

    Semantic Scholar provides AI-powered research tools and comprehensive
    metadata for scientific literature across multiple disciplines.

    Rate limit: 100 requests/second (recommended)

    Features:
    - Comprehensive metadata
    - Citation graph
    - Influential citations
    - Paper recommendations
    - Open access status
    - Full-text search
    - Author disambiguation

    Example:
        >>> config = ProviderConfig(rate_limit=10.0)
        >>> provider = SemanticScholarProvider(config)
        >>> query = Query(text="machine learning", year_min=2020)
        >>> for doc in provider.search(query):
        ...     print(doc.title)
    """

    # Use bulk search endpoint for efficient batch retrieval
    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

    # Fields to retrieve from the API
    FIELDS = [
        "paperId",
        "corpusId",
        "title",
        "abstract",
        "year",
        "authors",
        "venue",
        "citationCount",
        "referenceCount",
        "influentialCitationCount",
        "isOpenAccess",
        "fieldsOfStudy",
        "publicationTypes",
        "externalIds",
        "url",
    ]

    @property
    def name(self) -> str:
        """Get the provider name.

        Returns:
            Provider name 's2' (Semantic Scholar)
        """
        return "s2"

    def __init__(self, config: ProviderConfig):
        """Initialize Semantic Scholar provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)

        # Set default rate limit if not specified (100/s is safe)
        if config.rate_limit == 100.0:  # Default value
            self.config.rate_limit = 100.0
            self.rate_limiter.rate = 100.0

        logger.info("Initialized Semantic Scholar provider")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on Semantic Scholar.

        Args:
            query: Query object with search parameters

        Yields:
            Document objects matching the query

        Raises:
            ProviderError: On API errors
            RateLimitError: When rate limit exceeded
        """
        params = self._translate_query(query)

        token: Optional[str] = None
        seen_paper_ids = set()
        total_fetched = 0

        logger.info(f"Starting S2 bulk search: {query.text}")

        while True:
            # Token-based pagination per bulk API
            if token:
                params["token"] = token
            elif "token" in params:
                params.pop("token", None)

            # Make request
            response_data = self._make_request(self.BASE_URL, params=params)

            # Extract data
            data = response_data.get("data", [])
            token = response_data.get("token")
            total = response_data.get("total", 0)

            if not data:
                logger.debug("No more results returned, ending pagination")
                break

            # Process items
            new_docs = 0
            for item in data:
                # Normalize response
                doc = self._normalize_response(item)
                if doc is None:
                    continue

                # Deduplicate by S2 paper ID
                paper_id = item.get("paperId")
                if paper_id and paper_id in seen_paper_ids:
                    continue
                if paper_id:
                    seen_paper_ids.add(paper_id)

                # Apply filters
                if not self._passes_filters(doc, query):
                    continue

                new_docs += 1
                total_fetched += 1
                yield doc

                # Check max results limit
                if query.max_results and total_fetched >= query.max_results:
                    logger.info(f"Reached max_results limit: {query.max_results}")
                    return

            logger.debug(
                f"S2 bulk page: {new_docs} new docs, total: {total_fetched}, "
                f"has_token: {bool(token)}, approx_total: {total}"
            )

            # Check if we've reached the end (no continuation token)
            if not token:
                break

        logger.info(
            f"S2 search complete: {total_fetched} documents "
            f"({len(seen_paper_ids)} unique S2 IDs)"
        )

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """Translate Query to Semantic Scholar bulk API parameters.

        Args:
            query: Query object

        Returns:
            Dictionary of S2 bulk API parameters
        """
        # Build boolean-friendly query string for bulk endpoint
        bulk_query = _to_bulk_query(query.text.strip())

        params: Dict[str, Any] = {
            "query": bulk_query,
            "fields": ",".join(self.FIELDS),
            # You may add sort here if desired, e.g., "citationCount:desc"
            # "sort": "paperId",
        }

        # Year filters map to 'year' range string
        if query.year_min is not None and query.year_max is not None:
            params["year"] = f"{query.year_min}-{query.year_max}"
        elif query.year_min is not None:
            params["year"] = f"{query.year_min}-"
        elif query.year_max is not None:
            params["year"] = f"-{query.year_max}"

        return params

    def _normalize_response(self, raw: Dict[str, Any]) -> Optional[Document]:
        """Convert S2 response to Document object.

        Args:
            raw: Raw S2 paper object

        Returns:
            Normalized Document object, or None if normalization fails
        """
        extractor = FieldExtractor(raw)

        # Extract title
        title = extractor.get_string("title")

        if not title:
            logger.debug("Skipping item without title")
            return None

        # Extract year
        year = extractor.get_int("year")

        # Extract S2 IDs
        paper_id = extractor.get_string("paperId")

        # Extract external IDs
        external_ids_data = extractor.get("externalIds", {})
        external_ids = self._extract_external_ids(external_ids_data)

        # Set S2 ID in external_ids
        external_ids.s2_id = paper_id

        # Extract authors
        authors = self._parse_authors(raw)

        # Extract abstract
        abstract = extractor.get_string("abstract")

        # Extract venue
        venue = extractor.get_string("venue")

        # Extract URL
        url = extractor.get_string("url")

        # Extract citation count
        citations = extractor.get_int("citationCount")

        # Create Document
        doc = Document(
            title=title,
            year=year,
            abstract=abstract,
            authors=authors,
            venue=venue,
            url=url,
            external_ids=external_ids,
            provider="s2",
            cited_by_count=citations,
            raw_data=raw,
        )

        return doc

    def _extract_external_ids(self, external_ids_data: Dict[str, Any]) -> ExternalIds:
        """Extract external IDs from S2 response.

        Args:
            external_ids_data: External IDs dictionary from S2

        Returns:
            ExternalIds object
        """
        extractor = FieldExtractor(external_ids_data)

        # S2 provides: DOI, ArXiv, MAG, ACL, PubMed, etc.
        # Use get() with None default to avoid empty strings
        doi = extractor.get("DOI") or None
        arxiv_id = extractor.get("ArXiv") or None
        pubmed_id = extractor.get("PubMed") or None

        return ExternalIds(
            doi=doi,
            arxiv_id=arxiv_id,
            pubmed_id=pubmed_id,
        )

    def _parse_authors(self, raw: Dict[str, Any]) -> list[Author]:
        """Parse authors from S2 response.

        Args:
            raw: Raw S2 paper object

        Returns:
            List of Author objects
        """
        extractor = FieldExtractor(raw)
        authors_data = extractor.get_list("authors")

        authors = []
        for author_dict in authors_data:
            if not isinstance(author_dict, dict):
                continue

            author_extractor = FieldExtractor(author_dict)

            # S2 provides full name in "name" field
            name = author_extractor.get_string("name")
            if not name:
                continue

            # Try to split into given/family names
            # S2 typically provides "FirstName LastName" format
            parts = name.rsplit(" ", 1)
            if len(parts) == 2:
                given_name, family_name = parts
            else:
                given_name = None
                family_name = name

            # S2 has authorId but not ORCID directly
            # We could store authorId in a custom field if needed

            authors.append(
                Author(
                    family_name=family_name,
                    given_name=given_name,
                )
            )

        return authors

    def _passes_filters(self, doc: Document, query: Query) -> bool:
        """Check if document passes filters.

        Args:
            doc: Document to check
            query: Original query with filter parameters

        Returns:
            True if document passes all filters
        """
        # Year filter (additional client-side check)
        if doc.year:
            if query.year_min and doc.year < query.year_min:
                return False
            if query.year_max and doc.year > query.year_max:
                return False

        return True
