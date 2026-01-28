"""
Rate limiting utilities for Simple SLR.

This module provides rate limiting mechanisms to control the frequency
of API requests and prevent exceeding provider rate limits.
"""

import logging
import time
from collections import deque
from threading import Lock, RLock
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket rate limiter.

    Implements the token bucket algorithm for rate limiting.
    Tokens are added at a constant rate, and operations consume tokens.
    If tokens are available, the operation proceeds; otherwise, it blocks or fails.

    This is thread-safe and can be used across multiple threads.

    Example:
        >>> limiter = TokenBucket(rate=10.0, capacity=20)
        >>> if limiter.consume(1):
        ...     make_api_call()
        ... else:
        ...     print("Rate limit exceeded")
    """

    def __init__(self, rate: float, capacity: int):
        """Initialize the token bucket.

        Args:
            rate: Rate at which tokens are added (tokens per second)
            capacity: Maximum number of tokens the bucket can hold (burst size)

        Raises:
            ValueError: If rate or capacity is not positive
        """
        if rate <= 0:
            raise ValueError(f"Rate must be positive, got {rate}")
        if capacity <= 0:
            raise ValueError(f"Capacity must be positive, got {capacity}")

        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self.lock = Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens without blocking.

        Args:
            tokens: Number of tokens to consume (default: 1)

        Returns:
            True if tokens were consumed, False if insufficient tokens

        Example:
            >>> limiter = TokenBucket(rate=10.0, capacity=20)
            >>> limiter.consume(5)
            True
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                logger.debug(f"Consumed {tokens} token(s), {self.tokens:.2f} remaining")
                return True

            logger.debug(f"Insufficient tokens: need {tokens}, have {self.tokens:.2f}")
            return False

    def wait_for_token(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Block until tokens are available or timeout occurs.

        Args:
            tokens: Number of tokens to wait for (default: 1)
            timeout: Maximum time to wait in seconds (None = wait forever)

        Returns:
            True if tokens were consumed, False if timeout occurred

        Example:
            >>> limiter = TokenBucket(rate=10.0, capacity=20)
            >>> limiter.wait_for_token(1, timeout=5.0)
            True
        """
        start_time = time.monotonic()

        while True:
            if self.consume(tokens):
                return True

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    logger.warning(f"Timeout waiting for {tokens} token(s)")
                    return False

            # Calculate sleep time based on token deficit
            with self.lock:
                self._refill()
                deficit = tokens - self.tokens
                if deficit > 0:
                    sleep_time = deficit / self.rate
                    # Cap sleep time to avoid long waits
                    sleep_time = min(sleep_time, 1.0)
                else:
                    sleep_time = 0.1

            time.sleep(sleep_time)

    def _refill(self) -> None:
        """Refill tokens based on elapsed time (must be called with lock held)."""
        now = time.monotonic()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        new_tokens = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_update = now

    def reset(self) -> None:
        """Reset the bucket to full capacity."""
        with self.lock:
            self.tokens = float(self.capacity)
            self.last_update = time.monotonic()
            logger.debug(f"Token bucket reset to {self.capacity} tokens")

    def available_tokens(self) -> float:
        """Get the current number of available tokens.

        Returns:
            Number of tokens currently available
        """
        with self.lock:
            self._refill()
            return self.tokens

    def time_until_tokens(self, tokens: int = 1) -> float:
        """Calculate time until the specified number of tokens will be available.

        Args:
            tokens: Number of tokens to wait for

        Returns:
            Time in seconds until tokens are available (0 if already available)
        """
        with self.lock:
            self._refill()
            deficit = tokens - self.tokens
            if deficit <= 0:
                return 0.0
            return deficit / self.rate


