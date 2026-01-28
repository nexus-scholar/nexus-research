"""
CSV exporter for Simple SLR.

This module provides functionality for exporting documents and clusters
to CSV format, suitable for analysis in spreadsheet applications.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexus.core.models import Document, DocumentCluster
from nexus.export.base import BaseExporter, ExportWriteError


class CSVExporter(BaseExporter):
    """Exporter for CSV format.

    This exporter converts documents and clusters to CSV format,
    flattening complex metadata into columns suitable for spreadsheet analysis.

    Features:
    - Automatic column mapping
    - Metadata flattening
    - Author list formatting
    - External IDs expansion
    - Cluster information

    Example:
        >>> from nexus.export import CSVExporter
        >>> from nexus.core.models import Document
        >>>
        >>> exporter = CSVExporter(output_dir="outputs")
        >>> exporter.export_documents(documents, "results.csv")
        PosixPath('outputs/results.csv')
    """

    @property
    def file_extension(self) -> str:
        """Get file extension for CSV files."""
        return "csv"

    def export_documents(
        self,
        documents: List[Document],
        output_file: str,
        include_raw: bool = False,
        **kwargs
    ) -> Path:
        """Export documents to CSV file.

        Args:
            documents: List of documents to export
            output_file: Name of output file (will add .csv if needed)
            include_raw: Whether to include raw provider data (not recommended)
            **kwargs: Additional CSV writer options

        Returns:
            Path to created CSV file

        Raises:
            ExportWriteError: If writing to file fails
        """
        if not output_file.endswith('.csv'):
            output_file = f"{output_file}.csv"

        output_path = self._get_output_path(output_file)

        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                if documents:
                    # Get fieldnames from first document
                    fieldnames = self._get_fieldnames(documents[0], include_raw)
                    writer = csv.DictWriter(f, fieldnames=fieldnames, **kwargs)
                    writer.writeheader()

                    for doc in documents:
                        row = self._document_to_row(doc, include_raw)
                        writer.writerow(row)
                else:
                    # Write empty CSV with standard headers
                    fieldnames = self._get_default_fieldnames()
                    writer = csv.DictWriter(f, fieldnames=fieldnames, **kwargs)
                    writer.writeheader()

        except IOError as e:
            raise ExportWriteError(f"Failed to write CSV file: {e}") from e

        return output_path

    def export_clusters(
        self,
        clusters: List[DocumentCluster],
        output_file: str,
        mode: str = "representatives",
        **kwargs
    ) -> Path:
        """Export document clusters to CSV file.

        Args:
            clusters: List of document clusters to export
            output_file: Name of output file (will add .csv if needed)
            mode: Export mode - "representatives" (one row per cluster) or
                  "all" (one row per document with cluster info)
            **kwargs: Additional CSV writer options

        Returns:
            Path to created CSV file

        Raises:
            ExportWriteError: If writing to file fails
        """
        if not output_file.endswith('.csv'):
            output_file = f"{output_file}.csv"

        output_path = self._get_output_path(output_file)

        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                if mode == "representatives":
                    self._write_cluster_representatives(f, clusters, **kwargs)
                elif mode == "all":
                    self._write_all_cluster_members(f, clusters, **kwargs)
                else:
                    raise ValueError(f"Invalid mode: {mode}. Use 'representatives' or 'all'")

        except IOError as e:
            raise ExportWriteError(f"Failed to write CSV file: {e}") from e

        return output_path

    def _write_cluster_representatives(
        self, file, clusters: List[DocumentCluster], **kwargs
    ):
        """Write cluster representatives to CSV."""
        if not clusters:
            # Write empty CSV with cluster headers
            fieldnames = self._get_default_fieldnames() + self._get_cluster_fieldnames()
            writer = csv.DictWriter(file, fieldnames=fieldnames, **kwargs)
            writer.writeheader()
            return

        # Get fieldnames from first cluster's representative
        base_fieldnames = self._get_fieldnames(clusters[0].representative, include_raw=False)
        cluster_fieldnames = self._get_cluster_fieldnames()
        fieldnames = base_fieldnames + cluster_fieldnames

        writer = csv.DictWriter(file, fieldnames=fieldnames, **kwargs)
        writer.writeheader()

        for cluster in clusters:
            row = self._document_to_row(cluster.representative, include_raw=False)
            row.update(self._cluster_to_row(cluster))
            writer.writerow(row)

    def _write_all_cluster_members(
        self, file, clusters: List[DocumentCluster], **kwargs
    ):
        """Write all cluster members to CSV with cluster info."""
        if not clusters:
            fieldnames = self._get_default_fieldnames() + ['cluster_id']
            writer = csv.DictWriter(file, fieldnames=fieldnames, **kwargs)
            writer.writeheader()
            return

        # Collect all documents from all clusters
        all_docs = []
        for cluster in clusters:
            all_docs.extend(cluster.members)

        if not all_docs:
            return

        base_fieldnames = self._get_fieldnames(all_docs[0], include_raw=False)
        # cluster_id is already in the document
        fieldnames = base_fieldnames

        writer = csv.DictWriter(file, fieldnames=fieldnames, **kwargs)
        writer.writeheader()

        for doc in all_docs:
            row = self._document_to_row(doc, include_raw=False)
            writer.writerow(row)

    def _document_to_row(self, doc: Document, include_raw: bool = False) -> Dict[str, Any]:
        """Convert a Document to a CSV row dictionary.

        Args:
            doc: Document to convert
            include_raw: Whether to include raw data

        Returns:
            Dictionary suitable for CSV writer
        """
        row = {
            'title': doc.title or '',
            'year': doc.year or '',
            'provider': doc.provider or '',
            'provider_id': doc.provider_id or '',
            'abstract': doc.abstract or '',
            'venue': doc.venue or '',
            'url': doc.url or '',
            'language': doc.language or '',
            'cited_by_count': doc.cited_by_count or '',
            'query_id': doc.query_id or '',
            'query_text': doc.query_text or '',
            'retrieved_at': doc.retrieved_at.isoformat() if doc.retrieved_at else '',
            'cluster_id': doc.cluster_id if doc.cluster_id is not None else '',
        }

        # Add authors
        row['authors'] = self._format_authors(doc.authors)
        row['author_count'] = len(doc.authors)

        # Add external IDs
        row['doi'] = doc.external_ids.doi or ''
        row['arxiv_id'] = doc.external_ids.arxiv_id or ''
        row['pubmed_id'] = doc.external_ids.pubmed_id or ''
        row['openalex_id'] = doc.external_ids.openalex_id or ''
        row['s2_id'] = doc.external_ids.s2_id or ''

        if include_raw and doc.raw_data:
            row['raw_data'] = str(doc.raw_data)

        return row

    def _cluster_to_row(self, cluster: DocumentCluster) -> Dict[str, Any]:
        """Convert cluster metadata to CSV row fields.

        Args:
            cluster: Document cluster

        Returns:
            Dictionary with cluster-specific fields
        """
        return {
            'cluster_size': cluster.size,
            'cluster_confidence': cluster.confidence,
            'cluster_dois': '; '.join(cluster.all_dois),
            'cluster_arxiv_ids': '; '.join(cluster.all_arxiv_ids),
            'cluster_providers': '; '.join(f"{k}({v})" for k, v in cluster.provider_counts.items()),
        }

    def _format_authors(self, authors: List) -> str:
        """Format author list as string.

        Args:
            authors: List of Author objects

        Returns:
            Semicolon-separated author names
        """
        if not authors:
            return ''

        author_strs = []
        for author in authors:
            if hasattr(author, 'full_name'):
                author_strs.append(author.full_name)
            else:
                author_strs.append(str(author))

        return '; '.join(author_strs)

    def _get_fieldnames(self, doc: Document, include_raw: bool = False) -> List[str]:
        """Get CSV field names from a document.

        Args:
            doc: Sample document
            include_raw: Whether to include raw data field

        Returns:
            List of field names
        """
        fieldnames = [
            'title',
            'year',
            'authors',
            'author_count',
            'venue',
            'abstract',
            'provider',
            'provider_id',
            'doi',
            'arxiv_id',
            'pubmed_id',
            'openalex_id',
            's2_id',
            'url',
            'language',
            'cited_by_count',
            'query_id',
            'query_text',
            'retrieved_at',
            'cluster_id',
        ]

        if include_raw:
            fieldnames.append('raw_data')

        return fieldnames

    def _get_default_fieldnames(self) -> List[str]:
        """Get default field names for empty CSV."""
        return [
            'title',
            'year',
            'authors',
            'author_count',
            'venue',
            'abstract',
            'provider',
            'provider_id',
            'doi',
            'arxiv_id',
            'pubmed_id',
            'openalex_id',
            's2_id',
            'url',
            'language',
            'cited_by_count',
            'query_id',
            'query_text',
            'retrieved_at',
            'cluster_id',
        ]

    def _get_cluster_fieldnames(self) -> List[str]:
        """Get field names for cluster-specific columns."""
        return [
            'cluster_size',
            'cluster_confidence',
            'cluster_dois',
            'cluster_arxiv_ids',
            'cluster_providers',
        ]

