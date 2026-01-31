"""
Export module for Simple SLR.

This module provides exporters for converting documents and clusters
to various output formats (CSV, BibTeX, JSONL, JSON).

Main classes:
    - CSVExporter: Export to CSV format
    - BibTeXExporter: Export to BibTeX format
    - JSONLExporter: Export to JSONL (JSON Lines) format
    - JSONExporter: Export to standard JSON format
    - BaseExporter: Base class for custom exporters

Example:
    >>> from nexus.export import CSVExporter, BibTeXExporter
    >>> from nexus.core.models import Document
    >>>
    >>> # Export to CSV
    >>> csv_exporter = CSVExporter(output_dir="outputs")
    >>> csv_exporter.export_documents(documents, "results.csv")
    >>>
    >>> # Export to BibTeX
    >>> bib_exporter = BibTeXExporter(output_dir="outputs")
    >>> bib_exporter.export_documents(documents, "references.bib")
"""

from nexus.export.base import BaseExporter, ExportError, ExportValidationError, ExportWriteError
from nexus.export.bibtex_exporter import BibTeXExporter
from nexus.export.csv_exporter import CSVExporter
from nexus.export.jsonl_exporter import JSONExporter, JSONLExporter
from nexus.export.ris_exporter import RISExporter

__all__ = [
    # Base classes
    "BaseExporter",
    "ExportError",
    "ExportValidationError",
    "ExportWriteError",
    # Exporters
    "CSVExporter",
    "BibTeXExporter",
    "JSONLExporter",
    "JSONExporter",
    "RISExporter",
    # Helper
    "get_exporter",
]


def get_exporter(format_name: str) -> BaseExporter:
    """Get an exporter instance for the specified format.

    Args:
        format_name: Export format name (bibtex, csv, jsonl, json, ris, endnote)

    Returns:
        Exporter instance

    Raises:
        ValueError: If format is not supported
    """
    format_map = {
        "bibtex": BibTeXExporter,
        "bib": BibTeXExporter,
        "csv": CSVExporter,
        "jsonl": JSONLExporter,
        "json": JSONExporter,
        "ris": RISExporter,
        "endnote": RISExporter,
    }

    format_lower = format_name.lower()

    if format_lower not in format_map:
        raise ValueError(
            f"Unknown format '{format_name}'. "
            "Supported formats: bibtex, csv, jsonl, json, ris"
        )

    exporter_class = format_map[format_lower]
    return exporter_class()


