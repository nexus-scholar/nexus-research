"""
Retry utilities with exponential backoff.

This module provides decorators and utilities for retrying operations
that may fail transiently (e.g., network requests, rate-limited APIs).
"""

import logging
import time
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type, TypeVar

from .exceptions import NetworkError, RateLimitError

# Type variable for generic function signatures
T = TypeVar("T")

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (NetworkError, RateLimitError),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """Decorator for retrying failed operations with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds before first retry (default: 1.0)
        backoff_factor: Multiplier for delay after each retry (default: 2.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exceptions: Tuple of exception types to catch and retry
            (default: NetworkError, RateLimitError)
        on_retry: Optional callback function called before each retry
            with (exception, attempt_number)

    Returns:
        Decorated function that retries on specified exceptions

    Example:
        >>> @retry_with_backoff(max_retries=3, base_delay=1.0)
        ... def fetch_data():
        ...     # Your code that might fail
        ...     return requests.get(url)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = base_delay
            last_exception: Optional[Exception] = None
            func_name = getattr(func, "__name__", repr(func))

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    # Don't sleep after the last attempt
                    if attempt < max_retries - 1:
                        # Calculate delay with exponential backoff
                        current_delay = min(delay, max_delay)

                        # Log the retry attempt
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func_name}: {e}. "
                            f"Retrying in {current_delay:.2f}s..."
                        )

                        # Call the on_retry callback if provided
                        if on_retry:
                            on_retry(e, attempt + 1)

                        # Sleep before retrying
                        time.sleep(current_delay)

                        # Increase delay for next attempt
                        delay *= backoff_factor
                    else:
                        logger.error(f"All {max_retries} attempts failed for {func_name}: {e}")

            # All retries exhausted, raise the last exception
            if last_exception:
                raise last_exception

            # This should never happen, but mypy needs it
            raise RuntimeError("Retry logic failed unexpectedly")

        return wrapper

    return decorator


def retry_on_rate_limit(
    max_retries: int = 5,
    base_delay: float = 5.0,
    backoff_factor: float = 2.0,
) -> Callable:
    """Specialized retry decorator for rate limit errors.

    This is a convenience wrapper around retry_with_backoff specifically
    configured for handling rate limit errors with more conservative settings.

    Args:
        max_retries: Maximum number of retry attempts (default: 5)
        base_delay: Initial delay in seconds (default: 5.0)
        backoff_factor: Multiplier for delay after each retry (default: 2.0)

    Returns:
        Decorated function that retries on RateLimitError

    Example:
        >>> @retry_on_rate_limit(max_retries=5)
        ... def search_api(query):
        ...     return api.search(query)
    """

    def on_retry(exception: Exception, attempt: int) -> None:
        """Handle rate limit specific retry logic."""
        if isinstance(exception, RateLimitError) and exception.retry_after:
            # If the API tells us when to retry, use that
            logger.info(f"Rate limit hit. API suggests waiting {exception.retry_after}s")

    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=base_delay,
        backoff_factor=backoff_factor,
        max_delay=300.0,  # Max 5 minutes
        exceptions=(RateLimitError,),
        on_retry=on_retry,
    )


def retry_with_custom_strategy(
    should_retry: Callable[[Exception], bool],
    get_delay: Callable[[int], float],
    max_retries: int = 3,
) -> Callable:
    """Advanced retry decorator with custom retry strategy.

    Allows full control over retry logic by providing custom functions
    to determine whether to retry and how long to wait.

    Args:
        should_retry: Function that takes an exception and returns True if should retry
        get_delay: Function that takes attempt number and returns delay in seconds
        max_retries: Maximum number of retry attempts

    Returns:
        Decorated function with custom retry logic

    Example:
        >>> def my_should_retry(e):
        ...     return isinstance(e, (NetworkError, TimeoutError))
        >>>
        >>> def my_get_delay(attempt):
        ...     return attempt * 2  # Linear backoff
        >>>
        >>> @retry_with_custom_strategy(my_should_retry, my_get_delay)
        ... def my_function():
        ...     pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            func_name = getattr(func, "__name__", repr(func))

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if we should retry this exception
                    if not should_retry(e):
                        logger.debug(f"{func_name} failed with non-retryable error: {e}")
                        raise

                    # Don't sleep after the last attempt
                    if attempt < max_retries - 1:
                        delay = get_delay(attempt + 1)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func_name}: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_retries} attempts failed for {func_name}: {e}")

            # All retries exhausted
            if last_exception:
                raise last_exception

            raise RuntimeError("Retry logic failed unexpectedly")

        return wrapper

    return decorator


class RetryableOperation:
    """Context manager for retryable operations.

    Provides a more explicit way to wrap retryable code blocks
    without using decorators.

    Example:
        >>> with RetryableOperation(max_retries=3) as retry:
        ...     data = fetch_data()
        ...     retry.success()
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        exceptions: Tuple[Type[Exception], ...] = (NetworkError, RateLimitError),
    ):
        """Initialize the retryable operation.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay in seconds
            backoff_factor: Multiplier for delay after each retry
            exceptions: Tuple of exception types to catch and retry
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff_factor = backoff_factor
        self.exceptions = exceptions
        self.attempt = 0
        self._success = False

    def __enter__(self) -> "RetryableOperation":
        """Enter the context manager."""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> bool:
        """Exit the context manager and handle retries."""
        # If no exception or operation was successful, return
        if exc_type is None or self._success:
            return True

        # If exception is not retryable, re-raise
        if not isinstance(exc_val, self.exceptions):
            return False

        # If we've exhausted retries, re-raise
        if self.attempt >= self.max_retries:
            logger.error(f"All {self.max_retries} attempts exhausted")
            return False

        # Calculate delay and sleep
        delay = self.base_delay * (self.backoff_factor**self.attempt)
        logger.warning(
            f"Attempt {self.attempt + 1} failed: {exc_val}. " f"Retrying in {delay:.2f}s..."
        )
        time.sleep(delay)
        self.attempt += 1

        # Suppress the exception to continue
        return True

    def success(self) -> None:
        """Mark the operation as successful."""
        self._success = True
