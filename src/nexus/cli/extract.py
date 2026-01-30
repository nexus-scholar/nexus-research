"""
Extraction command.

Converts PDFs to structured Markdown and chunks using the integrated pipeline.
"""

from pathlib import Path
from typing import Optional

import os
import concurrent.futures
from pathlib import Path
from typing import Optional

import click
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from nexus.cli.formatting import (
    console,
    print_error,
    print_header,
    print_success,
    print_statistics,
)
from nexus.cli.main import pass_context
from nexus.extraction.pipeline import process_pdf_to_chunks

def _process_single_pdf(args):
    """Helper for multiprocessing."""
    pdf, output_dir, images, math, tables = args
    try:
        paper_output_dir = output_dir / pdf.stem
        paper_output_dir.mkdir(exist_ok=True)
        
        process_pdf_to_chunks(
            pdf,
            output_dir=paper_output_dir,
            extract_images=images,
            extract_math=math,
            extract_tables=tables,
            resolve_citations=False,
            save_intermediate=True
        )
        return True, None
    except Exception as e:
        return False, str(e)

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
@click.option(
    "--workers",
    type=int,
    default=None,
    help="Number of parallel workers (default: CPU count).",
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
    workers: Optional[int],
):
    """Extract text and structure from PDFs.

    Converts PDFs to Markdown, extracts tables, and chunks content.
    Uses parallel processing for speed.
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

    max_workers = workers or os.cpu_count() or 1
    
    console.print(f"[bold]Input:[/bold] {input_dir} ({len(pdf_files)} PDFs)")
    console.print(f"[bold]Output:[/bold] {output_dir}")
    console.print(f"[bold]Features:[/bold] Images={images}, Math={math}, Tables={tables}")
    console.print(f"[bold]Workers:[/bold] {max_workers}\n")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Processing loop
    stats = {"success": 0, "failed": 0}
    
    # Prepare arguments for each task
    tasks = [(pdf, output_dir, images, math, tables) for pdf in pdf_files]
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TextColumn("{task.fields[stats]}"),
        console=console
    ) as progress:
        task = progress.add_task("Extracting...", total=len(pdf_files), stats="(0/0)")
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Map futures to pdf filenames for error reporting
            futures = {executor.submit(_process_single_pdf, t): t[0].name for t in tasks}
            
            for future in concurrent.futures.as_completed(futures):
                filename = futures[future]
                try:
                    success, error = future.result()
                    if success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1
                        # console.print(f"  [red]Failed {filename}: {error}[/red]")
                except Exception as e:
                    stats["failed"] += 1
                    console.print(f"  [red]Crash {filename}: {e}[/red]")
                
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
