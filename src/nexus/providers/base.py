"""
Base provider module for Simple SLR.

This module defines the abstract base class for all provider implementations,
along with provider-specific configuration and interfaces.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Document, Query
from nexus.utils.exceptions import (
    AuthenticationError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from nexus.utils.rate_limit import TokenBucket
from nexus.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Abstract base class for all data providers.

    This class defines the interface that all provider implementations must follow.
    It provides common functionality like rate limiting, error handling, and
    logging, while requiring subclasses to implement provider-specific logic.

    Attributes:
        config: Provider configuration
        rate_limiter: Token bucket rate limiter
        name: Provider name (from config)

    Example:
        >>> class MyProvider(BaseProvider):
        ...     def search(self, query: Query) -> Iterator[Document]:
        ...         # Implementation
        ...         yield document
        ...
        ...     def _translate_query(self, query: Query) -> Dict[str, Any]:
        ...         return {"q": query.text}
        ...
        ...     def _normalize_response(self, raw: Dict) -> Optional[Document]:
        ...         return Document(...)
    """

    def __init__(self, config: ProviderConfig):
        """Initialize the provider.

        Args:
            config: Provider configuration with rate limits, timeouts, etc.

        Raises:
            ValueError: If config is invalid
        """
        if not isinstance(config, ProviderConfig):
            raise ValueError("config must be a ProviderConfig instance")

        self.config = config
        self._last_query: Optional[str] = None

        # Initialize rate limiter
        self.rate_limiter = TokenBucket(
            rate=config.rate_limit, capacity=int(config.rate_limit * 5)  # 5x burst capacity
        )

        logger.info(
            f"Initialized {self.name} provider "
            f"(rate_limit={config.rate_limit}/s, timeout={config.timeout}s)"
        )

    @property
    def name(self) -> str:
        """Get the provider name.

        Returns:
            Provider name from configuration or class name
        """
        return getattr(self.config, "name", self.__class__.__name__.lower())

    def get_last_query(self) -> Optional[str]:
        """Get the last raw query string sent to the provider.

        Returns:
            The URL and parameters of the last request, or None
        """
        return self._last_query

    @abstractmethod
    def search(self, query: Query) -> Iterator[Document]:
        """Execute a search query and yield results.

        This is the main method that provider implementations must override.
        It should handle pagination, rate limiting, and error recovery internally.

        Args:
            query: Query object with search parameters

        Yields:
            Document objects matching the query

        Raises:
            ProviderError: On provider-specific errors
            RateLimitError: When rate limit is exceeded
            NetworkError: On network/connectivity issues

        Example:
            >>> provider = MyProvider(config)
            >>> query = Query(text="machine learning", year_min=2020)
            >>> for doc in provider.search(query):
            ...     print(doc.title)
        """
        pass

    @abstractmethod
    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """Translate Query object to provider-specific parameters.

        Subclasses must implement this to convert the generic Query object
        into the specific format required by the provider's API.

        Args:
            query: Generic query object

        Returns:
            Dictionary of provider-specific query parameters

        Example:
            >>> params = self._translate_query(query)
            >>> # OpenAlex: {"search": "ML", "filter": "publication_year:2020"}
            >>> # Crossref: {"query": "ML", "filter": "from-pub-date:2020"}
        """
        pass

    @abstractmethod
    def _normalize_response(self, raw: Dict[str, Any]) -> Optional[Document]:
        """Convert provider response to Document object.

        Subclasses must implement this to normalize provider-specific
        response formats into the standard Document model.

        Args:
            raw: Raw response data from provider

        Returns:
            Normalized Document object, or None if normalization fails

        Example:
            >>> raw = {"id": "W123", "title": "Paper", ...}
            >>> doc = self._normalize_response(raw)
            >>> assert isinstance(doc, Document)
        """
        pass

    def _make_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request with rate limiting and retry.

        This is a helper method that providers can use for making API requests.
        It handles rate limiting, retries, and common error conditions.

        Args:
            url: Request URL
            params: Query parameters
            headers: Request headers

        Returns:
            Parsed JSON response

        Raises:
            RateLimitError: When rate limit is exceeded
            NetworkError: On network errors
            AuthenticationError: On authentication failures
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
            raise RateLimitError(
                self.name,
                f"Rate limit timeout for {self.name}",
            )

        # Prepare headers
        request_headers = {
            "User-Agent": f'SimpleSLR/1.0 ({self.config.mailto or ""})',
        }
        if headers:
            request_headers.update(headers)

        # Make request with retry
        try:
            response = self._execute_request(url, params, request_headers)
            return dict(response.json())
        except requests.exceptions.JSONDecodeError as e:
            raise ProviderError(self.name, f"Invalid JSON response: {e}", url=url)

    @retry_with_backoff(max_retries=3, base_delay=1.0, backoff_factor=2.0)
    def _execute_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> Any:
        """Execute HTTP request with retries.

        This method is decorated with retry logic and will automatically
        retry on transient failures.

        Args:
            url: Request URL
            params: Query parameters
            headers: Request headers

        Returns:
            Response object

        Raises:
            RateLimitError: On 429 status
            AuthenticationError: On 401/403 status
            NetworkError: On other HTTP errors
        """
        import requests

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.timeout,
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise RateLimitError(
                    self.name,
                    retry_after=retry_after,
                )

            # Handle authentication errors
            if response.status_code in (401, 403):
                raise AuthenticationError(
                    self.name,
                    "Authentication failed - check API key",
                    status_code=response.status_code,
                )

            # Handle server errors (retry these)
            if response.status_code >= 500:
                raise NetworkError(
                    self.name,
                    f"Server error: {response.status_code}",
                    status_code=response.status_code,
                )

            # Raise for other errors
            response.raise_for_status()

            return response

        except requests.exceptions.Timeout:
            raise NetworkError(
                self.name,
                f"Request timeout after {self.config.timeout}s",
            )
        except requests.exceptions.ConnectionError as e:
            raise NetworkError(
                self.name,
                f"Connection error: {e}",
            )
        except requests.exceptions.RequestException as e:
            raise ProviderError(
                self.name,
                f"Request failed: {e}",
            )

    def _build_filters(self, query: Query) -> Dict[str, Any]:
        """Build common filters from Query object.

        Helper method to extract common filter parameters like year range,
        language, etc. Providers can override or extend this.

        Args:
            query: Query object

        Returns:
            Dictionary of filter parameters
        """
        filters: Dict[str, Any] = {}

        if query.year_min is not None:
            filters["year_min"] = query.year_min

        if query.year_max is not None:
            filters["year_max"] = query.year_max

        if query.language:
            filters["language"] = query.language

        return filters

    def validate_config(self) -> bool:
        """Validate provider configuration.

        Subclasses can override this to add provider-specific validation.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        if self.config.rate_limit <= 0:
            raise ValueError("rate_limit must be positive")

        if self.config.timeout <= 0:
            raise ValueError("timeout must be positive")

        return True

    def __repr__(self) -> str:
        """String representation of provider."""
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"rate_limit={self.config.rate_limit}, "
            f"enabled={self.config.enabled}"
            ")"
        )


class ProviderRegistry:
    """Registry for managing provider instances.

    This class provides a central registry for all available providers,
    allowing lookup by name and batch operations.

    Example:
        >>> registry = ProviderRegistry()
        >>> registry.register("openalex", openalex_provider)
        >>> provider = registry.get("openalex")
        >>> for name in registry.list_providers():
        ...     print(name)
    """

    def __init__(self) -> None:
        """Initialize the provider registry."""
        self._providers: Dict[str, BaseProvider] = {}
        logger.debug("Initialized provider registry")

    def register(self, name: str, provider: BaseProvider) -> None:
        """Register a provider instance.

        Args:
            name: Provider name (e.g., 'openalex', 'crossref')
            provider: Provider instance

        Raises:
            ValueError: If provider is already registered
            TypeError: If provider is not a BaseProvider instance
        """
        if not isinstance(provider, BaseProvider):
            raise TypeError("provider must be a BaseProvider instance")

        if name in self._providers:
            logger.warning(f"Overwriting existing provider: {name}")

        self._providers[name] = provider
        logger.info(f"Registered provider: {name}")

    def unregister(self, name: str) -> None:
        """Unregister a provider.

        Args:
            name: Provider name to remove

        Raises:
            KeyError: If provider not found
        """
        if name not in self._providers:
            raise KeyError(f"Provider not found: {name}")

        del self._providers[name]
        logger.info(f"Unregistered provider: {name}")

    def get(self, name: str) -> BaseProvider:
        """Get a provider by name.

        Args:
            name: Provider name

        Returns:
            Provider instance

        Raises:
            KeyError: If provider not found
        """
        if name not in self._providers:
            raise KeyError(
                f"Provider '{name}' not found. " f"Available: {list(self._providers.keys())}"
            )

        return self._providers[name]

    def list_providers(self) -> List[str]:
        """List all registered provider names.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    def get_enabled_providers(self) -> List[BaseProvider]:
        """Get all enabled provider instances.

        Returns:
            List of enabled providers
        """
        return [provider for provider in self._providers.values() if provider.config.enabled]

    def clear(self) -> None:
        """Clear all registered providers."""
        self._providers.clear()
        logger.info("Cleared all providers from registry")

    def __len__(self) -> int:
        """Get number of registered providers."""
        return len(self._providers)

    def __contains__(self, name: str) -> bool:
        """Check if provider is registered."""
        return name in self._providers

    def __repr__(self) -> str:
        """String representation of registry."""
        return f"ProviderRegistry(providers={list(self._providers.keys())})"


# Global registry instance
_global_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    """Get the global provider registry.

    Returns:
        Global ProviderRegistry instance

    Example:
        >>> registry = get_registry()
        >>> providers = registry.list_providers()
    """
    return _global_registry
