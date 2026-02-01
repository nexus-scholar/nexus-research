"""
OpenAlex provider implementation.

OpenAlex is an open, comprehensive index of scholarly papers, authors,
institutions, and more. This provider implements search functionality
for the OpenAlex API.

API Documentation: https://docs.openalex.org/
"""

import logging
from typing import Any, Dict, Iterator, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Author, Document, ExternalIds, Query
from nexus.normalization.standardizer import FieldExtractor, ResponseNormalizer
from nexus.providers.base import BaseProvider
from nexus.providers.query_translator import BooleanQueryTranslator, QueryField
from nexus.utils.exceptions import ProviderError, RateLimitError

logger = logging.getLogger(__name__)


class OpenAlexProvider(BaseProvider):
    """Provider for OpenAlex API."""

    BASE_URL = "https://api.openalex.org/works"

    @property
    def name(self) -> str:
        """Get the provider name.

        Returns:
            Provider name 'openalex'
        """
        return "openalex"

    def __init__(self, config: ProviderConfig):
        """Initialize OpenAlex provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)

        # Set default rate limit if not specified (9/s to be safe)
        if config.rate_limit == 1.0:  # Default value
            self.config.rate_limit = 9.0
            self.rate_limiter.rate = 9.0

        # Field mapping for OpenAlex
        field_map = {
            QueryField.TITLE: "title",
            QueryField.ABSTRACT: "abstract",
            QueryField.AUTHOR: "authorships.author.display_name",
            QueryField.VENUE: "primary_location.source.display_name",
            QueryField.YEAR: "publication_year",
            QueryField.DOI: "doi",
        }
        self.translator = BooleanQueryTranslator(field_map=field_map)
        self.normalizer = ResponseNormalizer(provider_name="openalex")

        logger.info(f"Initialized OpenAlex provider (mailto={config.mailto})")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on OpenAlex."""
        params = self._translate_query(query)

        # Add pagination
        params["per-page"] = 200  # Max per page
        params["cursor"] = "*"  # Start cursor

        # Add select fields for efficiency
        params["select"] = ",".join(
            [
                "id",
                "doi",
                "title",
                "display_name",
                "publication_year",
                "publication_date",
                "primary_location",
                "authorships",
                "cited_by_count",
                "biblio",
                "is_retracted",
                "type",
                "open_access",
                "abstract_inverted_index",
            ]
        )

        page = 0
        total_retrieved = 0
        max_results = query.max_results or float("inf")

        while total_retrieved < max_results:
            # Make request
            try:
                response = self._make_request(
                    self.BASE_URL, params=params, headers=self._get_headers()
                )
            except RateLimitError:
                logger.warning("Rate limit hit, stopping search")
                break
            except ProviderError as e:
                logger.error(f"Search failed: {e}")
                break

            # Extract results
            results = response.get("results", [])
            if not results:
                logger.info("No more results")
                break

            # Process results
            for item in results:
                if total_retrieved >= max_results:
                    return

                doc = self._normalize_response(item)
                if doc:
                    doc.query_id = query.id
                    doc.query_text = query.text
                    yield doc
                    total_retrieved += 1

            # Check for next page
            meta = response.get("meta", {})
            next_cursor = meta.get("next_cursor")

            if not next_cursor:
                logger.info(f"Retrieved {total_retrieved} results (no more pages)")
                break

            params["cursor"] = next_cursor
            page += 1

            logger.debug(f"Page {page}: retrieved {len(results)} results")

        logger.info(f"OpenAlex search complete: {total_retrieved} documents")

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """Translate Query to OpenAlex parameters using BooleanQueryTranslator."""
        # Use translator for main search string
        translation = self.translator.translate(query)
        search_text = translation["q"]

        params = {
            "search": search_text,
        }

        # Build filter string
        filters = []

        # Year range
        if query.year_min or query.year_max:
            year_min = query.year_min or 1900
            year_max = query.year_max or 2100
            filters.append(f"publication_year:{year_min}-{year_max}")

        # Language
        if query.language:
            filters.append(f"language:{query.language}")

        # Type filter
        filters.append("type:article|review")

        if filters:
            params["filter"] = ",".join(filters)

        # Add mailto
        if self.config.mailto:
            params["mailto"] = self.config.mailto

        return params

    def _normalize_response(self, raw: Dict[str, Any]) -> Optional[Document]:
        """Convert OpenAlex response to Document."""
        try:
            extractor = FieldExtractor(raw)

            # Extract title
            title = extractor.get_string("display_name") or extractor.get_string("title")
            if not title:
                return None

            # Extract year
            year = extractor.get_int("publication_year")

            # Extract authors
            authors = self._parse_authors(raw)

            # Extract IDs
            external_ids = self._extract_ids(raw)

            # Extract abstract
            abstract = self._extract_abstract(raw)

            # Extract venue
            venue = extractor.get_string("primary_location.source.display_name")

            # Extract OpenAlex ID
            openalex_id = extractor.get_string("id", "")
            if "openalex.org/" in openalex_id:
                openalex_id = openalex_id.split("/")[-1]

            # Generate provider_id
            provider_id = openalex_id or external_ids.doi or str(hash(title))[:16]

            # Get citation count
            citations = extractor.get_int("cited_by_count", 0)

            # Get URL
            url = f"https://openalex.org/{openalex_id}" if openalex_id else None

            return Document(
                title=title,
                year=year,
                provider="openalex",
                provider_id=provider_id,
                external_ids=external_ids,
                abstract=abstract,
                authors=authors,
                venue=venue,
                url=url,
                cited_by_count=citations,
                raw_data=raw,
            )

        except Exception as e:
            logger.error(f"Failed to normalize OpenAlex document: {e}")
            return None

    def _parse_authors(self, raw: Dict[str, Any]) -> list[Author]:
        """Parse authors from OpenAlex authorships."""
        authorships = raw.get("authorships", [])
        authors = []

        for authorship in authorships:
            author_data = authorship.get("author", {})
            name = author_data.get("display_name") or "Unknown"

            if not name or not name.strip():
                continue

            # Parse name
            parts = name.rsplit(" ", 1)
            if len(parts) == 1:
                family = parts[0]
                given = None
            else:
                family = parts[-1]
                given = parts[0]

            # Get ORCID
            orcid = author_data.get("orcid")
            if orcid and "orcid.org/" in orcid:
                orcid = orcid.split("/")[-1]

            authors.append(Author(family_name=family, given_name=given, orcid=orcid))

        return authors

    def _extract_ids(self, raw: Dict[str, Any]) -> ExternalIds:
        """Extract external IDs from OpenAlex work."""
        extractor = FieldExtractor(raw)

        # Extract DOI
        doi = extractor.get_string("doi")
        if doi and "doi.org/" in doi:
            doi = doi.split("doi.org/")[-1]

        # Extract OpenAlex ID
        openalex_id = extractor.get_string("id")
        if openalex_id and "openalex.org/" in openalex_id:
            openalex_id = openalex_id.split("/")[-1]

        # Extract other IDs
        ids_dict = raw.get("ids", {})
        pmid = ids_dict.get("pmid")
        if pmid:
            pmid = pmid.replace("https://pubmed.ncbi.nlm.nih.gov/", "")

        return ExternalIds(
            doi=doi,
            openalex_id=openalex_id,
            pubmed_id=pmid,
        )

    def _extract_abstract(self, raw: Dict[str, Any]) -> Optional[str]:
        """Extract abstract from inverted index."""
        inverted_index = raw.get("abstract_inverted_index")
        if not inverted_index:
            return None

        try:
            word_positions = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))

            word_positions.sort(key=lambda x: x[0])
            abstract = " ".join(word for _, word in word_positions)

            return abstract[:5000]

        except Exception as e:
            logger.warning(f"Failed to reconstruct abstract: {e}")
            return None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "User-Agent": f'SimpleSLR/1.0 (mailto:{self.config.mailto or ""})',
        }
        return headers