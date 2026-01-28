import requests
from pathlib import Path
from nexus.retrieval.sources.base import PDFSource
from nexus.core.models import Document

class OpenAlexSource(PDFSource):
    """Fetcher using OpenAlex API to find Open Access links."""

    @property
    def name(self) -> str:
        return "openalex"

    def fetch(self, doc: Document, output_path: Path) -> bool:
        if not doc.external_ids.doi:
            return False

        try:
            url = f"https://api.openalex.org/works/https://doi.org/{doc.external_ids.doi}"
            # Polite pool
            if self.config.get("email"):
                url += f"?mailto={self.config['email']}"
                
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                return False
                
            data = response.json()
            oa_url = data.get("open_access", {}).get("oa_url")
            
            if not oa_url:
                oa_url = data.get("best_oa_location", {}).get("pdf_url")

            if oa_url:
                return self._download_file(oa_url, output_path)
                    
        except Exception:
            pass
            
        return False
