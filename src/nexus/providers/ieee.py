"""
IEEE Xplore provider implementation.

IEEE Xplore provides access to more than 5 million full-text documents from some
of the world's most highly-cited publications in electrical engineering,
computer science, and electronics.

API Documentation: https://developer.ieee.org/docs
"""

import logging
from typing import Any, Dict, Iterator, List, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Author, Document, ExternalIds, Query
from nexus.normalization.standardizer import FieldExtractor, ResponseNormalizer
from nexus.providers.base import BaseProvider
from nexus.utils.exceptions import AuthenticationError, ProviderError

logger = logging.getLogger(__name__)


class IEEEProvider(BaseProvider):
    """Provider for IEEE Xplore Metadata Search API.

    IEEE Xplore provides high-quality technical literature.
    Note: Free tier has a strict daily limit (e.g., 200 calls/day).

    Rate limit:
    - 10 requests/second
    - 200 requests/day (typical for free keys)

    Example:
        >>> config = ProviderConfig(api_key="your_key")
        >>> provider = IEEEProvider(config)
        >>> query = Query(text="machine learning", year_min=2020)
        >>> for doc in provider.search(query):
        ...     print(doc.title)
    """

    BASE_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "ieee"

    def __init__(self, config: ProviderConfig):
        """Initialize IEEE provider."""
        super().__init__(config)
        
        # Default rate limit (1/s to stay safe)
        if config.rate_limit == 1.0:
            self.config.rate_limit = 1.0
            self.rate_limiter.rate = 1.0

        self.normalizer = ResponseNormalizer(provider_name="ieee")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on IEEE Xplore."""
        if not self.config.api_key:
            raise AuthenticationError(self.name, "API key is required for IEEE Xplore")

        params = {
            "apikey": self.config.api_key,
            "querytext": query.text,
            "format": "json",
            "max_records": 100,
            "start_record": 1,
            "sort_field": "publication_year",
            "sort_order": "desc"
        }

        # Add year filters
        if query.year_min:
            params["start_year"] = query.year_min
        if query.year_max:
            params["end_year"] = query.year_max

        total_fetched = 0
        max_results = query.max_results or 1000

        while total_fetched < max_results:
            try:
                response = self._make_request(self.BASE_URL, params=params)
            except Exception as e:
                logger.error(f"IEEE search failed: {e}")
                break

            # IEEE returns articles in 'articles' key
            articles = response.get("articles", [])
            if not articles:
                break

            for item in articles:
                if total_fetched >= max_results:
                    return

                doc = self._normalize_response(item)
                if doc:
                    doc.query_id = query.id
                    doc.query_text = query.text
                    yield doc
                    total_fetched += 1

            # Check for next page
            total_records = response.get("total_records", 0)
            if total_fetched >= total_records or len(articles) < params["max_records"]:
                break

            params["start_record"] += len(articles)

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """BaseProvider interface - parameters only."""
        return {}

    def _normalize_response(self, raw: Dict[str, Any]) -> Optional[Document]:
        """Convert IEEE JSON result to Document."""
        try:
            extractor = FieldExtractor(raw)

            # Title
            title = extractor.get_string("title")
            if not title:
                return None

            # Year
            year = extractor.get_int("publication_year")

            # Authors
            authors = []
            author_data = raw.get("authors", {})
            if isinstance(author_data, dict):
                author_list = author_data.get("authors", [])
                for au in author_list:
                    full_name = au.get("full_name")
                    if not full_name:
                        continue
                    
                    from nexus.normalization.standardizer import AuthorParser
                    parsed = AuthorParser.parse_author_name(full_name)
                    authors.append(Author(
                        family_name=parsed["family"] or "Unknown",
                        given_name=parsed["given"]
                    ))

            # Abstract
            abstract = extractor.get_string("abstract")

            # Venue
            venue = extractor.get_string("publication_title")

            # IDs
            doi = extractor.get_string("doi")
            article_number = extractor.get_string("article_number")

            # URL
            url = extractor.get_string("html_url")

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
                provider="ieee",
                provider_id=article_number or doi or str(hash(title))
            )

        except Exception as e:
            logger.error(f"Failed to normalize IEEE result: {e}")
            return None
