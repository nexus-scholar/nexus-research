"""
Response normalization utilities for Simple SLR.

This module provides utilities for normalizing provider-specific responses
into the standard Document model, including field extraction, author parsing,
date parsing, and ID extraction.
"""

import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from nexus.core.models import Author, Document, ExternalIds

logger = logging.getLogger(__name__)


class FieldExtractor:
    """Utility for extracting fields from provider responses.

    Provides methods for safely extracting nested fields, with fallbacks
    and type conversions.

    Example:
        >>> extractor = FieldExtractor(response_data)
        >>> title = extractor.get_string("title", default="Unknown")
        >>> year = extractor.get_int("publication_year")
    """

    def __init__(self, data: Dict[str, Any]):
        """Initialize with response data.

        Args:
            data: Raw response dictionary
        """
        self.data = data

    def get(self, path: str, default: Any = None) -> Any:
        """Get value at path using dot notation.

        Args:
            path: Dot-separated path (e.g., "metadata.title")
            default: Default value if path not found

        Returns:
            Value at path or default

        Example:
            >>> extractor.get("authors.0.name")
            'John Doe'
        """
        parts = path.split(".")
        current = self.data

        for part in parts:
            if current is None:
                return default

            # Handle list indexing
            if isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx] if idx < len(current) else default
                except (ValueError, IndexError):
                    return default
            # Handle dict access
            elif isinstance(current, dict):
                current = current.get(part, default)
            else:
                return default

        return current if current is not None else default

    def get_string(self, path: str, default: str = "") -> str:
        """Get string value at path.

        Args:
            path: Dot-separated path
            default: Default string value

        Returns:
            String value or default
        """
        value = self.get(path, default)
        return str(value).strip() if value else default

    def get_int(self, path: str, default: Optional[int] = None) -> Optional[int]:
        """Get integer value at path.

        Args:
            path: Dot-separated path
            default: Default integer value

        Returns:
            Integer value or default
        """
        value = self.get(path)
        if value is None:
            return default

        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert '{value}' to int at path '{path}'")
            return default

    def get_list(self, path: str, default: Optional[List] = None) -> List:
        """Get list value at path.

        Args:
            path: Dot-separated path
            default: Default list value

        Returns:
            List value or default
        """
        value = self.get(path, default or [])
        return value if isinstance(value, list) else (default or [])

    def get_first(self, *paths: str, default: Any = None) -> Any:
        """Get first non-None value from multiple paths.

        Args:
            *paths: Multiple paths to try
            default: Default if all paths are None

        Returns:
            First non-None value or default

        Example:
            >>> extractor.get_first("doi", "DOI", "identifier.doi")
            '10.1234/paper'
        """
        for path in paths:
            value = self.get(path)
            if value is not None:
                return value
        return default


class AuthorParser:
    """Parser for extracting author information from various formats.

    Example:
        >>> parser = AuthorParser()
        >>> authors = parser.parse_authors(raw_authors)
    """

    @staticmethod
    def parse_author_name(name: str) -> Dict[str, Optional[str]]:
        """Parse author name into family and given names.

        Handles formats:
        - "Last, First"
        - "First Last"
        - "Last"

        Args:
            name: Full author name

        Returns:
            Dict with 'family' and 'given' keys
        """
        if not name:
            return {"family": "Unknown", "given": None}

        name = name.strip()

        # Format: "Last, First"
        if "," in name:
            parts = name.split(",", 1)
            return {
                "family": parts[0].strip(),
                "given": parts[1].strip() if len(parts) > 1 else None,
            }

        # Format: "First Last" or "Last"
        parts = name.split()
        if len(parts) == 1:
            return {"family": parts[0], "given": None}
        else:
            # Last word is family name
            return {"family": parts[-1], "given": " ".join(parts[:-1])}

    @classmethod
    def parse_authors(
        cls,
        authors_data: List[Any],
        name_field: str = "name",
        family_field: Optional[str] = None,
        given_field: Optional[str] = None,
        orcid_field: Optional[str] = None,
    ) -> List[Author]:
        """Parse authors from provider data.

        Args:
            authors_data: List of author objects
            name_field: Field containing full name
            family_field: Field containing family name (if separate)
            given_field: Field containing given name (if separate)
            orcid_field: Field containing ORCID

        Returns:
            List of Author objects
        """
        authors = []

        for author_data in authors_data:
            if isinstance(author_data, str):
                # Simple string format
                parsed = cls.parse_author_name(author_data)
                authors.append(
                    Author(
                        family_name=parsed["family"] or "Unknown",
                        given_name=parsed["given"],
                    )
                )
            elif isinstance(author_data, dict):
                # Structured format
                extractor = FieldExtractor(author_data)

                # Try to get family and given names separately
                if family_field:
                    family = extractor.get_string(family_field, "Unknown")
                    given = extractor.get_string(given_field) if given_field else None
                else:
                    # Parse from full name
                    full_name = extractor.get_string(name_field, "Unknown")
                    parsed = cls.parse_author_name(full_name)
                    family = parsed["family"] or "Unknown"
                    given = parsed["given"]

                # Try to extract ORCID - use specified field or try common fields
                if orcid_field:
                    orcid = extractor.get_string(orcid_field)
                else:
                    orcid = extractor.get_first("orcid", "ORCID", "orcid_id")

                authors.append(Author(family_name=family, given_name=given, orcid=orcid))

        return authors


