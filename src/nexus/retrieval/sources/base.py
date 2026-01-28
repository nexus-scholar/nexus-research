from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import time

import requests
from nexus.core.models import Document

HEADERS_PDF = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
}

class PDFSource(ABC):
    """Abstract base class for PDF sources."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def fetch(self, doc: Document, output_path: Path) -> bool:
        """
        Attempt to fetch the PDF for the given document.
        
        Args:
            doc: The document metadata.
            output_path: The full path where the PDF should be saved.
            
        Returns:
            True if download was successful, False otherwise.
        """
        pass

    def _download_file(self, url: str, output_path: Path, timeout: int = 30, retries: int = 2) -> bool:
        """Helper to download a file with headers, validation, and retries."""
        for attempt in range(retries + 1):
            try:
                response = requests.get(url, headers=HEADERS_PDF, timeout=timeout, stream=True, allow_redirects=True)
                
                if response.status_code == 200:
                    # Basic content type check
                    ctype = response.headers.get("Content-Type", "").lower()
                    if "text/html" in ctype:
                        # Probably a landing page, not a PDF
                        return False
                        
                    # Download to temp file to verify content
                    temp_path = output_path.with_suffix(".tmp")
                    with open(temp_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Verify PDF magic bytes
                    with open(temp_path, "rb") as f:
                        header = f.read(4)
                    
                    if header == b"%PDF":
                        temp_path.replace(output_path)
                        return True
                    else:
                        temp_path.unlink(missing_ok=True)
                        # Invalid content
                        pass
                
            except Exception:
                if attempt < retries:
                    time.sleep(1)
                else:
                    pass
                    
        return False
