"""Core data models for Simple SLR framework."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExternalIds(BaseModel):
    """All possible paper identifiers.

    This model holds various external identifiers that papers may have
    across different academic databases and repositories.

    Attributes:
        doi: Digital Object Identifier (normalized to lowercase, without URL prefix)
        arxiv_id: arXiv identifier (e.g., '2301.12345')
        pubmed_id: PubMed identifier
        openalex_id: OpenAlex work identifier (e.g., 'W123456789')
        s2_id: Semantic Scholar corpus identifier
    """

    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    openalex_id: Optional[str] = None
    s2_id: Optional[str] = None

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, v: Optional[str]) -> Optional[str]:
        """Normalize DOI by removing URL prefixes and converting to lowercase.

        Handles common DOI formats:
        - https://doi.org/10.1234/test
        - http://dx.doi.org/10.1234/test
        - doi:10.1234/test
        - 10.1234/test

        Args:
            v: Raw DOI string

        Returns:
            Normalized DOI in lowercase without prefixes, or None if input is None
        """
        if not v:
            return None
        import re

        # Remove https://doi.org/ or http://dx.doi.org/ prefixes
        v = re.sub(r"^https?://(dx\.)?doi\.org/", "", v, flags=re.IGNORECASE)
        # Remove doi: prefix
        v = re.sub(r"^doi:\s*", "", v, flags=re.IGNORECASE)
        return v.strip().lower() if v else None


class Author(BaseModel):
    """Author information.

    Represents an academic author with their name components and optional ORCID.

    Attributes:
        family_name: Author's last name (required)
        given_name: Author's first/given name(s) (optional)
        orcid: ORCID identifier (e.g., '0000-0001-2345-6789')
    """

    family_name: str
    given_name: Optional[str] = None
    orcid: Optional[str] = None

    @property
    def full_name(self) -> str:
        """Get full author name in 'Given Family' format.

        Returns:
            Full name if given_name exists, otherwise just family_name
        """
        if self.given_name:
            return f"{self.given_name} {self.family_name}"
        return self.family_name


class Document(BaseModel):
    """Unified document representation across all providers.

    This is the core model representing an academic paper/document
    regardless of which provider it came from. It normalizes data from
    different sources into a consistent structure.

    Attributes:
        title: Document title (required)
        year: Publication year
        provider: Source provider (openalex, crossref, arxiv, s2)
        provider_id: Original identifier from the provider
        external_ids: All known external identifiers
        abstract: Document abstract/summary
        authors: List of authors
        venue: Publication venue (journal, conference, etc.)
        url: URL to the document
        language: Language code (ISO 639-1, e.g., 'en')
        cited_by_count: Number of citations
        query_id: ID of the query that retrieved this document
        query_text: Text of the query that retrieved this document
        retrieved_at: Timestamp when document was retrieved
        cluster_id: Deduplication cluster identifier (populated during dedup)
        raw_data: Original raw response from provider (excluded from serialization)
    """

    # Required fields
    title: str
    year: Optional[int] = None
    provider: str = "unknown"  # openalex, crossref, arxiv, s2
    provider_id: str = ""  # Default to empty string

    # External identifiers
    external_ids: ExternalIds = Field(default_factory=ExternalIds)

    # Optional metadata
    abstract: Optional[str] = None
    authors: List[Author] = Field(default_factory=list)
    venue: Optional[str] = None
    url: Optional[str] = None
    language: Optional[str] = None
    cited_by_count: Optional[int] = None

    # Search context
    query_id: Optional[str] = None
    query_text: Optional[str] = None
    retrieved_at: Optional[datetime] = None

    # Deduplication (populated later)
    cluster_id: Optional[int] = None

    # Raw data for debugging
    raw_data: Optional[Dict[str, Any]] = Field(default=None, exclude=True)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class Query(BaseModel):
    """Search query specification.

    Defines a search query with filtering criteria and metadata.

    Attributes:
        id: Query identifier (e.g., 'Q01', 'Q02'), auto-generated if not provided
        text: Boolean query string or keywords
        year_min: Minimum publication year filter
        year_max: Maximum publication year filter
        language: Language filter (ISO 639-1 code)
        max_results: Maximum number of results to retrieve
        metadata: Additional query metadata (flexible dict)
    """

    id: str = Field(
        default_factory=lambda: f"Q{hash(datetime.now()) % 100000:05d}"
    )  # Auto-generate if not provided
    text: str  # Boolean query string
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    language: str = "en"
    max_results: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentCluster(BaseModel):
    """Deduplication cluster result.

    Represents a group of documents that have been identified as duplicates
    or near-duplicates during the deduplication process.

    Attributes:
        cluster_id: Unique identifier for this cluster
        representative: The document chosen as the canonical representative
        members: All documents in this cluster (including representative)
        all_dois: Aggregated list of all DOIs from all members
        all_arxiv_ids: Aggregated list of all arXiv IDs from all members
        provider_counts: Count of documents from each provider
    """

    cluster_id: int
    representative: Document
    members: List[Document]

    # Aggregated info
    all_dois: List[str] = Field(default_factory=list)
    all_arxiv_ids: List[str] = Field(default_factory=list)
    provider_counts: Dict[str, int] = Field(default_factory=dict)

    @property
    def size(self) -> int:
        """Get cluster size (number of member documents).

        Returns:
            Number of documents in this cluster
        """
        return len(self.members)

    @property
    def confidence(self) -> float:
        """Get deduplication confidence score.

        Returns a confidence score indicating how certain we are that these
        documents are duplicates. Higher when there are exact ID matches.

        Returns:
            1.0 if exact ID match (DOI or arXiv), 0.95 for fuzzy matches
        """
        # 1.0 if exact ID match, lower for fuzzy
        if len(self.all_dois) >= 1 or len(self.all_arxiv_ids) >= 1:
            return 1.0
        return 0.95  # Default for fuzzy matches


class SearchResult(BaseModel):
    """Container for search results.

    Wraps the results of a search operation along with metadata about
    the search itself.

    Attributes:
        query: The query that was executed
        documents: List of documents found
        total_found: Total number of results found (may exceed len(documents))
        provider: Provider that executed the search
        timestamp: When the search was executed
        errors: List of error messages encountered during search
    """

    query: Query
    documents: List[Document]
    total_found: int
    provider: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    errors: List[str] = Field(default_factory=list)
