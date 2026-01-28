"""
Fetch command.

Retrieves full-text PDFs for documents.
"""

from pathlib import Path
from typing import Optional

import click
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from nexus.cli.formatting import (
    console,
    print_error,
    print_header,
    print_success,
    print_statistics,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import load_documents, get_latest_run, load_config
from nexus.retrieval.fetcher import PDFFetcher

@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    help="Input file (JSONL). Defaults to latest dedup run.",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=Path("results/pdfs"),
    help="Output directory for PDFs.",
)
@click.option(
    "--limit",
    type=int,
    help="Limit number of downloads (useful for testing).",
)
@pass_context
def fetch(
    ctx,
    input_path: Optional[Path],
    output_dir: Path,
    limit: Optional[int],
):
    """Fetch full-text PDFs.

    Downloads PDFs for documents from supported sources (ArXiv, Open Access).
    """
    print_header("Nexus Fetch", "Full-text PDF Retrieval")

    # Load config
    config = load_config(ctx.config_path)

    # Resolve input path
    if not input_path:
        # Try to find latest dedup run
        dedup_base = Path("results/dedup")
        latest_dedup = get_latest_run(dedup_base, prefix="dedup_")
        if latest_dedup:
            input_path = latest_dedup / "representatives.jsonl"
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

    if limit:
        documents = documents[:limit]
        console.print(f"[yellow]Limiting to first {limit} documents[/yellow]")

    console.print(f"Loaded {len(documents)} documents.")

    # Initialize Fetcher
    fetcher_config = {"email": config.mailto}
    fetcher = PDFFetcher(output_dir, config=fetcher_config)
    console.print(f"[bold]Output:[/bold] {output_dir}\n")

    # Run fetch loop
    stats = {"success": 0, "failed": 0, "skipped": 0}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("{task.fields[stats]}"),
        console=console
    ) as progress:
        task = progress.add_task("Fetching PDFs...", total=len(documents), stats="(0/0)")
        
        for doc in documents:
            filename = fetcher.get_filename(doc)
            if (output_dir / filename).exists():
                stats["skipped"] += 1
                progress.console.print(f"  [dim]Skipped (Exists): {filename}[/dim]")
            else:
                success = fetcher.fetch(doc)
                if success:
                    stats["success"] += 1
                    progress.console.print(f"  [green]Downloaded: {filename}[/green]")
                else:
                    stats["failed"] += 1
                    # progress.console.print(f"  [red]Failed: {doc.title[:40]}...[/red]")
            
            progress.update(
                task, 
                advance=1, 
                stats=f"([green]{stats['success']}[/green]/[red]{stats['failed']}[/red])"
            )

    console.print()
    print_statistics({
        "Total processed": len(documents),
        "Downloaded": f"{stats['success']} ({stats['success']/len(documents)*100:.1f}%)",
        "Failed": f"{stats['failed']} ({stats['failed']/len(documents)*100:.1f}%)",
        "Skipped": stats['skipped']
    }, title="Retrieval Results")