class SlidingWindowRateLimiter:
    """Sliding window rate limiter.

    Tracks request timestamps in a sliding time window.
    More memory-intensive than TokenBucket but provides exact rate limiting.

    Example:
        >>> limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=60)
        >>> if limiter.allow_request():
        ...     make_api_call()
    """

    def __init__(self, max_requests: int, window_seconds: float):
        """Initialize the sliding window rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds

        Raises:
            ValueError: If max_requests or window_seconds is not positive
        """
        if max_requests <= 0:
            raise ValueError(f"max_requests must be positive, got {max_requests}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {window_seconds}")

        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()
        self.lock = RLock()

    def allow_request(self) -> bool:
        """Check if a request is allowed and record it if so.

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        with self.lock:
            now = time.monotonic()
            self._cleanup_old_requests(now)

            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                logger.debug(
                    f"Request allowed: {len(self.requests)}/{self.max_requests} "
                    f"in last {self.window_seconds}s"
                )
                return True

            logger.debug(
                f"Request denied: {len(self.requests)}/{self.max_requests} "
                f"in last {self.window_seconds}s"
            )
            return False

    def wait_for_slot(self, timeout: Optional[float] = None) -> bool:
        """Wait until a request slot is available.

        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)

        Returns:
            True if slot became available, False if timeout occurred
        """
        start_time = time.monotonic()

        while True:
            if self.allow_request():
                return True

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    logger.warning("Timeout waiting for request slot")
                    return False

            # Calculate sleep time
            with self.lock:
                if self.requests:
                    oldest_request = self.requests[0]
                    time_until_slot = (oldest_request + self.window_seconds) - time.monotonic()
                    sleep_time = max(0.1, min(time_until_slot, 1.0))
                else:
                    sleep_time = 0.1

            time.sleep(sleep_time)

    def _cleanup_old_requests(self, now: float) -> None:
        """Remove requests outside the time window (must be called with lock held)."""
        cutoff = now - self.window_seconds
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

    def reset(self) -> None:
        """Reset the limiter, clearing all recorded requests."""
        with self.lock:
            self.requests.clear()
            logger.debug("Sliding window rate limiter reset")

    def current_usage(self) -> int:
        """Get the current number of requests in the window.

        Returns:
            Number of requests in the current window
        """
        with self.lock:
            self._cleanup_old_requests(time.monotonic())
            return len(self.requests)

    def time_until_slot(self) -> float:
        """Calculate time until a slot will be available.

        Returns:
            Time in seconds until a slot is available (0 if already available)
        """
        with self.lock:
            now = time.monotonic()
            self._cleanup_old_requests(now)

            if len(self.requests) < self.max_requests:
                return 0.0

            # Slot will be available when oldest request expires
            oldest_request = self.requests[0]
            return float(max(0.0, (oldest_request + self.window_seconds) - now))


class RateLimitDecorator:
    """Decorator for rate-limiting function calls.

    Can use either TokenBucket or SlidingWindow limiter.

    Example:
        >>> limiter = TokenBucket(rate=10.0, capacity=20)
        >>> @RateLimitDecorator(limiter)
        ... def api_call():
        ...     return requests.get(url)
    """

    def __init__(
        self,
        limiter: Any,
        wait: bool = True,
        timeout: Optional[float] = None,
        on_limit: Optional[Callable] = None,
    ):
        """Initialize the rate limit decorator.

        Args:
            limiter: TokenBucket or SlidingWindowRateLimiter instance
            wait: If True, wait for tokens; if False, raise exception
            timeout: Maximum time to wait (None = wait forever)
            on_limit: Optional callback when rate limit is hit
        """
        self.limiter = limiter
        self.wait = wait
        self.timeout = timeout
        self.on_limit = on_limit

    def __call__(self, func: Callable) -> Callable:
        """Decorate a function with rate limiting."""

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Try to acquire permission
            if isinstance(self.limiter, TokenBucket):
                if self.wait:
                    success = self.limiter.wait_for_token(1, self.timeout)
                else:
                    success = self.limiter.consume(1)
            elif isinstance(self.limiter, SlidingWindowRateLimiter):
                if self.wait:
                    success = self.limiter.wait_for_slot(self.timeout)
                else:
                    success = self.limiter.allow_request()
            else:
                raise TypeError(f"Unsupported limiter type: {type(self.limiter)}")

            if not success:
                if self.on_limit:
                    self.on_limit()
                from nexus.utils.exceptions import RateLimitError

                raise RateLimitError("rate_limiter", "Rate limit exceeded", function=func.__name__)

            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
