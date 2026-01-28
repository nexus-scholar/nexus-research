"""
Core functionality for Simple SLR.

This package contains core models, configuration, and base classes
for the SLR framework.
"""

from .config import (
    ClassificationConfig,
    ClassificationMethod,
    DeduplicationConfig,
    DeduplicationStrategy,
    OutputConfig,
    ProviderConfig,
    ProvidersConfig,
    SLRConfig,
    create_default_config,
    load_config,
    load_config_from_dict,
    merge_configs,
    save_config,
)

__all__ = [
    # Configuration
    "SLRConfig",
    "ProviderConfig",
    "ProvidersConfig",
    "DeduplicationConfig",
    "ClassificationConfig",
    "OutputConfig",
    "DeduplicationStrategy",
    "ClassificationMethod",
    # Config utilities
    "load_config",
    "load_config_from_dict",
    "create_default_config",
    "save_config",
    "merge_configs",
]