class DateParser:
    """Parser for extracting dates and years from various formats.

    Example:
        >>> parser = DateParser()
        >>> year = parser.extract_year("2023-05-15")
        2023
    """

    @staticmethod
    def extract_year(date_value: Any) -> Optional[int]:
        """Extract year from various date formats.

        Handles:
        - Integer: 2023
        - String: "2023", "2023-05-15", "May 2023"
        - Dict: {"year": 2023}

        Args:
            date_value: Date in various formats

        Returns:
            Year as integer or None
        """
        if date_value is None:
            return None

        # Already an integer
        if isinstance(date_value, int):
            if 1900 <= date_value <= 2100:
                return date_value
            return None

        # Dictionary with year field
        if isinstance(date_value, dict):
            year = date_value.get("year") or date_value.get("Year")
            if year:
                return DateParser.extract_year(year)
            return None

        # String parsing
        if isinstance(date_value, str):
            # Try to extract 4-digit year
            match = re.search(r"\b(19|20)\d{2}\b", date_value)
            if match:
                year = int(match.group(0))
                if 1900 <= year <= 2100:
                    return year

        logger.warning(f"Could not extract year from: {date_value}")
        return None

    @staticmethod
    def parse_date(date_value: Any) -> Optional[datetime]:
        """Parse date to datetime object.

        Args:
            date_value: Date string or timestamp

        Returns:
            datetime object or None
        """
        if not date_value:
            return None

        # Already a datetime
        if isinstance(date_value, datetime):
            return date_value

        # Try common formats
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%d/%m/%Y",
        ]

        date_str = str(date_value)
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_value}")
        return None


class IDExtractor:
    """Extractor for various external identifiers.

    Example:
        >>> extractor = IDExtractor(response_data)
        >>> external_ids = extractor.extract_all()
    """

    def __init__(self, data: Dict[str, Any]):
        """Initialize with response data.

        Args:
            data: Raw response dictionary
        """
        self.extractor = FieldExtractor(data)

    def extract_doi(self, *paths: str) -> Optional[str]:
        """Extract and normalize DOI.

        Args:
            *paths: Paths to try for DOI

        Returns:
            Normalized DOI or None
        """
        doi = self.extractor.get_first(*paths) if paths else self.extractor.get("doi")
        if not doi:
            return None

        # DOI normalization is handled by ExternalIds model
        return str(doi).strip()

    def extract_arxiv_id(self, *paths: str) -> Optional[str]:
        """Extract arXiv ID.

        Args:
            *paths: Paths to try for arXiv ID

        Returns:
            arXiv ID or None
        """
        arxiv_id = self.extractor.get_first(*paths) if paths else self.extractor.get("arxiv_id")
        if not arxiv_id:
            return None

        arxiv_str = str(arxiv_id).strip()

        # Remove common prefixes
        arxiv_str = re.sub(r"^(arxiv:|arXiv:)", "", arxiv_str, flags=re.IGNORECASE)

        return arxiv_str if arxiv_str else None

    def extract_pmid(self, *paths: str) -> Optional[str]:
        """Extract PubMed ID.

        Args:
            *paths: Paths to try for PMID

        Returns:
            PMID or None
        """
        pmid = self.extractor.get_first(*paths) if paths else self.extractor.get("pmid")
        return str(pmid).strip() if pmid else None

    def extract_openalex_id(self, *paths: str) -> Optional[str]:
        """Extract OpenAlex ID.

        Args:
            *paths: Paths to try for OpenAlex ID

        Returns:
            OpenAlex ID or None
        """
        oa_id = self.extractor.get_first(*paths) if paths else self.extractor.get("id")
        if not oa_id:
            return None

        # Extract just the ID part if it's a URL
        oa_str = str(oa_id)
        if "openalex.org" in oa_str:
            match = re.search(r"(W\d+)", oa_str)
            if match:
                return match.group(1)

        return oa_str.strip()

    def extract_s2_id(self, *paths: str) -> Optional[str]:
        """Extract Semantic Scholar corpus ID.

        Args:
            *paths: Paths to try for S2 ID

        Returns:
            S2 corpus ID or None
        """
        s2_id = self.extractor.get_first(*paths) if paths else self.extractor.get("corpusId")
        return str(s2_id).strip() if s2_id else None

    def extract_all(
        self,
        doi_paths: Optional[List[str]] = None,
        arxiv_paths: Optional[List[str]] = None,
        pmid_paths: Optional[List[str]] = None,
        openalex_paths: Optional[List[str]] = None,
        s2_paths: Optional[List[str]] = None,
    ) -> ExternalIds:
        """Extract all available IDs.

        Args:
            doi_paths: Custom paths for DOI
            arxiv_paths: Custom paths for arXiv ID
            pmid_paths: Custom paths for PMID
            openalex_paths: Custom paths for OpenAlex ID
            s2_paths: Custom paths for S2 ID

        Returns:
            ExternalIds object with all found IDs
        """
        return ExternalIds(
            doi=self.extract_doi(*doi_paths) if doi_paths else self.extract_doi(),
            arxiv_id=(
                self.extract_arxiv_id(*arxiv_paths) if arxiv_paths else self.extract_arxiv_id()
            ),
            pubmed_id=self.extract_pmid(*pmid_paths) if pmid_paths else self.extract_pmid(),
            openalex_id=(
                self.extract_openalex_id(*openalex_paths)
                if openalex_paths
                else self.extract_openalex_id()
            ),
            s2_id=self.extract_s2_id(*s2_paths) if s2_paths else self.extract_s2_id(),
        )


