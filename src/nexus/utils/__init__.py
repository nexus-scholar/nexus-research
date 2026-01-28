"""
Utility modules for Simple SLR.

This package contains utility functions and classes for:
- Exception handling
- Retry logic with backoff
- Rate limiting
- Logging configuration
- Configuration management (coming soon)
"""

from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    DeduplicationError,
    ExportError,
    NetworkError,
    ProviderConfigError,
    ProviderError,
    ProviderNotFoundError,
    QueryError,
    RateLimitError,
    SLRException,
    ValidationError,
)
from .logging import (
    ColoredFormatter,
    LogContext,
    PerformanceLogger,
    configure_library_logging,
    create_session_log_file,
    get_logger,
    log_function_call,
    setup_logging,
    setup_provider_logging,
)
from .rate_limit import RateLimitDecorator, SlidingWindowRateLimiter, TokenBucket
from .retry import (
    RetryableOperation,
    retry_on_rate_limit,
    retry_with_backoff,
    retry_with_custom_strategy,
)

__all__ = [
    # Exceptions
    "SLRException",
    "ProviderError",
    "RateLimitError",
    "AuthenticationError",
    "NetworkError",
    "ProviderNotFoundError",
    "ProviderConfigError",
    "DeduplicationError",
    "ValidationError",
    "ConfigurationError",
    "ExportError",
    "QueryError",
    # Retry utilities
    "retry_with_backoff",
    "retry_on_rate_limit",
    "retry_with_custom_strategy",
    "RetryableOperation",
    # Rate limiting
    "TokenBucket",
    "SlidingWindowRateLimiter",
    "RateLimitDecorator",
    # Logging
    "setup_logging",
    "get_logger",
    "setup_provider_logging",
    "configure_library_logging",
    "LogContext",
    "PerformanceLogger",
    "log_function_call",
    "create_session_log_file",
    "ColoredFormatter",
]
