"""
CLI output formatting utilities.

This module provides helpers for consistent, beautiful terminal output
using the Rich library.
"""

from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TaskProgressColumn,
)
from rich.syntax import Syntax
from rich.tree import Tree


# Global console instance
console = Console()


def print_header(title: str, subtitle: Optional[str] = None) -> None:
    """Print a formatted header."""
    console.print()
    console.rule(f"[bold blue]{title}[/bold blue]")
    if subtitle:
        console.print(f"[dim]{subtitle}[/dim]")
    console.print()


def print_section(title: str) -> None:
    """Print a section header."""
    console.print(f"\n[bold]{title}[/bold]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}", style="red")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")


def print_config(config_dict: Dict[str, Any], title: str = "Configuration") -> None:
    """Print a configuration dictionary in a nice format."""
    print_section(title)
    for key, value in config_dict.items():
        if isinstance(value, (list, tuple)):
            value_str = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            value_str = f"{len(value)} items"
        else:
            value_str = str(value)
        console.print(f"  [cyan]{key}:[/cyan] {value_str}")


def print_statistics(stats: Dict[str, Any], title: str = "Statistics") -> None:
    """Print statistics in a table format."""
    table = Table(title=title, show_header=False, box=None)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    for key, value in stats.items():
        # Format percentages nicely
        if isinstance(value, float) and 0 <= value <= 1:
            value_str = f"{value:.1%}"
        elif isinstance(value, float):
            value_str = f"{value:.2f}"
        else:
            value_str = str(value)
        table.add_row(key, value_str)

    console.print(table)


def print_provider_results(results: Dict[str, int]) -> None:
    """Print provider search results."""
    table = Table(title="Provider Results", show_header=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Documents", justify="right", style="green")

    total = 0
    for provider, count in results.items():
        table.add_row(provider, str(count))
        total += count

    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")
    console.print(table)


def print_year_distribution(year_counts: Dict[int, int]) -> None:
    """Print year distribution as a simple bar chart."""
    if not year_counts:
        return

    print_section("Year Distribution")
    max_count = max(year_counts.values())

    for year in sorted(year_counts.keys()):
        count = year_counts[year]
        bar_width = int((count / max_count) * 40)
        bar = "█" * bar_width
        percentage = (count / sum(year_counts.values())) * 100
        console.print(f"  {year}: {bar} {count:,} ({percentage:.1f}%)")


def create_progress() -> Progress:
    """Create a progress bar with consistent styling."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def print_summary_panel(
    title: str,
    content: Dict[str, Any],
    success: bool = True
) -> None:
    """Print a summary panel with results."""
    lines = []
    for key, value in content.items():
        lines.append(f"[cyan]{key}:[/cyan] {value}")

    style = "green" if success else "red"
    panel = Panel(
        "\n".join(lines),
        title=f"[bold]{title}[/bold]",
        border_style=style,
    )
    console.print(panel)


def print_file_tree(root_path: str, files: List[str]) -> None:
    """Print a file tree structure."""
    tree = Tree(f"[bold blue]{root_path}[/bold blue]")
    for file in files:
        tree.add(f"[green]{file}[/green]")
    console.print(tree)


def confirm(question: str, default: bool = False) -> bool:
    """Ask a yes/no question and return the answer."""
    default_str = "Y/n" if default else "y/N"
    response = console.input(f"{question} [{default_str}]: ").strip().lower()

    if not response:
        return default
    return response in ("y", "yes")


def format_number(n: int) -> str:
    """Format a number with thousand separators."""
    return f"{n:,}"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

