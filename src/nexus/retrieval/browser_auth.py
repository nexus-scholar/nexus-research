import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import logging

logger = logging.getLogger(__name__)

SNDL_LOGIN_URL = "https://www.sndl.cerist.dz/login.php"
AUTH_FILE = Path("auth.json")

def login_and_save_state(headless: bool = False):
    """
    Launch a browser for manual login and save the session state.
    """
    print(f"Launching browser for manual login at {SNDL_LOGIN_URL}...")
    
    with sync_playwright() as p:
        # Use Firefox as it handles legacy proxies/SSL better sometimes
        browser = p.firefox.launch(headless=headless)
        # Ignore HTTPS errors for SNDL proxy
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        
        try:
            page.goto(SNDL_LOGIN_URL)
            
            print("\n" + "="*50)
            print("Action Required: Please log in manually in the browser.")
            print("1. Log in to SNDL.")
            print("2. Click on a database (e.g. ScienceDirect/IEEE).")
            print("3. Ensure the database page loads completely.")
            print("="*50 + "\n")
            
            # Simple manual confirmation - foolproof
            input(">>> Press ENTER in this terminal once you have successfully loaded a database page... <<<")

            # Capture state from ALL pages to ensure we get the proxy cookies
            print("Capturing session state...")
            context.storage_state(path=AUTH_FILE)
            print(f"Session saved to {AUTH_FILE}")
            return True
            
        except Exception as e:
            print(f"Browser Error: {e}")
            return False
        finally:
            try:
                browser.close()
            except:
                pass

def load_auth_cookies() -> dict:
    """Load cookies from the saved auth.json file."""
    if not AUTH_FILE.exists():
        return {}
        
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
            
        cookies = {}
        for cookie in data.get("cookies", []):
            cookies[cookie["name"]] = cookie["value"]
        return cookies
    except Exception as e:
        logger.error(f"Failed to load auth file: {e}")
        return {}