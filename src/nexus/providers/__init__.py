"""
Provider implementations for Simple SLR.

This package contains provider implementations for various academic databases
and search engines, including OpenAlex, Crossref, arXiv, and Semantic Scholar.

Available Providers:
    - OpenAlex: Open bibliographic database
    - Crossref: DOI metadata provider
    - arXiv: Preprint repository
    - Semantic Scholar: AI-powered paper search

Example:
    >>> from nexus.providers import get_registry
    >>> from nexus.core import SLRConfig, load_config
    >>>
    >>> config = load_config(Path("config.yml"))
    >>> registry = get_registry()
    >>>
    >>> # Providers are automatically registered from config
    >>> for name in registry.list_providers():
    ...     print(name)
"""

from .arxiv import ArxivProvider
from .base import BaseProvider, ProviderRegistry, get_registry
from .crossref import CrossrefProvider
from .doaj import DOAJProvider
from .openalex import OpenAlexProvider
from .pubmed import PubMedProvider
from .query_translator import (
    BaseQueryTranslator,
    BooleanOperator,
    BooleanQueryTranslator,
    QueryField,
    QueryParser,
    QueryToken,
    SimpleQueryTranslator,
    StructuredQueryTranslator,
    create_translator,
)
from .s2 import SemanticScholarProvider

# Re-export normalization classes from new location for compatibility
from nexus.normalization.standardizer import (
    AuthorParser,
    DateParser,
    FieldExtractor,
    IDExtractor,
    ResponseNormalizer,
)

# Import ProviderConfig for type hints
from nexus.core.config import ProviderConfig


def get_provider(name: str, config: ProviderConfig) -> BaseProvider:
    """Get a provider instance by name.

    Factory function to create provider instances.

    Args:
        name: Provider name (openalex, crossref, arxiv, semantic_scholar, s2, pubmed)
        config: Provider configuration

    Returns:
        Provider instance

    Raises:
        ValueError: If provider name is unknown
    """
    provider_map = {
        "openalex": OpenAlexProvider,
        "crossref": CrossrefProvider,
        "arxiv": ArxivProvider,
        "semantic_scholar": SemanticScholarProvider,
        "s2": SemanticScholarProvider,  # Alias
        "pubmed": PubMedProvider,
        "doaj": DOAJProvider,
    }

    name_lower = name.lower()
    if name_lower not in provider_map:
        raise ValueError(
            f"Unknown provider '{name}'. "
            f"Available: {', '.join(provider_map.keys())}"
        )

    provider_class = provider_map[name_lower]
    return provider_class(config)


__all__ = [
    # Base provider
    "BaseProvider",
    "ProviderRegistry",
    "get_registry",
    "get_provider",
    # Query translation
    "QueryParser",
    "QueryToken",
    "QueryField",
    "BooleanOperator",
    "BaseQueryTranslator",
    "SimpleQueryTranslator",
    "BooleanQueryTranslator",
    "StructuredQueryTranslator",
    "create_translator",
    # Response normalization (Re-exported)
    "FieldExtractor",
    "AuthorParser",
    "DateParser",
    "IDExtractor",
    "ResponseNormalizer",
    # Providers
    "OpenAlexProvider",
    "CrossrefProvider",
    "ArxivProvider",
    "SemanticScholarProvider",
    "PubMedProvider",
    "DOAJProvider",
]