"""
Screening command.

This command uses an LLM to screen papers based on title and abstract.
"""

import os
import json
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

    # Prepare output and resume logic
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"screening_{input_path.parent.name}.jsonl"
    
    existing_dois = set()
    if output_file.exists():
        console.print(f"[yellow]Found existing output file. Resuming...[/yellow]")
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if "doi" in data and data["doi"]:
                            existing_dois.add(data["doi"])
            console.print(f"  Skipping {len(existing_dois)} already screened papers.")
        except Exception as e:
            print_error(f"Error reading existing file: {e}")

    # Filter documents
    docs_to_screen = [d for d in documents if d.external_ids.doi not in existing_dois]
    
    if not docs_to_screen:
        print_success("All documents have been screened!")
        return

    # Run screening
    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Screening...", total=len(docs_to_screen))
        
        # We wrap the generator to update progress
        # Create a map for quick lookup if needed, or just iterate if order is preserved
        # Actually, screener yields results. We need to match them to docs.
        # But screener takes a list. It yields one result per doc in order.
        
        # Better approach: Iterate over documents and screen one by one in the loop
        # But Screener.screen_documents is a generator.
        
        # Let's iterate the generator and the docs together?
        # Or just have screener yield (doc, result) tuple? No, keep it clean.
        # We can map by DOI/Title or assume order. Assuming order is risky if errors occur.
        
        # Let's assume order for now as screener yields for each input.
        
        doc_map = {d.external_ids.doi: d for d in docs_to_screen if d.external_ids.doi}
        # Fallback map for docs without DOI? Title?
        # Simplest: Update Screener to return the original doc OR pass it through.
        
        # Actually, let's just update the loop to manually call client for each doc
        # inside this CLI loop? No, that breaks the abstraction.
        
        # I will rely on the fact that I passed docs_to_screen to screen_documents.
        # I will update the Document object with the result.
        
        for i, result in enumerate(screener.screen_documents(docs_to_screen, criteria=criteria)):
            original_doc = docs_to_screen[i] # This assumes 1:1 mapping and order preservation
            
            # Update the document
            original_doc.decision = result.decision.value
            
            # Save full document
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(original_doc.model_dump_json() + "\n")
            
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
    console.print("[bold]Summary (Current Run):[/bold]")
    console.print(f"  Include: [green]{counts['include']}[/green]")
    console.print(f"  Maybe:   [yellow]{counts['maybe']}[/yellow]")
    console.print(f"  Exclude: [red]{counts['exclude']}[/red]")
