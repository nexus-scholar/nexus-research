"""
Logging configuration for Simple SLR.

This module provides utilities for setting up structured logging
across the SLR framework with consistent formatting and levels.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

# Default log format
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DETAILED_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - " "[%(filename)s:%(lineno)d] - %(message)s"
)
JSON_FORMAT = "%(asctime)s|%(name)s|%(levelname)s|%(message)s"


class ColoredFormatter(logging.Formatter):
    """Colored log formatter for console output.

    Adds color codes to log levels for better visibility in terminals.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors."""
        # Add color to levelname
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"

        result = super().format(record)

        # Reset levelname for other formatters
        record.levelname = levelname

        return result


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
    colored: bool = True,
    include_timestamp: bool = True,
) -> logging.Logger:
    """Setup logging configuration for the SLR framework.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file (logs to console if None)
        format_string: Custom format string (uses DEFAULT_FORMAT if None)
        colored: Use colored output for console logging
        include_timestamp: Include timestamps in log messages

    Returns:
        Configured root logger

    Example:
        >>> logger = setup_logging(level="DEBUG", log_file=Path("slr.log"))
        >>> logger.info("Application started")
    """
    # Get root logger
    root_logger = logging.getLogger()

    # Clear existing handlers
    root_logger.handlers.clear()

    # Set level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Determine format
    if format_string is None:
        format_string = (
            DEFAULT_FORMAT if include_timestamp else "%(name)s - %(levelname)s - %(message)s"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    console_formatter: Union[ColoredFormatter, logging.Formatter]
    if colored and sys.stdout.isatty():
        console_formatter = ColoredFormatter(format_string)
    else:
        console_formatter = logging.Formatter(format_string)

    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(numeric_level)

        # Use detailed format for file logs
        file_formatter = logging.Formatter(DETAILED_FORMAT)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Get a logger instance with the specified name.

    Args:
        name: Logger name (typically __name__ of the module)
        level: Optional logging level override

    Returns:
        Logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing started")
    """
    logger = logging.getLogger(name)

    if level:
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(numeric_level)

    return logger


def setup_provider_logging(provider_name: str, level: str = "INFO") -> logging.Logger:
    """Setup logging for a specific provider.

    Args:
        provider_name: Name of the provider (e.g., 'openalex', 'crossref')
        level: Logging level for this provider

    Returns:
        Logger instance for the provider

    Example:
        >>> logger = setup_provider_logging("openalex", "DEBUG")
        >>> logger.debug("Fetching page 1")
    """
    logger_name = f"slr.providers.{provider_name}"
    logger = logging.getLogger(logger_name)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    return logger


def configure_library_logging(quiet: bool = False) -> None:
    """Configure logging for third-party libraries.

    Reduces noise from verbose libraries like urllib3, requests, etc.

    Args:
        quiet: If True, set libraries to WARNING level; else INFO
    """
    library_level = logging.WARNING if quiet else logging.INFO

    # Common noisy libraries
    noisy_loggers = [
        "urllib3",
        "requests",
        "httpx",
        "httpcore",
        "charset_normalizer",
    ]

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(library_level)


class LogContext:
    """Context manager for temporary log level changes.

    Example:
        >>> with LogContext("slr.providers", "DEBUG"):
        ...     # Temporarily enable debug logging for providers
        ...     fetch_data()
    """

    def __init__(self, logger_name: str, level: str):
        """Initialize the context manager.

        Args:
            logger_name: Name of the logger to modify
            level: Temporary logging level
        """
        self.logger = logging.getLogger(logger_name)
        self.original_level = self.logger.level
        self.new_level = getattr(logging, level.upper(), logging.INFO)

    def __enter__(self) -> logging.Logger:
        """Enter the context and change log level."""
        self.logger.setLevel(self.new_level)
        return self.logger

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context and restore original log level."""
        self.logger.setLevel(self.original_level)


class PerformanceLogger:
    """Context manager for logging operation performance.

    Example:
        >>> with PerformanceLogger("Fetching papers"):
        ...     papers = fetch_papers()
        # Output: "Fetching papers completed in 2.34s"
    """

    def __init__(
        self, operation: str, logger: Optional[logging.Logger] = None, level: str = "INFO"
    ):
        """Initialize the performance logger.

        Args:
            operation: Description of the operation
            logger: Logger instance (uses root logger if None)
            level: Log level for the message
        """
        self.operation = operation
        self.logger = logger or logging.getLogger()
        self.level = getattr(logging, level.upper(), logging.INFO)
        self.start_time: Optional[float] = None

    def __enter__(self) -> "PerformanceLogger":
        """Enter the context and start timing."""
        import time

        self.start_time = time.perf_counter()
        self.logger.log(self.level, f"{self.operation} started")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context and log elapsed time."""
        import time

        if self.start_time is not None:
            elapsed = time.perf_counter() - self.start_time
            if exc_type is None:
                self.logger.log(self.level, f"{self.operation} completed in {elapsed:.2f}s")
            else:
                self.logger.log(
                    logging.ERROR, f"{self.operation} failed after {elapsed:.2f}s: {exc_val}"
                )


def log_function_call(
    logger: Optional[logging.Logger] = None,
    level: str = "DEBUG",
    include_args: bool = True,
    include_result: bool = False,
) -> Any:
    """Decorator to log function calls.

    Args:
        logger: Logger instance (uses function's module logger if None)
        level: Log level for the messages
        include_args: Log function arguments
        include_result: Log function return value

    Example:
        >>> @log_function_call(level="INFO")
        ... def fetch_papers(query):
        ...     return api.search(query)
    """

    def decorator(func: Any) -> Any:
        import functools

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get logger
            func_logger = logger or logging.getLogger(func.__module__)
            log_level = getattr(logging, level.upper(), logging.DEBUG)

            # Build log message
            func_name = func.__name__
            if include_args:
                args_str = ", ".join(repr(a) for a in args)
                kwargs_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
                params = ", ".join(filter(None, [args_str, kwargs_str]))
                func_logger.log(log_level, f"Calling {func_name}({params})")
            else:
                func_logger.log(log_level, f"Calling {func_name}")

            # Execute function
            result = func(*args, **kwargs)

            # Log result if requested
            if include_result:
                func_logger.log(log_level, f"{func_name} returned {result!r}")
            else:
                func_logger.log(log_level, f"{func_name} completed")

            return result

        return wrapper

    return decorator


def create_session_log_file(base_dir: Path, prefix: str = "slr") -> Path:
    """Create a timestamped log file for the current session.

    Args:
        base_dir: Directory to create the log file in
        prefix: Prefix for the log filename

    Returns:
        Path to the created log file

    Example:
        >>> log_file = create_session_log_file(Path("logs"))
        >>> setup_logging(log_file=log_file)
    """
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = base_dir / f"{prefix}_{timestamp}.log"

    return log_file
