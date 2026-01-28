"""
Configuration management for Simple SLR.

This module provides configuration models and utilities for loading
and validating configuration from YAML files, environment variables,
and programmatic sources.
"""

import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeduplicationStrategy(str, Enum):
    """Deduplication strategy options."""

    CONSERVATIVE = "conservative"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class ClassificationMethod(str, Enum):
    """Classification method options."""

    HEURISTIC = "heuristic"
    ML = "ml"
    ENSEMBLE = "ensemble"


class ProviderConfig(BaseModel):
    """Configuration for a single provider."""

    enabled: bool = True
    rate_limit: float = Field(default=1.0, gt=0, le=100, description="Requests per second")
    timeout: int = Field(default=30, gt=0, le=300, description="Request timeout in seconds")
    api_key: Optional[str] = Field(default=None, description="API key if required")
    mailto: Optional[str] = Field(default=None, description="Email for polite crawling")

    model_config = ConfigDict(
        extra="allow",  # Allow provider-specific fields
        str_strip_whitespace=True,
    )


class ProvidersConfig(BaseModel):
    """Configuration for all providers."""

    openalex: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(enabled=True, rate_limit=5.0)
    )
    crossref: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(enabled=True, rate_limit=1.0)
    )
    arxiv: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(enabled=True, rate_limit=0.5)
    )
    semantic_scholar: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(enabled=False, rate_limit=1.0), alias="s2"
    )

    model_config = ConfigDict(
        extra="allow",  # Allow additional providers
        populate_by_name=True,  # Allow alias "s2" for semantic_scholar
    )

    def get_enabled_providers(self) -> List[str]:
        """Get list of enabled provider names."""
        enabled = []
        for name, config in self.model_dump().items():
            if isinstance(config, dict) and config.get("enabled", False):
                enabled.append(name)
        return enabled

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider."""
        return getattr(self, name, None)


class DeduplicationConfig(BaseModel):
    """Configuration for deduplication."""

    strategy: DeduplicationStrategy = Field(
        default=DeduplicationStrategy.CONSERVATIVE, description="Deduplication strategy"
    )
    fuzzy_threshold: int = Field(
        default=97, ge=0, le=100, description="Fuzzy matching threshold (0-100)"
    )
    max_year_gap: int = Field(default=1, ge=0, description="Maximum year difference for duplicates")
    # Semantic settings (future)
    semantic_threshold: float = Field(
        default=0.92, ge=0.0, le=1.0, description="Semantic similarity threshold"
    )
    embedding_model: str = Field(
        default="allenai/specter2", description="Embedding model for semantic deduplication"
    )
    use_embeddings: bool = Field(
        default=False, description="Enable semantic embeddings (requires additional dependencies)"
    )

    model_config = ConfigDict(extra="forbid")


class ClassificationConfig(BaseModel):
    """Configuration for classification (future feature)."""

    enabled: bool = Field(default=False, description="Enable classification")
    method: ClassificationMethod = Field(
        default=ClassificationMethod.HEURISTIC, description="Classification method"
    )
    confidence_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum confidence for classification"
    )

    model_config = ConfigDict(extra="forbid")


class OutputConfig(BaseModel):
    """Configuration for output settings."""

    directory: Path = Field(default=Path("outputs"), description="Output directory for results")
    format: str = Field(default="csv", description="Output format (csv, jsonl, both)")
    include_raw: bool = Field(default=False, description="Include raw provider response in output")

    model_config = ConfigDict(extra="allow")

    @field_validator("directory")
    @classmethod
    def validate_directory(cls, v: Path) -> Path:
        """Convert to Path and ensure it's a directory path."""
        return Path(v)

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate output format."""
        valid_formats = {"csv", "jsonl", "both", "json"}
        if v.lower() not in valid_formats:
            raise ValueError(f"format must be one of {valid_formats}")
        return v.lower()


class SLRConfig(BaseModel):
    """Main configuration for Simple SLR."""

    # General settings
    mailto: Optional[str] = Field(default=None, description="Email for polite API crawling")
    year_min: Optional[int] = Field(default=None, description="Minimum publication year")
    year_max: Optional[int] = Field(default=None, description="Maximum publication year")
    language: str = Field(default="en", description="Document language filter")

    # Component configurations
    providers: ProvidersConfig = Field(
        default_factory=ProvidersConfig, description="Provider configurations"
    )
    deduplication: DeduplicationConfig = Field(
        default_factory=DeduplicationConfig, description="Deduplication settings"
    )
    classification: ClassificationConfig = Field(
        default_factory=ClassificationConfig, description="Classification settings"
    )
    output: OutputConfig = Field(default_factory=OutputConfig, description="Output settings")

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
    )

    @field_validator("year_min", "year_max")
    @classmethod
    def validate_year(cls, v: Optional[int]) -> Optional[int]:
        """Validate year is reasonable."""
        if v is None:
            return v
        if v < 1900 or v > 2100:
            raise ValueError("Year must be between 1900 and 2100")
        return v

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization validation."""
        # Validate year range
        if self.year_min and self.year_max and self.year_min > self.year_max:
            raise ValueError("year_min cannot be greater than year_max")

        # Propagate mailto to providers if not set
        if self.mailto:
            for provider_name in ["openalex", "crossref", "arxiv", "semantic_scholar"]:
                provider = getattr(self.providers, provider_name, None)
                if provider and not provider.mailto:
                    provider.mailto = self.mailto


