import os
import requests
from typing import Optional
import logging

logger = logging.getLogger(__name__)

SNDL_LOGIN_URL = "https://www.sndl.cerist.dz/login.php"

class SNDLAuthenticator:
    """Handles authentication with SNDL (Cerist)."""

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.username = username or os.getenv("SNDL_USERNAME")
        self.password = password or os.getenv("SNDL_PASSWORD")
        self.session = requests.Session()
        # Set a browser-like user agent
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })

    def login(self) -> bool:
        """Perform login and store cookies."""
        if not self.username or not self.password:
            logger.warning("SNDL credentials not set. Skipping SNDL authentication.")
            return False

        try:
            # First, get the login page to set initial cookies/tokens if needed
            self.session.get(SNDL_LOGIN_URL)

            # Payload (guessing standard field names based on URL structure)
            # Common variants: login/password, user/pass, username/password
            # Based on standard PHP apps, 'login' and 'password' are good guesses.
            payload = {
                "login": self.username,
                "password": self.password,
                "submit": "Login" # Sometimes required
            }

            response = self.session.post(SNDL_LOGIN_URL, data=payload, timeout=15)
            
            # Check for success
            # Usually redirects to index or has specific text
            if response.status_code == 200 and "logout" in response.text.lower():
                logger.info("Successfully logged into SNDL.")
                return True
            elif response.url != SNDL_LOGIN_URL:
                # Redirected typically means success
                logger.info("Successfully logged into SNDL (Redirect).")
                return True
            else:
                logger.error("SNDL Login failed. Check credentials.")
                return False

        except Exception as e:
            logger.error(f"SNDL Login Error: {e}")
            return False

    def get_session(self) -> requests.Session:
        """Get the authenticated session."""
        if not self.session.cookies:
            self.login()
        return self.session
