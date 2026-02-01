"""
CORE (Connecting Repositories) provider implementation.

CORE aggregates millions of open access research papers from thousands of
repositories and journals worldwide. This provider implements search
functionality for the CORE API v3.

API Documentation: https://api.core.ac.uk/docs/v3
"""

import logging
from typing import Any, Dict, Iterator, List, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Author, Document, ExternalIds, Query
from nexus.normalization.standardizer import FieldExtractor, ResponseNormalizer
from nexus.providers.base import BaseProvider
from nexus.utils.exceptions import AuthenticationError, ProviderError

logger = logging.getLogger(__name__)


class CoreProvider(BaseProvider):
    """Provider for CORE API v3.

    CORE provides access to one of the world's largest collections of
    open access research papers.

    Rate limit: 10 requests per 10 seconds.

    Features:
    - Focus on Open Access repositories
    - Aggregated versions of works
    - Direct PDF download links

    Example:
        >>> config = ProviderConfig(api_key="your_key")
        >>> provider = CoreProvider(config)
        >>> query = Query(text="machine learning", year_min=2020)
        >>> for doc in provider.search(query):
        ...     print(doc.title)
    """

    BASE_URL = "https://api.core.ac.uk/v3"

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "core"

    def __init__(self, config: ProviderConfig):
        """Initialize CORE provider."""
        super().__init__(config)
        
        # Set default rate limit (1/s or 10 per 10s)
        if config.rate_limit == 1.0:
            self.config.rate_limit = 1.0
            self.rate_limiter.rate = 1.0

        self.normalizer = ResponseNormalizer(provider_name="core")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on CORE."""
        if not self.config.api_key:
            raise AuthenticationError(self.name, "API key is required for CORE")

        url = f"{self.BASE_URL}/search/works"
        
        # CORE v3 uses 'q' for query and 'limit'/'offset' for pagination
        params = {
            "q": self._translate_query_text(query),
            "limit": 100,
            "offset": 0
        }

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json"
        }

        total_fetched = 0
        max_results = query.max_results or 1000

        while total_fetched < max_results:
            try:
                # Note: CORE supports both GET and POST for search.
                # BaseProvider._make_request uses GET.
                response = self._make_request(url, params=params, headers=headers)
            except Exception as e:
                logger.error(f"CORE search failed: {e}")
                break

            results = response.get("results", [])
            if not results:
                break

            for item in results:
                if total_fetched >= max_results:
                    return

                doc = self._normalize_response(item)
                if doc:
                    doc.query_id = query.id
                    doc.query_text = query.text
                    yield doc
                    total_fetched += 1

            # Check for next page
            total_hits = response.get("totalHits", 0)
            if total_fetched >= total_hits or len(results) < params["limit"]:
                break

            params["offset"] += len(results)

    def _translate_query_text(self, query: Query) -> str:
        """Translate Query object to CORE search string."""
        text = query.text.strip()
        
        # Add year filter if present using yearPublished field
        # CORE uses Lucene-like syntax
        filters = []
        if query.year_min and query.year_max:
            filters.append(f"yearPublished:[{query.year_min} TO {query.year_max}]")
        elif query.year_min:
            filters.append(f"yearPublished:[{query.year_min} TO 3000]")
        elif query.year_max:
            filters.append(f"yearPublished:[1000 TO {query.year_max}]")

        if filters:
            filter_str = " AND ".join(filters)
            if " " in text:
                return f"({text}) AND {filter_str}"
            return f"{text} AND {filter_str}"
            
        return text

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """BaseProvider interface - parameters only."""
        return {}

    def _normalize_response(self, raw: Dict[str, Any]) -> Optional[Document]:
        """Convert CORE JSON result to Document."""
        try:
            extractor = FieldExtractor(raw)

            # Title
            title = extractor.get_string("title")
            if not title:
                return None

            # Year
            year = extractor.get_int("yearPublished")

            # Authors
            authors = []
            author_list = extractor.get_list("authors")
            for au in author_list:
                # au can be string or dict with 'name'
                name = au.get("name") if isinstance(au, dict) else str(au)
                if not name:
                    continue
                
                from nexus.normalization.standardizer import AuthorParser
                parsed = AuthorParser.parse_author_name(name)
                authors.append(Author(
                    family_name=parsed["family"] or "Unknown",
                    given_name=parsed["given"]
                ))

            # Abstract
            abstract = extractor.get_string("abstract")

            # Venue
            venue = None
            # CORE has 'publisher' or 'source' info in different nested levels
            # For Works, check 'publisher'
            venue = extractor.get_string("publisher")

            # IDs
            doi = extractor.get_string("doi")
            
            # CORE ID is the main ID
            core_id = extractor.get_string("id")

            # URL
            url = extractor.get_string("downloadUrl") or extractor.get_string("fullTextUrl")
            if not url:
                url = f"https://core.ac.uk/works/{core_id}" if core_id else None

            # External IDs
            external_ids = ExternalIds(doi=doi)

            return Document(
                title=title,
                year=year,
                abstract=abstract,
                authors=authors,
                venue=venue,
                url=url,
                external_ids=external_ids,
                provider="core",
                provider_id=core_id or doi or str(hash(title))
            )

        except Exception as e:
            logger.error(f"Failed to normalize CORE result: {e}")
            return None