class ResponseNormalizer:
    """High-level normalizer for converting provider responses to Documents.

    Combines all extraction utilities for easy normalization.

    Example:
        >>> normalizer = ResponseNormalizer(provider_name="openalex")
        >>> doc = normalizer.normalize(raw_response, {
        ...     'title': 'title',
        ...     'year': 'publication_year',
        ...     'authors': 'authorships',
        ... })
    """

    def __init__(self, provider_name: str):
        """Initialize normalizer.

        Args:
            provider_name: Name of the provider
        """
        self.provider_name = provider_name

    def normalize(
        self,
        data: Dict[str, Any],
        field_map: Dict[str, str],
        author_parser: Optional[Callable] = None,
        id_extractor: Optional[Callable] = None,
    ) -> Optional[Document]:
        """Normalize response data to Document.

        Args:
            data: Raw response data
            field_map: Mapping of Document fields to response fields
            author_parser: Custom author parsing function
            id_extractor: Custom ID extraction function

        Returns:
            Document object or None if normalization fails
        """
        try:
            extractor = FieldExtractor(data)

            # Extract basic fields
            title = extractor.get_string(field_map.get("title", "title"))
            if not title:
                logger.warning("Missing title, skipping document")
                return None

            # Extract year
            year_field = field_map.get("year", "year")
            year_value = extractor.get(year_field)
            year = DateParser.extract_year(year_value)

            # Extract authors
            if author_parser:
                authors = author_parser(data)
            else:
                authors_data = extractor.get_list(field_map.get("authors", "authors"))
                authors = AuthorParser.parse_authors(authors_data)

            # Extract IDs
            if id_extractor:
                external_ids = id_extractor(data)
            else:
                id_ext = IDExtractor(data)
                external_ids = id_ext.extract_all()

            # Extract other fields
            abstract = extractor.get_string(field_map.get("abstract", "abstract"))
            venue = extractor.get_string(field_map.get("venue", "venue"))
            url = extractor.get_string(field_map.get("url", "url"))
            citations = extractor.get_int(field_map.get("citations", "cited_by_count"))

            # Generate provider_id
            provider_id = (
                external_ids.doi
                or external_ids.openalex_id
                or external_ids.arxiv_id
                or external_ids.s2_id
                or str(hash(title))[:16]
            )

            return Document(
                title=title,
                year=year,
                provider=self.provider_name,
                provider_id=provider_id,
                external_ids=external_ids,
                abstract=abstract,
                authors=authors,
                venue=venue,
                url=url,
                cited_by_count=citations,
                raw_data=data,
            )

        except Exception as e:
            logger.error(f"Failed to normalize document: {e}", exc_info=True)
            return None
