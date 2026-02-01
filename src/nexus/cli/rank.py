"""
Ranking command for identifying high-impact papers.
"""

import json
from pathlib import Path
from typing import Optional, List

import click
from rich.table import Table

from nexus.cli.formatting import (
    console,
    print_header,
    print_success,
    print_error,
    format_number,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import load_documents, save_documents, get_latest_run
from nexus.analysis.journal_ranker import JournalRanker
from nexus.core.models import Document

@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    help="Input JSONL file (screened results).",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=Path("results/ranked"),
    help="Output directory.",
)
@click.option(
    "--threshold",
    type=int,
    default=90,
    help="Fuzzy matching threshold for journal names (0-100).",
)
@click.option(
    "--only-q1",
    is_flag=True,
    default=True,
    help="Only keep papers from Q1 journals.",
)
@pass_context
def rank(
    ctx,
    input_path: Optional[Path],
    output_dir: Path,
    threshold: int,
    only_q1: bool,
):
    """Rank and filter papers by venue impact.

    Identifies papers published in high-impact (Q1) journals using
    the curated Scimago-aligned database.
    """
    print_header("Nexus Ranker", "Journal Impact & Venue Validation")

    # Resolve input path
    if not input_path:
        # Try to find latest screening run
        screening_base = Path("results/screening")
        latest_run = get_latest_run(screening_base, prefix="final_") or get_latest_run(screening_base, prefix="screening_")
        if latest_run:
            # Check for final_screened_dataset.jsonl first
            final_file = latest_run / "final_screened_dataset.jsonl"
            if final_file.exists():
                input_path = final_file
            else:
                # Find any jsonl in that folder
                jsonls = list(screening_base.glob("*.jsonl"))
                if jsonls:
                    # Sort by modification time
                    jsonls.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    input_path = jsonls[0]
        
        if not input_path:
            # Check the direct screening folder
            jsonls = list(screening_base.glob("*.jsonl"))
            if jsonls:
                jsonls.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                input_path = jsonls[0]

    if not input_path or not input_path.exists():
        print_error("No input specified and no recent screening results found.")
        return

    console.print(f"[bold]Input:[/bold] {input_path}")

    # Load documents
    try:
        all_docs = load_documents(input_path)
        # Only process INCLUDED or MAYBE papers
        documents = [d for d in all_docs if d.decision in ["include", "maybe"]]
    except Exception as e:
        print_error(f"Failed to load documents: {e}")
        return

    console.print(f"Loaded {len(documents)} included/maybe papers for ranking.")

    # Init Ranker
    ranker = JournalRanker()
    
    q1_docs = []
    other_docs = []

    with console.status("[cyan]Validating venues against Q1 database..."):
        for doc in documents:
            if ranker.is_q1(doc.venue, threshold=threshold):
                q1_docs.append(doc)
            else:
                other_docs.append(doc)

    # Prepare results
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save Q1 results
    q1_file = output_dir / f"q1_papers_{input_path.stem}.jsonl"
    save_documents(q1_docs, q1_file, format="jsonl")
    
    # Statistics Table
    table = Table(title="Venue Impact Summary")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right", style="green")
    table.add_column("Percentage", justify="right", style="magenta")

    total = len(documents)
    if total > 0:
        q1_pct = len(q1_docs) / total * 100
        other_pct = len(other_docs) / total * 100
        
        table.add_row("Q1 High-Impact", format_number(len(q1_docs)), f"{q1_pct:.1f}%")
        table.add_row("Other Venues", format_number(len(other_docs)), f"{other_pct:.1f}%")
        table.add_row("Total Processed", format_number(total), "100.0%")
        
        console.print(table)
    
    print_success(f"Ranking complete! Q1 papers saved to: {q1_file}")
    
    if len(q1_docs) > 0:
        console.print("\n[bold]Top Q1 Venues found:[/bold]")
        venues = [d.venue for d in q1_docs if d.venue]
        from collections import Counter
        for v, c in Counter(venues).most_common(10):
            console.print(f"  - {v}: {c}")
    
    # Recommendation
    if only_q1:
        console.print(f"\n[yellow]Final dataset reduced to {len(q1_docs)} Q1 papers.[/yellow]")
