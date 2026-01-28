"""
Screening command.

This command uses an LLM to screen papers based on title and abstract.
"""

import os
from pathlib import Path
from typing import Optional

import click
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID

from nexus.cli.formatting import (
    console,
    print_error,
    print_header,
    print_success,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import load_documents, get_latest_run
from nexus.screener.screener import Screener
from nexus.screener.client import LLMClient
from nexus.screener.models import ScreeningResult

@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    help="Input file (deduplicated JSONL). Defaults to latest dedup run.",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=Path("results/screening"),
    help="Output directory.",
)
@click.option(
    "--criteria",
    type=str,
    default="General Relevance to the research query provided in context.",
    help="Global screening criteria passed to the system prompt.",
)
@click.option(
    "--model",
    type=str,
    default="gpt-4o",
    help="LLM model to use.",
)
@pass_context
def screen(
    ctx,
    input_path: Optional[Path],
    output_dir: Path,
    criteria: str,
    model: str,
):
    """Screen papers using an LLM.

    Classifies papers as 'include', 'exclude', or 'maybe' based on
    title and abstract relevance to the search queries.

    Requires OPENAI_API_KEY environment variable.
    """
    print_header("Nexus Screener", "LLM-based Title & Abstract Screening")

    # Resolve input path
    if not input_path:
        # Try to find latest dedup run
        dedup_base = Path("results/dedup")
        latest_dedup = get_latest_run(dedup_base, prefix="dedup_")
        if latest_dedup:
            input_path = latest_dedup / "representatives.jsonl"
            if not input_path.exists():
                print_error(f"Latest run found at {latest_dedup} but missing representatives.jsonl")
                return
        else:
            print_error("No input specified and no recent deduplication run found.")
            return

    console.print(f"[bold]Input:[/bold] {input_path}")
    
    # Load documents
    try:
        documents = load_documents(input_path)
    except Exception as e:
        print_error(f"Failed to load documents: {e}")
        return

    console.print(f"Loaded {len(documents)} documents.")

    # Initialize Client & Screener
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print_error("OPENAI_API_KEY environment variable is not set.")
        return

    client = LLMClient(api_key=api_key, model=model)
    screener = Screener(client)

    # Prepare output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"screening_{input_path.parent.name}.jsonl"
    
    # Run screening
    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Screening...", total=len(documents))
        
        # We wrap the generator to update progress
        for result in screener.screen_documents(documents, criteria=criteria):
            results.append(result)
            
            # Streaming save (append mode)
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(result.model_dump_json() + "\n")
            
            color = "green" if result.decision == "include" else "red" if result.decision == "exclude" else "yellow"
            progress.console.print(f"  [{color}]{result.decision.upper()}[/{color}] {result.title[:60]}...")
            progress.advance(task)

    print_success(f"Screening complete! Results saved to {output_file}")
    
    # Summary stats
    counts = {"include": 0, "exclude": 0, "maybe": 0}
    for r in results:
        if r.decision.value in counts:
            counts[r.decision.value] += 1
            
    console.print()
    console.print("[bold]Summary:[/bold]")
    console.print(f"  Include: [green]{counts['include']}[/green]")
    console.print(f"  Maybe:   [yellow]{counts['maybe']}[/yellow]")
    console.print(f"  Exclude: [red]{counts['exclude']}[/red]")
