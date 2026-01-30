import re
import logging
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse, urljoin
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from nexus.core.models import Document
from nexus.retrieval.sources.base import PDFSource
from nexus.retrieval.browser_auth import AUTH_FILE

logger = logging.getLogger(__name__)

# Suppress SSL warnings for proxy connection
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Regex to find the PDF meta tag

class SNDLSource(PDFSource):
    """Fetcher using Algerian National System of Online Documentation (SNDL) via Playwright."""

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    @property
    def name(self) -> str:
        return "sndl_browser"

    def _start_browser(self):
        """Initialize Playwright browser with auth state."""
        if self.browser:
            return

        self.playwright = sync_playwright().start()
        # Use Firefox and HEADFUL mode to bypass bot detection
        self.browser = self.playwright.firefox.launch(headless=False)
        
        if AUTH_FILE.exists():
            self.context = self.browser.new_context(storage_state=AUTH_FILE, ignore_https_errors=True)
            logger.info(f"Loaded SNDL session from {AUTH_FILE}")
        else:
            logger.warning("No auth.json found. SNDL fetch may fail.")
            self.context = self.browser.new_context(ignore_https_errors=True)
            
        self.page = self.context.new_page()

    def _close_browser(self):
        """Clean up browser resources."""
        if self.browser:
            self.browser.close()
            self.playwright.stop()
            self.browser = None

    def _rewrite_url_for_sndl(self, url: str) -> str:
        """Rewrite standard URL to SNDL proxy format."""
        parsed = urlparse(url)
        host = parsed.netloc
        
        if "sndl1.arn.dz" in host:
            return url
            
        # SNDL Rewriting Rule: replace dots with dashes, append proxy suffix
        new_host = host.replace(".", "-") + ".www.sndl1.arn.dz"
        return urlunparse((parsed.scheme, new_host, parsed.path, parsed.params, parsed.query, parsed.fragment))

    def fetch(self, doc: Document, output_path: Path) -> bool:
        if not doc.external_ids.doi:
            return False

        self._start_browser()
        doi_url = f"https://doi.org/{doc.external_ids.doi}"

        try:
            # 1. Resolve DOI to get real publisher URL (using requests is faster for this)
            try:
                # We use verify=False here too as redirects might pass through proxy logic
                resp = requests.head(doi_url, allow_redirects=True, timeout=10, verify=False)
                publisher_url = resp.url
            except:
                # Fallback
                return False

            # 2. Rewrite to SNDL
            target_url = self._rewrite_url_for_sndl(publisher_url)
            logger.warning(f"SNDL Debug: {publisher_url} -> {target_url}")

            # 3. Navigate & Trap Download
            try:
                # Listener for download event
                with self.page.expect_download(timeout=15000) as download_info:
                    # Navigate to the page
                    logger.warning(f"Navigating to: {target_url}")
                    self.page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                    
                    # Check for blocking
                    if "Request Rejected" in self.page.title() or "Request Rejected" in self.page.content():
                        logger.error("SNDL Proxy rejected the request (Bot detection).")
                        return False
                    
                    # Log page title/url to verify we are logged in
                    logger.warning(f"Page loaded: {self.page.title()} ({self.page.url})")
                    
                    # Heuristic: Try to find and click a PDF button
                    selectors = [
                        "a[href$='.pdf']",
                        "a:has-text('PDF')",
                        "a:has-text('Download')",
                        "button:has-text('PDF')",
                        "meta[name='citation_pdf_url']", 
                        "iframe[src$='.pdf']"
                    ]
                    
                    # Check for meta tag first (fastest)
                    pdf_meta = self.page.locator("meta[name='citation_pdf_url']").get_attribute("content")
                    if pdf_meta:
                        logger.warning(f"Found meta PDF: {pdf_meta}")
                        self.page.goto(pdf_meta) 
                    else:
                        # Try clicking a button
                        for sel in selectors:
                            if self.page.locator(sel).first.is_visible():
                                logger.warning(f"Clicking selector: {sel}")
                                self.page.locator(sel).first.click()
                                break
                        else:
                            logger.warning("No PDF selector found on page.")
                
                # If we get here, download started
                download = download_info.value
                download.save_as(output_path)
                logger.info(f"Downloaded: {output_path.name}")
                return True

            except PlaywrightTimeoutError:
                logger.error(f"Timeout waiting for download on {target_url}")
                if self.page.url.endswith(".pdf"):
                     logger.warning("Page URL ends with .pdf but download didn't trigger automatically.")
                pass

        except Exception as e:
            logger.error(f"SNDL Browser Error: {e}")
            
        return False

    def __del__(self):
        self._close_browser()
