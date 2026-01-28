"""
Exception hierarchy for Simple SLR.

This module defines a comprehensive exception hierarchy for handling
various error scenarios in the SLR framework.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


class SLRException(Exception):
    """Base exception for all SLR errors.

    All custom exceptions in the SLR framework inherit from this class.
    Provides common functionality for error details and timestamps.
    """

    def __init__(self, message: str, details: Optional[Dict] = None):
        """Initialize the exception.

        Args:
            message: Human-readable error message
            details: Optional dictionary with additional error context
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc)

    def __str__(self) -> str:
        """String representation of the exception."""
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message

    def to_dict(self) -> Dict:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class ProviderError(SLRException):
    """Provider-related errors.

    Base class for all errors that occur when interacting with
    external data providers (OpenAlex, Crossref, arXiv, S2).
    """

    def __init__(self, provider: str, message: str, **kwargs: Any) -> None:
        """Initialize the provider error.

        Args:
            provider: Name of the provider (e.g., 'openalex', 'crossref')
            message: Human-readable error message
            **kwargs: Additional details to store
        """
        super().__init__(f"[{provider}] {message}", kwargs)
        self.provider = provider


class RateLimitError(ProviderError):
    """Hit API rate limit.

    Raised when a provider's rate limit is exceeded.
    Should trigger retry logic with backoff.
    """

    def __init__(
        self,
        provider: str,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the rate limit error.

        Args:
            provider: Name of the provider
            message: Human-readable error message
            retry_after: Optional seconds to wait before retrying
            **kwargs: Additional details
        """
        super().__init__(provider, message, retry_after=retry_after, **kwargs)
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    """API key invalid or missing.

    Raised when authentication with a provider fails.
    This is typically a fatal error that won't be resolved by retrying.
    """

    def __init__(
        self, provider: str, message: str = "Authentication failed", **kwargs: Any
    ) -> None:
        """Initialize the authentication error.

        Args:
            provider: Name of the provider
            message: Human-readable error message
            **kwargs: Additional details
        """
        super().__init__(provider, message, **kwargs)


class NetworkError(ProviderError):
    """Network/timeout issues.

    Raised when network connectivity issues occur.
    Should trigger retry logic.
    """

    def __init__(
        self,
        provider: str,
        message: str = "Network error",
        status_code: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the network error.

        Args:
            provider: Name of the provider
            message: Human-readable error message
            status_code: Optional HTTP status code
            **kwargs: Additional details
        """
        super().__init__(provider, message, status_code=status_code, **kwargs)
        self.status_code = status_code


class ProviderNotFoundError(ProviderError):
    """Provider not found or not registered.

    Raised when attempting to use a provider that doesn't exist
    or hasn't been registered in the provider registry.
    """

    def __init__(self, provider: str, message: str = "Provider not found", **kwargs: Any) -> None:
        """Initialize the provider not found error.

        Args:
            provider: Name of the provider
            message: Human-readable error message
            **kwargs: Additional details
        """
        super().__init__(provider, message, **kwargs)


class ProviderConfigError(ProviderError):
    """Provider configuration error.

    Raised when a provider's configuration is invalid or incomplete.
    """

    def __init__(
        self, provider: str, message: str = "Invalid configuration", **kwargs: Any
    ) -> None:
        """Initialize the provider config error.

        Args:
            provider: Name of the provider
            message: Human-readable error message
            **kwargs: Additional details
        """
        super().__init__(provider, message, **kwargs)


class DeduplicationError(SLRException):
    """Deduplication failed.

    Raised when the deduplication process encounters an error.
    """

    def __init__(self, message: str = "Deduplication failed", **kwargs: Any) -> None:
        """Initialize the deduplication error.

        Args:
            message: Human-readable error message
            **kwargs: Additional details
        """
        super().__init__(message, kwargs)


class ValidationError(SLRException):
    """Data validation failed.

    Raised when input data fails validation checks.
    """

    def __init__(
        self, message: str = "Validation failed", field: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Initialize the validation error.

        Args:
            message: Human-readable error message
            field: Optional name of the field that failed validation
            **kwargs: Additional details
        """
        details = kwargs
        if field:
            details["field"] = field
        super().__init__(message, details)
        self.field = field


class ConfigurationError(SLRException):
    """Configuration error.

    Raised when the application configuration is invalid or incomplete.
    """

    def __init__(
        self,
        message: str = "Configuration error",
        config_key: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the configuration error.

        Args:
            message: Human-readable error message
            config_key: Optional configuration key that caused the error
            **kwargs: Additional details
        """
        details = kwargs
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, details)
        self.config_key = config_key


class ExportError(SLRException):
    """Export operation failed.

    Raised when exporting data to a file or format fails.
    """

    def __init__(
        self, message: str = "Export failed", format: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Initialize the export error.

        Args:
            message: Human-readable error message
            format: Optional export format (e.g., 'csv', 'bibtex')
            **kwargs: Additional details
        """
        details = kwargs
        if format:
            details["format"] = format
        super().__init__(message, details)
        self.format = format


class QueryError(SLRException):
    """Query parsing or execution failed.

    Raised when a search query is invalid or cannot be executed.
    """

    def __init__(
        self, message: str = "Query error", query: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Initialize the query error.

        Args:
            message: Human-readable error message
            query: Optional query string that caused the error
            **kwargs: Additional details
        """
        details = kwargs
        if query:
            details["query"] = query
        super().__init__(message, details)
        self.query = query
