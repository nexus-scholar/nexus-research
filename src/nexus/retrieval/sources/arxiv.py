import requests
from pathlib import Path
from nexus.retrieval.sources.base import PDFSource
from nexus.core.models import Document

class ArXivSource(PDFSource):
    """Fetcher for ArXiv papers."""

    @property
    def name(self) -> str:
        return "arxiv"

    def fetch(self, doc: Document, output_path: Path) -> bool:
        arxiv_id = doc.external_ids.arxiv_id
        if not arxiv_id:
            return False

        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        return self._download_file(url, output_path)
