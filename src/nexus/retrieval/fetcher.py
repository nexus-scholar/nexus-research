from pathlib import Path
import logging
from typing import List, Optional, Dict, Any

from nexus.core.models import Document
from nexus.retrieval.sources.base import PDFSource
from nexus.retrieval.sources.arxiv import ArXivSource
from nexus.retrieval.sources.openalex import OpenAlexSource
from nexus.retrieval.sources.unpaywall import UnpaywallSource
from nexus.retrieval.sources.direct import DirectSource

logger = logging.getLogger(__name__)

class PDFFetcher:
    """Manager for PDF retrieval from multiple sources."""

    def __init__(self, output_dir: Path, config: Dict[str, Any] = None):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or {}
        
        # Sources in priority order
        self.sources: List[PDFSource] = [
            DirectSource(self.config),
            ArXivSource(self.config),
            UnpaywallSource(self.config),
            OpenAlexSource(self.config),
        ]

    def get_filename(self, doc: Document) -> str:
        """Generate a safe filename for the document."""
        # Prioritize DOI
        if doc.external_ids.doi:
            safe_doi = doc.external_ids.doi.replace("/", "_").replace(":", "_")
            return f"{safe_doi}.pdf"
        
        # Fallback to ArXiv ID
        if doc.external_ids.arxiv_id:
            return f"arxiv_{doc.external_ids.arxiv_id}.pdf"
            
        # Fallback to Title hash
        return f"doc_{abs(hash(doc.title))}.pdf"

    def fetch(self, doc: Document) -> bool:
        """
        Attempt to download PDF for the document from available sources.
        
        Returns:
            True if successful, False otherwise.
        """
        filename = self.get_filename(doc)
        output_path = self.output_dir / filename
        
        if output_path.exists():
            logger.info(f"PDF already exists: {filename}")
            return True

        for source in self.sources:
            try:
                if source.fetch(doc, output_path):
                    logger.info(f"Downloaded {filename} from {source.name}")
                    return True
            except Exception as e:
                logger.warning(f"Failed to fetch from {source.name}: {e}")
                
        return False
