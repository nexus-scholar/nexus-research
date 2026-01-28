"""
Base exporter classes for Simple SLR.

This module provides the base infrastructure for exporting documents
to various formats (CSV, BibTeX, JSONL, etc.).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from nexus.core.models import Document, DocumentCluster


class BaseExporter(ABC):
    """Base class for all exporters.

    This abstract class defines the interface that all exporters must implement.
    Exporters are responsible for converting documents and clusters to specific
    output formats and writing them to files.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize the exporter.

        Args:
            output_dir: Directory to write output files. If None, uses current directory.
        """
        self.output_dir = Path(output_dir) if output_dir else Path("")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def export_documents(
        self, documents: List[Document], output_file: str, **kwargs
    ) -> Path:
        """Export a list of documents to a file.

        Args:
            documents: List of documents to export
            output_file: Name of the output file (without path)
            **kwargs: Format-specific options

        Returns:
            Path to the created file
        """
        pass

    @abstractmethod
    def export_clusters(
        self, clusters: List[DocumentCluster], output_file: str, **kwargs
    ) -> Path:
        """Export document clusters to a file.

        Args:
            clusters: List of document clusters to export
            output_file: Name of the output file (without path)
            **kwargs: Format-specific options

        Returns:
            Path to the created file
        """
        pass

    def _get_output_path(self, filename: str) -> Path:
        """Get the full output path for a filename.

        Args:
            filename: Name of the output file

        Returns:
            Full path to the output file
        """
        return self.output_dir / filename

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Get the file extension for this exporter (e.g., 'csv', 'bib')."""
        pass


class ExportError(Exception):
    """Base exception for export-related errors."""
    pass


class ExportValidationError(ExportError):
    """Exception raised when export data validation fails."""
    pass


class ExportWriteError(ExportError):
    """Exception raised when writing to output file fails."""
    pass

