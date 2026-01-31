"""
RIS exporter for Simple SLR.

This module provides functionality for exporting documents to RIS format,
which is widely supported by reference managers like EndNote, Zotero, and Mendeley.
"""

from pathlib import Path
from typing import List, Optional

from nexus.core.models import Document, DocumentCluster
from nexus.export.base import BaseExporter, ExportWriteError


class RISExporter(BaseExporter):
    """Exporter for RIS format.

    This exporter converts documents to RIS tags, ensuring compatibility
    with EndNote and other reference managers.

    Features:
    - Standard RIS tag mapping
    - Author list formatting (one per line)
    - Multiline notes support
    - Automatic type detection

    Example:
        >>> from nexus.export import RISExporter
        >>> exporter = RISExporter(output_dir="outputs")
        >>> exporter.export_documents(documents, "references.ris")
    """

    @property
    def file_extension(self) -> str:
        """Get file extension for RIS files."""
        return "ris"

    def export_documents(
        self,
        documents: List[Document],
        output_file: str,
        **kwargs
    ) -> Path:
        """Export documents to RIS file.

        Args:
            documents: List of documents to export
            output_file: Name of output file (will add .ris if needed)
            **kwargs: Additional options

        Returns:
            Path to created RIS file

        Raises:
            ExportWriteError: If writing to file fails
        """
        if not output_file.endswith('.ris'):
            output_file = f"{output_file}.ris"

        output_path = self._get_output_path(output_file)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for doc in documents:
                    entry = self._document_to_ris(doc)
                    f.write(entry)
                    f.write("\n\n")

        except IOError as e:
            raise ExportWriteError(f"Failed to write RIS file: {e}") from e

        return output_path

    def export_clusters(
        self,
        clusters: List[DocumentCluster],
        output_file: str,
        **kwargs
    ) -> Path:
        """Export cluster representatives to RIS file."""
        representatives = [cluster.representative for cluster in clusters]
        return self.export_documents(representatives, output_file, **kwargs)

    def _document_to_ris(self, doc: Document) -> str:
        """Convert a document to RIS entry string."""
        lines = []

        # Type (TY) - Must be first
        ty = self._determine_ris_type(doc)
        lines.append(f"TY  - {ty}")

        # Title (TI or T1)
        if doc.title:
            lines.append(f"TI  - {doc.title}")

        # Authors (AU) - One per line
        if doc.authors:
            for author in doc.authors:
                if hasattr(author, 'family_name'):
                    name = author.family_name
                    if hasattr(author, 'given_name') and author.given_name:
                        # Prefer "Family, Given" for RIS
                        lines.append(f"AU  - {name}, {author.given_name}")
                    else:
                        lines.append(f"AU  - {name}")
                elif hasattr(author, 'full_name') and author.full_name:
                     # Fallback if family_name is missing but full_name exists (unlikely given Author model)
                    lines.append(f"AU  - {author.full_name}")
                else:
                    lines.append(f"AU  - {str(author)}")

        # Year (PY)
        if doc.year:
            lines.append(f"PY  - {doc.year}")

        # Venue/Journal (JO/JF/T2)
        if doc.venue:
            if ty == "JOUR":
                lines.append(f"JO  - {doc.venue}")
            else:
                lines.append(f"T2  - {doc.venue}")

        # Abstract (AB)
        if doc.abstract:
            lines.append(f"AB  - {doc.abstract}")

        # DOI (DO)
        if doc.external_ids.doi:
            lines.append(f"DO  - {doc.external_ids.doi}")

        # URL (UR)
        if doc.url:
            lines.append(f"UR  - {doc.url}")

        # Custom Fields / Notes
        if doc.provider:
            lines.append(f"DB  - {doc.provider}")
        
        if doc.external_ids.arxiv_id:
            lines.append(f"C1  - arXiv: {doc.external_ids.arxiv_id}")

        # End of Record (ER) - Must be last
        lines.append("ER  -")

        return "\n".join(lines)

    def _determine_ris_type(self, doc: Document) -> str:
        """Determine RIS reference type."""
        venue_lower = (doc.venue or '').lower()

        if any(x in venue_lower for x in ['journal', 'review', 'transaction']):
            return 'JOUR'
        
        if any(x in venue_lower for x in ['conference', 'proceedings', 'symposium']):
            return 'CONF'
        
        if doc.external_ids.doi:
            return 'JOUR'  # Default to Journal for DOI-bearing items if unsure
        
        return 'GEN'  # Generic
