"""
Extraction command.

Converts PDFs to structured Markdown and chunks using the integrated pipeline.
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
from nexus.extraction.pipeline import process_pdf_to_chunks

@click.command()
@click.option(
    "--input",
    "input_dir",
    type=click.Path(exists=True, path_type=Path),
    default=Path("results/pdfs"),
    help="Input directory containing PDFs.",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=Path("results/extraction"),
    help="Output directory for extracted content.",
)
@click.option(
    "--images/--no-images",
    default=False,
    help="Extract images (slower).",
)
@click.option(
    "--math/--no-math",
    default=False,
    help="Extract math equations (slower).",
)
@click.option(
    "--tables/--no-tables",
    default=True,
    help="Extract tables.",
)
@click.option(
    "--limit",
    type=int,
    help="Limit number of PDFs to process.",
)
@pass_context
def extract(
    ctx,
    input_dir: Path,
    output_dir: Path,
    images: bool,
    math: bool,
    tables: bool,
    limit: Optional[int],
):
    """Extract text and structure from PDFs.

    Converts PDFs to Markdown, extracts tables, and chunks content.
    """
    print_header("Nexus Extract", "PDF to Structured Text")

    if not input_dir.exists():
        print_error(f"Input directory not found: {input_dir}")
        return

    # Find PDFs
    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        print_error(f"No PDF files found in {input_dir}")
        return

    if limit:
        pdf_files = pdf_files[:limit]
        console.print(f"[yellow]Limiting to first {limit} PDFs[/yellow]")

    console.print(f"[bold]Input:[/bold] {input_dir} ({len(pdf_files)} PDFs)")
    console.print(f"[bold]Output:[/bold] {output_dir}")
    console.print(f"[bold]Features:[/bold] Images={images}, Math={math}, Tables={tables}\n")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Processing loop
    stats = {"success": 0, "failed": 0}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("{task.fields[stats]}"),
        console=console
    ) as progress:
        task = progress.add_task("Extracting...", total=len(pdf_files), stats="(0/0)")
        
        for pdf in pdf_files:
            progress.update(task, description=f"Extracting: {pdf.name}...")
            
            try:
                # Create a subfolder for each paper to keep things clean
                paper_output_dir = output_dir / pdf.stem
                paper_output_dir.mkdir(exist_ok=True)
                
                process_pdf_to_chunks(
                    pdf,
                    output_dir=paper_output_dir,
                    extract_images=images,
                    extract_math=math,
                    extract_tables=tables,
                    resolve_citations=False, # Disable for speed in CLI default
                    save_intermediate=True
                )
                stats["success"] += 1
                
            except Exception as e:
                stats["failed"] += 1
                # console.print(f"  [red]Failed {pdf.name}: {e}[/red]")
            
            progress.update(
                task, 
                advance=1, 
                stats=f"([green]{stats['success']}[/green]/[red]{stats['failed']}[/red])"
            )

    console.print()
    print_statistics({
        "Total processed": len(pdf_files),
        "Success": f"{stats['success']} ({stats['success']/len(pdf_files)*100:.1f}%)",
        "Failed": f"{stats['failed']} ({stats['failed']/len(pdf_files)*100:.1f}%)",
    }, title="Extraction Results")
