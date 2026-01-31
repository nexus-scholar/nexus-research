"""
JSONL (JSON Lines) exporter for Simple SLR.

This module provides functionality for exporting documents to JSONL format,
suitable for data pipelines, machine learning, and programmatic processing.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from nexus.core.models import Document, DocumentCluster
from nexus.export.base import BaseExporter, ExportWriteError


class JSONLExporter(BaseExporter):
    """Exporter for JSONL (JSON Lines) format.

    This exporter converts documents to JSONL format, with one JSON object
    per line. This format is efficient for streaming processing and is
    commonly used in data pipelines.

    Features:
    - One JSON object per line
    - Preserves full document structure
    - Optional raw data inclusion
    - Efficient for large datasets
    - Easy to stream/process

    Example:
        >>> from nexus.export import JSONLExporter
        >>> from nexus.core.models import Document
        >>>
        >>> exporter = JSONLExporter(output_dir="outputs")
        >>> exporter.export_documents(documents, "results.jsonl")
        PosixPath('outputs/results.jsonl')
    """

    @property
    def file_extension(self) -> str:
        """Get file extension for JSONL files."""
        return "jsonl"

    def export_documents(
        self,
        documents: List[Document],
        output_file: str,
        include_raw: bool = False,
        indent: bool = False,
        **kwargs
    ) -> Path:
        """Export documents to JSONL file.

        Args:
            documents: List of documents to export
            output_file: Name of output file (will add .jsonl if needed)
            include_raw: Whether to include raw provider data
            indent: Whether to pretty-print JSON (not recommended for JSONL)
            **kwargs: Additional JSON encoder options

        Returns:
            Path to created JSONL file

        Raises:
            ExportWriteError: If writing to file fails
        """
        if not output_file.endswith('.jsonl'):
            output_file = f"{output_file}.jsonl"

        output_path = self._get_output_path(output_file)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for doc in documents:
                    json_obj = self._document_to_dict(doc, include_raw)

                    if indent:
                        # Pretty print (one object per line, but formatted)
                        json_str = json.dumps(json_obj, ensure_ascii=False, indent=2, **kwargs)
                    else:
                        # Standard JSONL (one compact object per line)
                        json_str = json.dumps(json_obj, ensure_ascii=False, **kwargs)

                    f.write(json_str)
                    f.write('\n')

        except IOError as e:
            raise ExportWriteError(f"Failed to write JSONL file: {e}") from e
        except (TypeError, ValueError) as e:
            raise ExportWriteError(f"Failed to serialize document to JSON: {e}") from e

        return output_path

    def export_clusters(
        self,
        clusters: List[DocumentCluster],
        output_file: str,
        mode: str = "representatives",
        include_raw: bool = False,
        **kwargs
    ) -> Path:
        """Export document clusters to JSONL file.

        Args:
            clusters: List of document clusters to export
            output_file: Name of output file (will add .jsonl if needed)
            mode: Export mode - "representatives", "all", or "clusters"
                  - representatives: One entry per cluster (representative only)
                  - all: One entry per document with cluster info
                  - clusters: One entry per cluster with all members
            include_raw: Whether to include raw provider data
            **kwargs: Additional JSON encoder options

        Returns:
            Path to created JSONL file

        Raises:
            ExportWriteError: If writing to file fails
        """
        if not output_file.endswith('.jsonl'):
            output_file = f"{output_file}.jsonl"

        output_path = self._get_output_path(output_file)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                if mode == "representatives":
                    for cluster in clusters:
                        json_obj = self._document_to_dict(
                            cluster.representative, include_raw
                        )
                        # Add cluster metadata
                        json_obj['cluster_metadata'] = self._cluster_metadata_to_dict(cluster)

                        json_str = json.dumps(json_obj, ensure_ascii=False, **kwargs)
                        f.write(json_str)
                        f.write('\n')

                elif mode == "all":
                    for cluster in clusters:
                        for doc in cluster.members:
                            json_obj = self._document_to_dict(doc, include_raw)
                            json_str = json.dumps(json_obj, ensure_ascii=False, **kwargs)
                            f.write(json_str)
                            f.write('\n')

                elif mode == "clusters":
                    for cluster in clusters:
                        json_obj = self._cluster_to_dict(cluster, include_raw)
                        json_str = json.dumps(json_obj, ensure_ascii=False, **kwargs)
                        f.write(json_str)
                        f.write('\n')
                else:
                    raise ValueError(
                        f"Invalid mode: {mode}. Use 'representatives', 'all', or 'clusters'"
                    )

        except IOError as e:
            raise ExportWriteError(f"Failed to write JSONL file: {e}") from e
        except (TypeError, ValueError) as e:
            raise ExportWriteError(f"Failed to serialize to JSON: {e}") from e

        return output_path

    def _document_to_dict(self, doc: Document, include_raw: bool = False) -> Dict[str, Any]:
        """Convert a Document to a dictionary.

        Args:
            doc: Document to convert
            include_raw: Whether to include raw provider data

        Returns:
            Dictionary representation of document
        """
        data = {
            'title': doc.title,
            'year': doc.year,
            'provider': doc.provider,
            'provider_id': doc.provider_id,
            'external_ids': {
                'doi': doc.external_ids.doi,
                'arxiv_id': doc.external_ids.arxiv_id,
                'pubmed_id': doc.external_ids.pubmed_id,
                'openalex_id': doc.external_ids.openalex_id,
                's2_id': doc.external_ids.s2_id,
            },
            'abstract': doc.abstract,
            'authors': [
                {
                    'family_name': author.family_name,
                    'given_name': author.given_name,
                    'orcid': author.orcid,
                }
                for author in doc.authors
            ],
            'venue': doc.venue,
            'url': doc.url,
            'language': doc.language,
            'cited_by_count': doc.cited_by_count,
            'query_id': doc.query_id,
            'query_text': doc.query_text,
            'retrieved_at': doc.retrieved_at.isoformat() if doc.retrieved_at else None,
            'cluster_id': doc.cluster_id,
        }

        if include_raw and doc.raw_data:
            data['raw_data'] = doc.raw_data

        return data

    def _cluster_to_dict(
        self, cluster: DocumentCluster, include_raw: bool = False
    ) -> Dict[str, Any]:
        """Convert a DocumentCluster to a dictionary.

        Args:
            cluster: Cluster to convert
            include_raw: Whether to include raw provider data

        Returns:
            Dictionary representation of cluster
        """
        return {
            'cluster_id': cluster.cluster_id,
            'size': cluster.size,
            'confidence': cluster.confidence,
            'representative': self._document_to_dict(cluster.representative, include_raw),
            'members': [
                self._document_to_dict(doc, include_raw)
                for doc in cluster.members
            ],
            'all_dois': cluster.all_dois,
            'all_arxiv_ids': cluster.all_arxiv_ids,
            'provider_counts': cluster.provider_counts,
        }

    def _cluster_metadata_to_dict(self, cluster: DocumentCluster) -> Dict[str, Any]:
        """Extract cluster metadata only.

        Args:
            cluster: Cluster to extract metadata from

        Returns:
            Dictionary with cluster metadata
        """
        return {
            'cluster_id': cluster.cluster_id,
            'size': cluster.size,
            'confidence': cluster.confidence,
            'all_dois': cluster.all_dois,
            'all_arxiv_ids': cluster.all_arxiv_ids,
            'provider_counts': cluster.provider_counts,
        }


class JSONExporter(JSONLExporter):
    """Exporter for standard JSON format (array of objects).

    This is a convenience class that exports to standard JSON array format
    instead of JSONL. Inherits from JSONLExporter and overrides export methods.
    
    Note: Uses stream writing to handle large datasets efficiently.

    Example:
        >>> from nexus.export import JSONExporter
        >>> exporter = JSONExporter(output_dir="outputs")
        >>> exporter.export_documents(documents, "results.json")
        PosixPath('outputs/results.json')
    """

    @property
    def file_extension(self) -> str:
        """Get file extension for JSON files."""
        return "json"

    def export_documents(
        self,
        documents: List[Document],
        output_file: str,
        include_raw: bool = False,
        indent: int = 2,
        **kwargs
    ) -> Path:
        """Export documents to JSON file (array format).

        Args:
            documents: List of documents to export
            output_file: Name of output file (will add .json if needed)
            include_raw: Whether to include raw provider data
            indent: Indentation level for pretty printing (default: 2)
            **kwargs: Additional JSON encoder options

        Returns:
            Path to created JSON file
        """
        if not output_file.endswith('.json'):
            output_file = f"{output_file}.json"

        output_path = self._get_output_path(output_file)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('[\n')
                
                for i, doc in enumerate(documents):
                    if i > 0:
                        f.write(',\n')
                    
                    json_obj = self._document_to_dict(doc, include_raw)
                    json_str = json.dumps(json_obj, ensure_ascii=False, indent=indent, **kwargs)
                    
                    # Indent the whole object if needed to fit inside the array
                    if indent:
                        prefix = " " * indent
                        json_str = "\n".join(prefix + line for line in json_str.split('\n'))
                    
                    f.write(json_str)

                f.write('\n]')

        except IOError as e:
            raise ExportWriteError(f"Failed to write JSON file: {e}") from e
        except (TypeError, ValueError) as e:
            raise ExportWriteError(f"Failed to serialize to JSON: {e}") from e

        return output_path

    def export_clusters(
        self,
        clusters: List[DocumentCluster],
        output_file: str,
        mode: str = "clusters",
        include_raw: bool = False,
        indent: int = 2,
        **kwargs
    ) -> Path:
        """Export clusters to JSON file (array format).

        Args:
            clusters: List of document clusters to export
            output_file: Name of output file (will add .json if needed)
            mode: Export mode - "representatives", "all", or "clusters"
            include_raw: Whether to include raw provider data
            indent: Indentation level for pretty printing
            **kwargs: Additional JSON encoder options

        Returns:
            Path to created JSON file
        """
        if not output_file.endswith('.json'):
            output_file = f"{output_file}.json"

        output_path = self._get_output_path(output_file)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('[\n')
                first = True

                if mode == "clusters":
                    for cluster in clusters:
                        if not first:
                            f.write(',\n')
                        first = False
                        
                        data = self._cluster_to_dict(cluster, include_raw)
                        self._write_json_item(f, data, indent, **kwargs)
                        
                elif mode == "representatives":
                    for cluster in clusters:
                        if not first:
                            f.write(',\n')
                        first = False

                        data = {
                            **self._document_to_dict(cluster.representative, include_raw),
                            'cluster_metadata': self._cluster_metadata_to_dict(cluster)
                        }
                        self._write_json_item(f, data, indent, **kwargs)

                elif mode == "all":
                    for cluster in clusters:
                        for doc in cluster.members:
                            if not first:
                                f.write(',\n')
                            first = False
                            
                            data = self._document_to_dict(doc, include_raw)
                            self._write_json_item(f, data, indent, **kwargs)
                else:
                    raise ValueError(
                        f"Invalid mode: {mode}. Use 'representatives', 'all', or 'clusters'"
                    )

                f.write('\n]')

        except IOError as e:
            raise ExportWriteError(f"Failed to write JSON file: {e}") from e
        except (TypeError, ValueError) as e:
            raise ExportWriteError(f"Failed to serialize to JSON: {e}") from e

        return output_path

    def _write_json_item(self, f, data: Any, indent: int, **kwargs):
        """Helper to write a single indented JSON item."""
        json_str = json.dumps(data, ensure_ascii=False, indent=indent, **kwargs)
        if indent:
            prefix = " " * indent
            json_str = "\n".join(prefix + line for line in json_str.split('\n'))
        f.write(json_str)

