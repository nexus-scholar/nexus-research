"""
DOAJ (Directory of Open Access Journals) provider implementation.

DOAJ is a community-curated online directory that indexes and provides access
to high quality, open access, peer-reviewed journals.

API Documentation: https://doaj.org/api/v1/docs
"""

import logging
from typing import Any, Dict, Iterator, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Author, Document, ExternalIds, Query
from nexus.normalization.standardizer import FieldExtractor, ResponseNormalizer
from nexus.providers.base import BaseProvider
from nexus.utils.exceptions import ProviderError

logger = logging.getLogger(__name__)


class DOAJProvider(BaseProvider):
    """Provider for DOAJ API.

    DOAJ provides a search interface for open access articles.
    It uses Elasticsearch query syntax.

    Features:
    - Focus on Open Access content
    - Rich bibliographic metadata (BibJSON)
    - Full text links

    Example:
        >>> config = ProviderConfig()
        >>> provider = DOAJProvider(config)
        >>> query = Query(text="machine learning", year_min=2020)
        >>> for doc in provider.search(query):
        ...     print(doc.title)
    """

    BASE_URL = "https://doaj.org/api/v1/search/articles"

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "doaj"

    def __init__(self, config: ProviderConfig):
        """Initialize DOAJ provider."""
        super().__init__(config)
        self.normalizer = ResponseNormalizer(provider_name="doaj")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on DOAJ."""
        # DOAJ search syntax: /search/articles/{query}?page=1&pageSize=10
        # We'll put the query in the path part as suggested by documentation
        
        search_text = self._translate_query_text(query)
        
        page = 1
        page_size = 100
        total_fetched = 0
        max_results = query.max_results or 1000

        while total_fetched < max_results:
            url = f"{self.BASE_URL}/{search_text}"
            params = {
                "page": page,
                "pageSize": page_size
            }

            try:
                response = self._make_request(url, params=params)
            except Exception as e:
                logger.error(f"DOAJ search failed: {e}")
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

            # Check if we've reached the end
            total_available = response.get("total", 0)
            if total_fetched >= total_available or len(results) < page_size:
                break

            page += 1

    def _translate_query_text(self, query: Query) -> str:
        """Translate Query object to DOAJ/Elasticsearch query string."""
        # Simple implementation for now
        # DOAJ supports field:value syntax
        
        text = query.text.strip()
        
        # Add year filter if present using range syntax
        # bibjson.year:[2020 TO 2025]
        year_filter = ""
        if query.year_min and query.year_max:
            year_filter = f" AND bibjson.year:[{query.year_min} TO {query.year_max}]"
        elif query.year_min:
            year_filter = f" AND bibjson.year:[{query.year_min} TO 3000]"
        elif query.year_max:
            year_filter = f" AND bibjson.year:[1000 TO {query.year_max}]"

        # Combine
        if year_filter:
            # Wrap original text in parentheses if it's complex
            if " " in text:
                return f"({text}){year_filter}"
            return f"{text}{year_filter}"
            
        return text

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """BaseProvider interface - parameters only."""
        # Not used directly as query text is in path
        return {}

    def _normalize_response(self, raw: Dict[str, Any]) -> Optional[Document]:
        """Convert DOAJ JSON result to Document."""
        try:
            bibjson = raw.get("bibjson", {})
            extractor = FieldExtractor(bibjson)

            # Title
            title = extractor.get_string("title")
            if not title:
                return None

            # Year
            year_val = extractor.get("year")
            year = None
            if year_val:
                try:
                    year = int(year_val)
                except (ValueError, TypeError):
                    pass

            # Authors
            authors = []
            author_list = extractor.get_list("author")
            for au in author_list:
                name = au.get("name")
                if not name:
                    continue
                
                # Use AuthorParser to split name
                from nexus.normalization.standardizer import AuthorParser
                parsed = AuthorParser.parse_author_name(name)
                authors.append(Author(
                    family_name=parsed["family"] or "Unknown",
                    given_name=parsed["given"]
                ))

            # Abstract
            abstract = extractor.get_string("abstract")

            # Venue (Journal title)
            venue = extractor.get_string("journal.title")

            # IDs
            doi = None
            identifiers = extractor.get_list("identifier")
            for ident in identifiers:
                if ident.get("type") == "doi":
                    doi = ident.get("id")
                    break

            # URL
            url = None
            for ident in identifiers:
                if ident.get("type") == "url":
                    url = ident.get("id")
                    break
            
            # Fallback URL: DOI
            if not url and doi:
                url = f"https://doi.org/{doi}"

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
                provider="doaj",
                provider_id=raw.get("id") or doi or str(hash(title))
            )

        except Exception as e:
            logger.error(f"Failed to normalize DOAJ result: {e}")
            return None
