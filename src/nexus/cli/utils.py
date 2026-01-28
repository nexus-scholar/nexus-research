"""
Shared CLI utilities.

This module provides common utilities used across CLI commands.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import click
import yaml
from pydantic import ValidationError

from nexus.core.config import SLRConfig
from nexus.core.models import Document
from nexus.cli.formatting import console, print_error


def load_config(config_path: Optional[Path] = None) -> SLRConfig:
    """Load configuration from file or use defaults.

    Args:
        config_path: Path to config file (YAML). If None, looks for nexus.yml or config.yml

    Returns:
        Loaded and validated SLRConfig

    Raises:
        click.ClickException: If config is invalid
    """
    if config_path is None:
        # Look for nexus.yml first, then config.yml
        config_path = Path("nexus.yml")
        if not config_path.exists():
            fallback = Path("config.yml")
            if fallback.exists():
                config_path = fallback
            else:
                # Use defaults
                return SLRConfig()

    if not config_path.exists():
        raise click.ClickException(f"Config file not found: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        return SLRConfig(**config_data)
    except ValidationError as e:
        print_error(f"Invalid configuration: {e}")
        raise click.ClickException("Configuration validation failed")
    except Exception as e:
        raise click.ClickException(f"Error loading config: {e}")


def load_queries(queries_path: Path) -> Any:
    """Load queries from YAML or JSON file.

    Args:
        queries_path: Path to queries file

    Returns:
        Loaded queries data structure (dict or list)

    Raises:
        click.ClickException: If file cannot be loaded
    """
    if not queries_path.exists():
        raise click.ClickException(f"Queries file not found: {queries_path}")

    try:
        with open(queries_path, "r", encoding="utf-8") as f:
            if queries_path.suffix in (".yml", ".yaml"):
                queries = yaml.safe_load(f)
            elif queries_path.suffix == ".json":
                queries = json.load(f)
            else:
                raise click.ClickException(
                    f"Unsupported queries file format: {queries_path.suffix}"
                )

        if not isinstance(queries, (dict, list)):
             raise click.ClickException("Queries file must contain a dictionary or list")

        return queries
    except Exception as e:
        raise click.ClickException(f"Error loading queries: {e}")


def load_documents(input_path: Path) -> List[Document]:
    """Load documents from JSONL or CSV file.

    Args:
        input_path: Path to input file

    Returns:
        List of Document objects

    Raises:
        click.ClickException: If file cannot be loaded
    """
    if not input_path.exists():
        raise click.ClickException(f"Input file not found: {input_path}")

    documents = []

    try:
        if input_path.suffix == ".jsonl":
            with open(input_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        doc = Document(**data)
                        documents.append(doc)
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: Skipping invalid document at line {line_num}: {e}[/yellow]"
                        )

        elif input_path.suffix == ".csv":
            import pandas as pd
            df = pd.read_csv(input_path)
            for _, row in df.iterrows():
                try:
                    # Convert row to dict and create Document
                    data = row.to_dict()
                    # Handle NaN values
                    data = {k: (v if pd.notna(v) else None) for k, v in data.items()}
                    doc = Document(**data)
                    documents.append(doc)
                except Exception as e:
                    console.print(f"[yellow]Warning: Skipping invalid row: {e}[/yellow]")

        else:
            raise click.ClickException(
                f"Unsupported input format: {input_path.suffix} (use .jsonl or .csv)"
            )

        return documents

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error loading documents: {e}")


def load_documents_from_directory(input_dir: Path) -> List[Document]:
    """Load all documents from a directory (typically search output).

    Args:
        input_dir: Directory containing provider output folders

    Returns:
        List of all documents from all providers

    Raises:
        click.ClickException: If directory cannot be read
    """
    if not input_dir.exists():
        raise click.ClickException(f"Input directory not found: {input_dir}")

    if not input_dir.is_dir():
        raise click.ClickException(f"Not a directory: {input_dir}")

    all_documents = []

    # Look for provider directories or all_results files
    for provider_dir in input_dir.iterdir():
        if not provider_dir.is_dir():
            continue

        # Skip dedup directories to avoid self-ingestion
        if "dedup" in provider_dir.name.lower():
            continue

        # Look for all_results.jsonl
        all_results = provider_dir / "all_results.jsonl"
        if all_results.exists():
            try:
                docs = load_documents(all_results)
                all_documents.extend(docs)
                console.print(
                    f"  Loaded {len(docs):,} documents from {provider_dir.name}"
                )
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Error loading {all_results}: {e}[/yellow]"
                )

    if not all_documents:
        raise click.ClickException(
            f"No documents found in {input_dir}. "
            "Make sure the directory contains provider output folders."
        )

    return all_documents


def save_documents(
    documents: List[Document],
    output_path: Path,
    format: str = "jsonl"
) -> None:
    """Save documents to file.

    Args:
        documents: List of documents to save
        output_path: Output file path
        format: Output format (jsonl, csv, json)

    Raises:
        click.ClickException: If save fails
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "jsonl":
            with open(output_path, "w", encoding="utf-8") as f:
                for doc in documents:
                    f.write(doc.model_dump_json() + "\n")

        elif format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    [doc.model_dump() for doc in documents],
                    f,
                    indent=2,
                    ensure_ascii=False
                )

        elif format == "csv":
            import pandas as pd
            df = pd.DataFrame([doc.model_dump() for doc in documents])
            df.to_csv(output_path, index=False)

        else:
            raise click.ClickException(f"Unsupported format: {format}")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error saving documents: {e}")


def generate_run_id() -> str:
    """Generate a timestamp-based run ID.

    Returns:
        Run ID string (e.g., 'run_2025-11-15_143022')
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"run_{timestamp}"


def generate_dedup_id() -> str:
    """Generate a timestamp-based dedup ID.

    Returns:
        Dedup ID string (e.g., 'dedup_2025-11-15_143022')
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"dedup_{timestamp}"


def save_metadata(
    output_dir: Path,
    metadata: Dict[str, Any],
    filename: str = "metadata.json"
) -> None:
    """Save metadata to JSON file.

    Args:
        output_dir: Output directory
        metadata: Metadata dictionary
        filename: Metadata filename
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = output_dir / filename

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)

    except Exception as e:
        console.print(f"[yellow]Warning: Could not save metadata: {e}[/yellow]")


def setup_logging(verbose: int = 0, quiet: bool = False) -> None:
    """Set up logging based on verbosity level.

    Args:
        verbose: Verbosity level (0=WARNING, 1=INFO, 2+=DEBUG)
        quiet: If True, suppress all non-error output
    """
    import logging

    if quiet:
        level = logging.ERROR
    elif verbose == 0:
        level = logging.WARNING
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )


def validate_output_format(ctx, param, value: str) -> str:
    """Validate output format parameter.

    Args:
        ctx: Click context
        param: Click parameter
        value: Format value

    Returns:
        Validated format string

    Raises:
        click.BadParameter: If format is invalid
    """
    valid_formats = {"csv", "jsonl", "json", "both", "all"}
    if value.lower() not in valid_formats:
        raise click.BadParameter(
            f"Invalid format '{value}'. Must be one of: {', '.join(valid_formats)}"
        )
    return value.lower()


def get_latest_run(base_dir: Path, prefix: str = "run_") -> Optional[Path]:
    """Get the most recent run directory.

    Args:
        base_dir: Base directory to search
        prefix: Directory name prefix

    Returns:
        Path to latest run directory, or None if not found
    """
    if not base_dir.exists():
        return None

    runs = [d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    if not runs:
        return None

    # Sort by timestamp in name
    runs.sort(reverse=True)
    return runs[0]

