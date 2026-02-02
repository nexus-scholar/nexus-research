"""
Extraction command.

Converts PDFs to structured Markdown and chunks using the integrated pipeline.
"""

import concurrent.futures
import os
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
    (
        pdf,
        output_dir,
        images,
        math,
        tables,
        enable_ocr,
        ocr_min_chars,
        ocr_lang,
        ocr_engine,
        ocr_dpi,
        math_ocr,
        math_ocr_engine,
        inline_math,
        merge_table_continuations,
        split_references,
    ) = args
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
            save_intermediate=True,
            enable_ocr=enable_ocr,
            ocr_min_chars=ocr_min_chars,
            ocr_lang=ocr_lang,
            ocr_engine=ocr_engine,
            ocr_dpi=ocr_dpi,
            math_ocr=math_ocr,
            math_ocr_engine=math_ocr_engine,
            inline_math=inline_math,
            merge_table_continuations=merge_table_continuations,
            split_references=split_references,
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
    default=None,
    help="Extract images (slower).",
)
@click.option(
    "--math/--no-math",
    default=None,
    help="Extract math equations (slower).",
)
@click.option(
    "--tables/--no-tables",
    default=None,
    help="Extract tables.",
)
@click.option(
    "--scientific/--no-scientific",
    default=False,
    help="Use a scientific extraction profile (OCR + LaTeX math + tables, no images).",
)
@click.option(
    "--ocr/--no-ocr",
    default=None,
    help="Enable OCR on low-text pages.",
)
@click.option(
    "--ocr-min-chars",
    type=int,
    default=200,
    help="Minimum characters before triggering OCR for a page.",
)
@click.option(
    "--ocr-lang",
    type=str,
    default="eng",
    help="OCR language (tesseract).",
)
@click.option(
    "--ocr-engine",
    type=click.Choice(["tesseract"], case_sensitive=False),
    default="tesseract",
    help="OCR engine to use.",
)
@click.option(
    "--ocr-dpi",
    type=int,
    default=300,
    help="DPI for OCR rendering.",
)
@click.option(
    "--math-ocr/--no-math-ocr",
    default=None,
    help="OCR math regions into LaTeX (pix2tex).",
)
@click.option(
    "--math-ocr-engine",
    type=click.Choice(["pix2tex"], case_sensitive=False),
    default="pix2tex",
    help="Math OCR engine to use.",
)
@click.option(
    "--inline-math/--no-inline-math",
    default=None,
    help="Append LaTeX math blocks to text chunks.",
)
@click.option(
    "--merge-table-continuations/--no-merge-table-continuations",
    default=None,
    help="Merge multi-page tables with matching headers.",
)
@click.option(
    "--split-references/--no-split-references",
    default=None,
    help="Detect and split references section from body text.",
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
    scientific: bool,
    ocr: bool,
    ocr_min_chars: int,
    ocr_lang: str,
    ocr_engine: str,
    ocr_dpi: int,
    math_ocr: bool,
    math_ocr_engine: str,
    inline_math: bool,
    merge_table_continuations: bool,
    split_references: bool,
    limit: Optional[int],
    workers: Optional[int],
):
    """Extract text and structure from PDFs.

    Converts PDFs to Markdown, extracts tables, and chunks content.
    Uses parallel processing for speed.
    """
    print_header("Nexus Extract", "PDF to Structured Text")

    def _resolve(value, default):
        return default if value is None else value

    if scientific:
        images = _resolve(images, False)
        math = _resolve(math, True)
        tables = _resolve(tables, True)
        ocr = _resolve(ocr, True)
        math_ocr = _resolve(math_ocr, True)
        inline_math = _resolve(inline_math, True)
        merge_table_continuations = _resolve(merge_table_continuations, True)
        split_references = _resolve(split_references, False)
    else:
        images = _resolve(images, False)
        math = _resolve(math, False)
        tables = _resolve(tables, True)
        ocr = _resolve(ocr, False)
        math_ocr = _resolve(math_ocr, False)
        inline_math = _resolve(inline_math, False)
        merge_table_continuations = _resolve(merge_table_continuations, True)
        split_references = _resolve(split_references, True)

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
    console.print(
        "[bold]Features:[/bold] "
        f"Images={images}, Math={math}, Tables={tables}, OCR={ocr}, "
        f"MathOCR={math_ocr}, InlineMath={inline_math}, MergeTables={merge_table_continuations}, "
        f"SplitReferences={split_references}"
    )
    console.print(f"[bold]Workers:[/bold] {max_workers}\n")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Processing loop
    stats = {"success": 0, "failed": 0}
    
    # Prepare arguments for each task
    tasks = [
        (
            pdf,
            output_dir,
            images,
            math,
            tables,
            ocr,
            ocr_min_chars,
            ocr_lang,
            ocr_engine,
            ocr_dpi,
            math_ocr,
            math_ocr_engine,
            inline_math,
            merge_table_continuations,
            split_references,
        )
        for pdf in pdf_files
    ]
    
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