def load_config(config_path: Path) -> SLRConfig:
    """Load configuration from a YAML file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Validated SLRConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid

    Example:
        >>> config = load_config(Path("config.yml"))
        >>> print(config.providers.openalex.rate_limit)
        5.0
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Load YAML
    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}

    # Expand environment variables
    expanded_config = _expand_env_vars(raw_config)

    # Create and validate config
    try:
        config = SLRConfig(**expanded_config)
    except Exception as e:
        raise ValueError(f"Invalid configuration: {e}") from e

    return config


def load_config_from_dict(config_dict: Dict[str, Any]) -> SLRConfig:
    """Load configuration from a dictionary.

    Args:
        config_dict: Configuration dictionary

    Returns:
        Validated SLRConfig instance

    Example:
        >>> config = load_config_from_dict({"mailto": "user@example.com"})
    """
    # Expand environment variables
    expanded_config = _expand_env_vars(config_dict)

    return SLRConfig(**expanded_config)


def create_default_config(output_path: Path) -> SLRConfig:
    """Create a default configuration and optionally save it.

    Args:
        output_path: Path to save the default configuration

    Returns:
        Default SLRConfig instance

    Example:
        >>> config = create_default_config(Path("config.yml"))
    """
    config = SLRConfig()

    if output_path:
        save_config(config, output_path)

    return config


def save_config(config: SLRConfig, output_path: Path) -> None:
    """Save configuration to a YAML file.

    Args:
        config: SLRConfig instance to save
        output_path: Path to save the configuration

    Example:
        >>> config = SLRConfig(mailto="user@example.com")
        >>> save_config(config, Path("config.yml"))
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict - serialize enums as their values
    config_dict = config.model_dump(exclude_none=True)

    # Manually convert enums and Path objects to strings
    def convert_special_types(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: convert_special_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_special_types(item) for item in obj]
        elif isinstance(obj, Enum):
            return obj.value
        elif isinstance(obj, Path):
            return str(obj)
        else:
            return obj

    config_dict = convert_special_types(config_dict)

    # Write YAML
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            config_dict,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def _expand_env_vars(config: Any) -> Any:
    """Recursively expand environment variables in config.

    Supports ${VAR_NAME} and ${VAR_NAME:-default} syntax.

    Args:
        config: Configuration object (dict, list, or str)

    Returns:
        Configuration with environment variables expanded
    """
    if isinstance(config, dict):
        return {k: _expand_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_expand_env_vars(item) for item in config]
    elif isinstance(config, str):
        # Check for ${VAR} or ${VAR:-default} pattern
        import re

        def replace_env_var(match: Any) -> str:
            var_expr = match.group(1)

            # Check for default value syntax: VAR:-default
            if ":-" in var_expr:
                var_name, default = var_expr.split(":-", 1)
                return str(os.getenv(var_name.strip(), default.strip()))
            else:
                var_name = var_expr.strip()
                value = os.getenv(var_name)
                if value is None:
                    # Keep original if env var not found
                    return str(match.group(0))
                return str(value)

        pattern = r"\$\{([^}]+)\}"
        return re.sub(pattern, replace_env_var, config)
    else:
        return config


def merge_configs(base: SLRConfig, override: Dict[str, Any]) -> SLRConfig:
    """Merge override configuration into base configuration.

    Args:
        base: Base SLRConfig instance
        override: Dictionary with override values

    Returns:
        New SLRConfig with merged values

    Example:
        >>> base = SLRConfig()
        >>> override = {"year_min": 2020, "providers": {"openalex": {"enabled": False}}}
        >>> merged = merge_configs(base, override)
    """
    # Convert base to dict
    base_dict = base.model_dump()

    # Deep merge
    merged = _deep_merge(base_dict, override)

    return SLRConfig(**merged)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Override dictionary

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result
