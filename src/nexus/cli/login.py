"""
Login command.

Handles interactive login for restricted sources (SNDL).
"""

import click
from nexus.retrieval.browser_auth import login_and_save_state

@click.command()
@click.option("--headless", is_flag=True, help="Run in headless mode (if you can automate it).")
def login(headless: bool):
    """Log in to restricted sources (SNDL).

    Launches a browser window for you to manually log in.
    Once logged in, the session is saved for future fetch operations.
    """
    success = login_and_save_state(headless=headless)
    if not success:
        click.echo("Login failed.", err=True)
        # sys.exit(1)
