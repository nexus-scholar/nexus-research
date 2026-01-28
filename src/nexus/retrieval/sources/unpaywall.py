import requests
from pathlib import Path
from nexus.retrieval.sources.base import PDFSource
from nexus.core.models import Document

class UnpaywallSource(PDFSource):
    """Fetcher using Unpaywall API."""

    @property
    def name(self) -> str:
        return "unpaywall"

    def fetch(self, doc: Document, output_path: Path) -> bool:
        if not doc.external_ids.doi:
            return False
            
        email = self.config.get("email", "unpaywall@example.com")
        url = f"https://api.unpaywall.org/v2/{doc.external_ids.doi}?email={email}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                best_loc = data.get("best_oa_location", {})
                pdf_url = best_loc.get("url_for_pdf") or best_loc.get("url")
                
                if pdf_url:
                    return self._download_file(pdf_url, output_path)
        except Exception:
            pass
            
        return False
