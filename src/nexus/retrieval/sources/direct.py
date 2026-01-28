from pathlib import Path
from nexus.retrieval.sources.base import PDFSource
from nexus.core.models import Document

class DirectSource(PDFSource):
    """Fetcher that tries the document URL directly if it looks like a PDF."""

    @property
    def name(self) -> str:
        return "direct"

    def fetch(self, doc: Document, output_path: Path) -> bool:
        # Check main URL
        if doc.url and doc.url.lower().endswith(".pdf"):
            return self._download_file(doc.url, output_path)
            
        # Check raw_data for open_access_url (common in OpenAlex raw)
        # We can't easily access raw_data unless we passed it through, 
        # but Document model excludes it from JSON serialization usually.
        # If it's in memory, we might have it.
        
        return False
