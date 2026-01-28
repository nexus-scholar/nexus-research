"""
Main CLI entry point for Simple SLR.

This module provides the main CLI group and global options.
"""

import sys
from pathlib import Path
from typing import Optional

import click

from nexus.cli.formatting import console, print_error, print_header
from nexus.cli.utils import setup_logging


# Version info
__version__ = "0.9.1-alpha.0"


# Global context object for passing config between commands
class CLIContext:
    """Context object for CLI commands."""

    def __init__(self):
        self.config_path: Optional[Path] = None
        self.verbose: int = 0
        self.quiet: bool = False


pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.group()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file (default: nexus.yml)",
)
@click.option(
    "--verbose", "-v",
    count=True,
    help="Enable verbose logging (can be repeated: -vv, -vvv)",
)
@click.option(
    "--quiet", "-q",
    is_flag=True,
    help="Suppress non-error output",
)
@click.version_option(version=__version__, prog_name="Nexus")
@click.pass_context
def cli(ctx, config: Optional[Path], verbose: int, quiet: bool):
    """
    Nexus - AI Research Assistant

    A modern, extensible framework for conducting systematic literature reviews
    with support for multiple academic databases, intelligent deduplication,
    and PRISMA-compliant workflows.

    \b
    Typical workflow:
      1. nexus init              # Set up project structure
      2. nexus search            # Search academic databases
      3. nexus deduplicate       # Remove duplicates
      4. nexus export            # Export to BibTeX/CSV/etc.

    \b
    For help on a specific command:
      nexus <command> --help
    """
    # Initialize context
    cli_ctx = ctx.ensure_object(CLIContext)
    cli_ctx.config_path = config
    cli_ctx.verbose = verbose
    cli_ctx.quiet = quiet

    # Set up logging
    setup_logging(verbose=verbose, quiet=quiet)


# Import and register commands
# This must happen at module level so commands are available when cli() is called
from nexus.cli.init import init
from nexus.cli.search import search
from nexus.cli.deduplicate import deduplicate
from nexus.cli.export import export
from nexus.cli.validate import validate
from nexus.cli.screen import screen
from nexus.cli.fetch import fetch
from nexus.cli.extract import extract

cli.add_command(init)
cli.add_command(search)
cli.add_command(deduplicate)
cli.add_command(export)
cli.add_command(validate)
cli.add_command(screen)
cli.add_command(fetch)
cli.add_command(extract)


def main():
    """Main entry point for the CLI."""
    try:
        # Run CLI
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        if "--verbose" in sys.argv or "-v" in sys.argv:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()

