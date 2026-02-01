"""
arXiv provider implementation.

arXiv is a free distribution service and open-access archive for scholarly
articles in physics, mathematics, computer science, and related disciplines.

API Documentation: https://arxiv.org/help/api/
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterator, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Author, Document, ExternalIds, Query
from nexus.providers.base import BaseProvider
from nexus.providers.query_translator import BooleanQueryTranslator, QueryField

logger = logging.getLogger(__name__)


class ArxivProvider(BaseProvider):
    """Provider for arXiv API.

    arXiv provides free access to preprints in physics, mathematics,
    computer science, quantitative biology, quantitative finance, and statistics.

    Rate limit: 3 requests/second (recommended by arXiv)

    Features:
    - Open access preprints
    - Full-text search
    - Category filtering
    - Author search
    - PDF downloads
    - Version tracking

    Example:
        >>> config = ProviderConfig(rate_limit=3.0)
        >>> provider = ArxivProvider(config)
        >>> query = Query(text="machine learning", year_min=2020)
        >>> for doc in provider.search(query):
        ...     print(doc.title)
    """

    BASE_URL = "https://export.arxiv.org/api/query"

    # XML namespaces for arXiv Atom feed
    NAMESPACES = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    }

    # Default categories (can be customized via config)
    DEFAULT_CATEGORIES = ["cs.CV", "cs.LG", "cs.AI", "stat.ML"]

    @property
    def name(self) -> str:
        """Get the provider name.

        Returns:
            Provider name 'arxiv'
        """
        return "arxiv"

    def __init__(self, config: ProviderConfig):
        """Initialize arXiv provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)

        # Set default rate limit if not specified (3/s as recommended)
        if config.rate_limit == 1.0:  # Default value
            self.config.rate_limit = 3.0
            self.rate_limiter.rate = 3.0

        # Field mapping for ArXiv
        field_map = {
            QueryField.TITLE: "ti",
            QueryField.ABSTRACT: "abs",
            QueryField.AUTHOR: "au",
            QueryField.VENUE: "jr",
            QueryField.ANY: "all",
        }
        self.translator = BooleanQueryTranslator(field_map=field_map)

        logger.info("Initialized arXiv provider")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on arXiv.

        Args:
            query: Query object with search parameters

        Yields:
            Document objects matching the query

        Raises:
            ProviderError: On API errors
            RateLimitError: When rate limit exceeded
        """
        params = self._translate_query(query)

        start = 0
        max_results_per_page = 100
        seen_arxiv_ids = set()
        total_fetched = 0

        # Track total results reported by arXiv (opensearch:totalResults)
        total_results: Optional[int] = None
        # arXiv API hard cap: start must be < 10000
        MAX_START = 10000

        logger.info(f"Starting arXiv search: {query.text}")

        while True:
            # Stop if we've reached provider/API caps before making a request
            if total_results is not None and start >= total_results:
                logger.debug(
                    f"Reached totalResults limit from feed: start={start} >= total={total_results}"
                )
                break
            if start >= MAX_START:
                logger.warning(
                    "Reached arXiv API offset cap (start >= 10000); stopping pagination"
                )
                break

            # Update pagination params
            params["start"] = start
            params["max_results"] = max_results_per_page

            # Make request
            response = self._make_request_xml(self.BASE_URL, params=params)

            # Parse XML
            try:
                root = ET.fromstring(response)
            except ET.ParseError as e:
                logger.error(f"Failed to parse arXiv XML response: {e}")
                break

            # Initialize total_results from feed metadata if available
            if total_results is None:
                try:
                    tot_text = root.findtext(
                        "opensearch:totalResults",
                        default="0",
                        namespaces=self.NAMESPACES,
                    )
                    total_results = int(tot_text) if tot_text is not None else None
                except Exception:
                    total_results = None

            # Get entries
            entries = root.findall("atom:entry", self.NAMESPACES)

            if not entries:
                logger.debug("No more entries returned, ending pagination")
                break

            # Process entries
            new_docs = 0
            for entry in entries:
                # Normalize response
                doc = self._normalize_response(entry)
                if doc is None:
                    continue

                # Deduplicate by arXiv ID
                arxiv_id = doc.external_ids.arxiv_id
                if arxiv_id and arxiv_id in seen_arxiv_ids:
                    continue
                if arxiv_id:
                    seen_arxiv_ids.add(arxiv_id)

                # Apply filters (year filtering)
                if not self._passes_filters(doc, query):
                    continue

                new_docs += 1
                total_fetched += 1
                yield doc

                # Check max results limit
                if query.max_results and total_fetched >= query.max_results:
                    logger.info(f"Reached max_results limit: {query.max_results}")
                    return

            # Update pagination
            start += len(entries)

            logger.debug(
                f"arXiv page: {new_docs} new docs, "
                f"total: {total_fetched}, start: {start}"
            )

            # Stop if fewer than requested (end of feed), or if we'd exceed caps on next loop
            if len(entries) < max_results_per_page:
                break

        logger.info(
            f"arXiv search complete: {total_fetched} documents "
            f"({len(seen_arxiv_ids)} unique arXiv IDs)"
        )

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """Translate Query to arXiv API parameters using BooleanQueryTranslator.

        Args:
            query: Query object

        Returns:
            Dictionary of arXiv API parameters
        """
        # Build search query string using the centralized translator
        translation = self.translator.translate(query)
        search_query = translation["q"]

        params: Dict[str, Any] = {
            "search_query": search_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        return params

    def _make_request_xml(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> str:
        """Make HTTP request and return XML response text.

        Args:
            url: Request URL
            params: Query parameters

        Returns:
            Response text (XML)
        """
        import requests
        from urllib.parse import urlencode

        # Store last query for scientific provenance
        query_str = f"{url}"
        if params:
            query_str = f"{url}?{urlencode(params)}"
        self._last_query = query_str

        # Wait for rate limit
        if not self.rate_limiter.wait_for_token(timeout=30):
            from nexus.utils.exceptions import RateLimitError

            raise RateLimitError(
                self.name,
                "Rate limit timeout for arXiv",
            )

        headers = {
            "User-Agent": f'SimpleSLR/1.0 ({self.config.mailto or ""})',
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            from nexus.utils.exceptions import NetworkError

            raise NetworkError(self.name, f"Request failed: {e}")

    def _normalize_response(self, entry: ET.Element) -> Optional[Document]:
        """Convert arXiv entry to Document object.

        Args:
            entry: XML entry element from arXiv feed

        Returns:
            Normalized Document object, or None if normalization fails
        """
        # Extract title
        title_elem = entry.find("atom:title", self.NAMESPACES)
        title = title_elem.text.strip() if title_elem is not None else None

        if not title:
            logger.debug("Skipping entry without title")
            return None

        # Extract abstract/summary
        summary_elem = entry.find("atom:summary", self.NAMESPACES)
        abstract = summary_elem.text.strip() if summary_elem is not None else None

        # Extract publication year from published date
        published_elem = entry.find("atom:published", self.NAMESPACES)
        published_text = published_elem.text if published_elem is not None else None
        year = self._extract_year(published_text)

        # Extract arXiv ID from id URL
        id_elem = entry.find("atom:id", self.NAMESPACES)
        id_url = id_elem.text if id_elem is not None else None
        arxiv_id = self._extract_arxiv_id(id_url)

        # Extract DOI if present
        doi_elem = entry.find("arxiv:doi", self.NAMESPACES)
        doi = doi_elem.text if doi_elem is not None else None

        # Extract authors
        authors = self._parse_authors(entry)

        # Extract primary category for venue
        primary_cat_elem = entry.find("arxiv:primary_category", self.NAMESPACES)
        primary_category = None
        if primary_cat_elem is not None:
            primary_category = primary_cat_elem.get("term")

        venue = f"arXiv ({primary_category})" if primary_category else "arXiv"

        # Extract links (abstract page and PDF)
        abs_url, pdf_url = self._extract_links(entry, id_url)

        # Create external IDs
        external_ids = ExternalIds(
            arxiv_id=arxiv_id,
            doi=doi,
        )

        # Create Document
        doc = Document(
            title=title,
            year=year,
            abstract=abstract,
            authors=authors,
            venue=venue,
            url=abs_url or id_url,
            external_ids=external_ids,
            provider="arxiv",
            raw_data=None,
        )

        return doc

    def _extract_year(self, date_str: Optional[str]) -> Optional[int]:
        """Extract year from ISO date string.

        Args:
            date_str: ISO date string (e.g., "2023-01-15T12:00:00Z")

        Returns:
            Year as integer or None
        """
        if not date_str:
            return None

        try:
            # Extract first 4 characters as year
            return int(date_str[:4])
        except (ValueError, IndexError):
            return None

    def _extract_arxiv_id(self, id_url: Optional[str]) -> Optional[str]:
        """Extract arXiv ID from ID URL.

        Args:
            id_url: arXiv ID URL (e.g., "http://arxiv.org/abs/2301.12345v1")

        Returns:
            arXiv ID (e.g., "2301.12345") or None
        """
        if not id_url:
            return None

        # Match pattern: arxiv.org/abs/XXXX.XXXXX or arxiv.org/abs/XXXX.XXXXXvN
        match = re.search(r"arxiv\.org/abs/(\d+\.\d+)(?:v\d+)?", id_url, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _parse_authors(self, entry: ET.Element) -> list[Author]:
        """Parse authors from arXiv entry.

        Args:
            entry: XML entry element

        Returns:
            List of Author objects
        """
        authors = []

        for author_elem in entry.findall("atom:author", self.NAMESPACES):
            name_elem = author_elem.find("atom:name", self.NAMESPACES)
            if name_elem is None or not name_elem.text:
                continue

            full_name = name_elem.text.strip()

            # Try to split into given/family names
            # arXiv typically provides "FirstName LastName" format
            parts = full_name.rsplit(" ", 1)
            if len(parts) == 2:
                given_name, family_name = parts
            else:
                given_name = None
                family_name = full_name

            authors.append(
                Author(
                    family_name=family_name,
                    given_name=given_name,
                )
            )

        return authors

    def _extract_links(
        self, entry: ET.Element, id_url: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """Extract abstract and PDF links from entry.

        Args:
            entry: XML entry element
            id_url: arXiv ID URL

        Returns:
            Tuple of (abstract_url, pdf_url)
        """
        abs_url = None
        pdf_url = None

        for link_elem in entry.findall("atom:link", self.NAMESPACES):
            href = link_elem.get("href")
            rel = link_elem.get("rel", "")
            link_type = link_elem.get("type", "")
            title = link_elem.get("title", "")

            if not href:
                continue

            # Abstract link (rel="alternate")
            if rel == "alternate":
                abs_url = href

            # PDF link (type="application/pdf" or title="pdf")
            if link_type == "application/pdf" or title.lower() == "pdf":
                pdf_url = href

        # Fallback: construct PDF URL from abstract URL
        if not pdf_url and abs_url and "/abs/" in abs_url:
            pdf_url = abs_url.replace("/abs/", "/pdf/") + ".pdf"
        elif not pdf_url and id_url and "/abs/" in id_url:
            pdf_url = id_url.replace("/abs/", "/pdf/") + ".pdf"

        return abs_url, pdf_url

    def _passes_filters(self, doc: Document, query: Query) -> bool:
        """Check if document passes filters.

        Args:
            doc: Document to check
            query: Original query with filter parameters

        Returns:
            True if document passes all filters
        """
        # Year filter (arXiv doesn't support server-side year filtering)
        if doc.year:
            if query.year_min and doc.year < query.year_min:
                return False
            if query.year_max and doc.year > query.year_max:
                return False

        return True