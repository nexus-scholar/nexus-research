"""
Crossref provider implementation.

Crossref provides comprehensive metadata for scholarly publications,
with a focus on DOI-registered content. This provider implements search
functionality for the Crossref API.

API Documentation: https://api.crossref.org/swagger-ui/index.html
"""

import logging
from typing import Any, Dict, Iterator, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Author, Document, ExternalIds, Query
from nexus.providers.base import BaseProvider
from nexus.providers.normalizer import FieldExtractor, ResponseNormalizer
from nexus.providers.query_translator import SimpleQueryTranslator

logger = logging.getLogger(__name__)


class CrossrefProvider(BaseProvider):
    """Provider for Crossref API.

    Crossref provides DOI registration and metadata for scholarly content.
    Polite pool rate limit: 50 requests/second (with mailto).

    Features:
    - Comprehensive metadata coverage
    - Citation counts
    - Open access status
    - Funder information
    - License information

    Example:
        >>> config = ProviderConfig(
        ...     rate_limit=45.0,
        ...     mailto="researcher@example.com"
        ... )
        >>> provider = CrossrefProvider(config)
        >>> query = Query(text="machine learning", year_min=2020)
        >>> for doc in provider.search(query):
        ...     print(doc.title)
    """

    BASE_URL = "https://api.crossref.org/works"

    # Document types to include in search results
    ALLOWED_TYPES = {
        "journal-article",
        "proceedings-article",
        "posted-content",
        "book-chapter",
        "monograph",
    }

    @property
    def name(self) -> str:
        """Get the provider name.

        Returns:
            Provider name 'crossref'
        """
        return "crossref"

    def __init__(self, config: ProviderConfig):
        """Initialize Crossref provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)

        # Set default rate limit if not specified (45/s to be safe in polite pool)
        if config.rate_limit == 1.0:  # Default value
            self.config.rate_limit = 45.0
            self.rate_limiter.rate = 45.0

        # Initialize translator and normalizer
        self.translator = SimpleQueryTranslator()
        self.normalizer = ResponseNormalizer(provider_name="crossref")

        logger.info(f"Initialized Crossref provider (mailto={config.mailto})")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on Crossref.

        Args:
            query: Query object with search parameters

        Yields:
            Document objects matching the query

        Raises:
            ProviderError: On API errors
            RateLimitError: When rate limit exceeded
        """
        params = self._translate_query(query)

        # Track pagination
        cursor = "*"
        seen_dois = set()
        page_count = 0
        max_pages = 500  # Safety limit

        logger.info(f"Starting Crossref search: {query.text}")

        while cursor and page_count < max_pages:
            # Update cursor in params
            params["cursor"] = cursor

            # Make request
            response_data = self._make_request(self.BASE_URL, params=params)

            # Extract message with items
            message = response_data.get("message", {})
            items = message.get("items", [])

            if not items:
                logger.debug("No more items returned, ending pagination")
                break

            # Process items
            new_docs = 0
            for item in items:
                # Normalize response
                doc = self._normalize_response(item)
                if doc is None:
                    continue

                # Deduplicate by DOI within this search
                doi = doc.external_ids.doi
                if doi and doi in seen_dois:
                    continue
                if doi:
                    seen_dois.add(doi)

                # Apply filters
                if not self._passes_filters(doc, query):
                    continue

                new_docs += 1
                yield doc

            # Check for next cursor
            next_cursor = message.get("next-cursor")
            if not next_cursor or next_cursor == cursor:
                logger.debug("No valid next cursor, ending pagination")
                break

            cursor = next_cursor
            page_count += 1

            logger.debug(
                f"Crossref page {page_count}: {new_docs} new docs, "
                f"total unique DOIs: {len(seen_dois)}"
            )

        logger.info(
            f"Crossref search complete: {len(seen_dois)} unique documents "
            f"over {page_count} pages"
        )

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """Translate Query to Crossref API parameters.

        Args:
            query: Query object

        Returns:
            Dictionary of Crossref API parameters
        """
        params: Dict[str, Any] = {
            "query": query.text,
            "rows": 100,  # Items per page
            "cursor": "*",  # Will be updated during pagination
        }

        # Build filters
        filters = []

        # Year filters
        if query.year_min is not None:
            filters.append(f"from-pub-date:{query.year_min}-01-01")
        if query.year_max is not None:
            filters.append(f"until-pub-date:{query.year_max}-12-31")

        # Document type filters - include multiple allowed types
        for doc_type in self.ALLOWED_TYPES:
            filters.append(f"type:{doc_type}")

        # Abstract filter (if we want only papers with abstracts)
        # filters.append("has-abstract:true")

        if filters:
            params["filter"] = ",".join(filters)

        # Sorting by relevance (default) or citation count
        # Note: Sorting with cursor can be unstable, so we skip it
        # params["sort"] = "relevance"

        # Select specific fields to reduce payload
        params["select"] = ",".join([
            "DOI",
            "title",
            "author",
            "container-title",
            "issued",
            "type",
            "URL",
            "abstract",
            "is-referenced-by-count",
            "publisher",
            "subject",
            "link",
        ])

        # Add mailto for polite pool (higher rate limit)
        if self.config.mailto:
            params["mailto"] = self.config.mailto

        return params

    def _normalize_response(self, raw: Dict[str, Any]) -> Optional[Document]:
        """Convert Crossref response to Document object.

        Args:
            raw: Raw Crossref work object

        Returns:
            Normalized Document object, or None if normalization fails
        """
        extractor = FieldExtractor(raw)

        # Extract title (Crossref returns array of titles)
        titles = extractor.get_list("title")
        title = titles[0] if titles else None

        if not title:
            logger.debug("Skipping item without title")
            return None

        # Extract year from issued date
        year = self._extract_year(raw)

        # Extract DOI
        doi = extractor.get_string("DOI")

        # Extract authors
        authors = self._parse_authors(raw)

        # Extract abstract
        abstract = extractor.get_string("abstract")

        # Extract venue (container-title)
        container_titles = extractor.get_list("container-title")
        venue = container_titles[0] if container_titles else None

        # Extract URL
        url = extractor.get_string("URL")

        # Extract citation count
        citations = extractor.get_int("is-referenced-by-count")

        # Create external IDs
        external_ids = ExternalIds(doi=doi)

        # Create Document (use existing fields; no generic metadata container)
        doc = Document(
            title=title,
            year=year,
            abstract=abstract,
            authors=authors,
            venue=venue,
            url=url,
            external_ids=external_ids,
            provider="crossref",
            cited_by_count=citations,
            raw_data=raw,
        )

        # Nothing else to attach; type/publisher remain in raw_data if needed
        return doc

    def _extract_year(self, raw: Dict[str, Any]) -> Optional[int]:
        """Extract publication year from Crossref date structure.

        Args:
            raw: Raw Crossref work object

        Returns:
            Publication year or None
        """
        extractor = FieldExtractor(raw)

        # Crossref uses nested structure: issued.date-parts[[year, month, day]]
        issued = extractor.get("issued", {})
        if isinstance(issued, dict):
            date_parts = issued.get("date-parts", [])
            if date_parts and isinstance(date_parts, list) and date_parts[0]:
                if isinstance(date_parts[0], list) and len(date_parts[0]) > 0:
                    year = date_parts[0][0]
                    if isinstance(year, int):
                        return year

        return None

    def _parse_authors(self, raw: Dict[str, Any]) -> list[Author]:
        """Parse authors from Crossref response.

        Args:
            raw: Raw Crossref work object

        Returns:
            List of Author objects
        """
        extractor = FieldExtractor(raw)
        authors_data = extractor.get_list("author")

        authors = []
        for author_dict in authors_data:
            if not isinstance(author_dict, dict):
                continue

            author_extractor = FieldExtractor(author_dict)

            family = author_extractor.get_string("family", "Unknown")
            given = author_extractor.get_string("given")
            orcid = author_extractor.get_string("ORCID")

            authors.append(
                Author(
                    family_name=family,
                    given_name=given,
                    orcid=orcid,
                )
            )

        return authors

    def _passes_filters(self, doc: Document, query: Query) -> bool:
        """Check if document passes additional filters.

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

        # Type filtering is handled via API filters; no client-side check
        return True
