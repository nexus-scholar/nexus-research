"""
Export command.

This command exports documents to various formats for citation management.
"""

from pathlib import Path
from typing import List, Optional

import click

from nexus.cli.formatting import (
    console,
    format_number,
    print_error,
    print_header,
    print_success,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import load_documents
from nexus.core.models import Document
from nexus.export import get_exporter


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Input file (JSONL/CSV of documents)",
)
@click.option(
    "--format",
    "formats",
    multiple=True,
    type=click.Choice(
        ["bibtex", "csv", "json", "jsonl", "ris", "endnote"],
        case_sensitive=False
    ),
    help="Export format(s) - can specify multiple",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    help="Output file path (auto-generates if not specified)",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("results/exports"),
    help="Output directory",
)
@click.option(
    "--min-year",
    type=int,
    help="Filter by minimum year",
)
@click.option(
    "--max-year",
    type=int,
    help="Filter by maximum year",
)
@click.option(
    "--has-doi",
    is_flag=True,
    help="Only export documents with DOI",
)
@click.option(
    "--has-abstract",
    is_flag=True,
    help="Only export documents with abstract",
)
@click.option(
    "--bibtex-key-format",
    type=str,
    default="author_year_title",
    help="Citation key format for BibTeX",
)
@pass_context
def export(
    ctx,
    input_path: Path,
    formats: tuple,
    output_path: Optional[Path],
    output_dir: Path,
    min_year: Optional[int],
    max_year: Optional[int],
    has_doi: bool,
    has_abstract: bool,
    bibtex_key_format: str,
):
    """Export results to various formats.

    Export documents to BibTeX, CSV, RIS, or other formats for
    citation management and analysis.

    \b
    Examples:
      # Export to BibTeX
      slr export --input dedup/latest/representatives.jsonl --format bibtex

      # Export to multiple formats
      slr export --input dedup/latest/representatives.jsonl \\
                 --format bibtex --format csv --format ris

      # Export with filters
      slr export --input dedup/latest/representatives.jsonl \\
                 --format bibtex --has-doi --min-year 2020
    """
    print_header("Simple SLR Export", "Export to citation formats")

    # Default to bibtex if no format specified
    if not formats:
        formats = ("bibtex",)

    # Load documents
    console.print("[bold]Loading documents...[/bold]")
    documents = load_documents(input_path)
    console.print(f"  Loaded {format_number(len(documents))} documents\n")

    # Apply filters
    filtered_docs = documents

    if min_year is not None:
        filtered_docs = [d for d in filtered_docs if d.year and d.year >= min_year]
        console.print(f"  Filtered by min year {min_year}: {len(filtered_docs)} documents")

    if max_year is not None:
        filtered_docs = [d for d in filtered_docs if d.year and d.year <= max_year]
        console.print(f"  Filtered by max year {max_year}: {len(filtered_docs)} documents")

    if has_doi:
        filtered_docs = [d for d in filtered_docs if d.external_ids.doi]
        console.print(f"  Filtered by has DOI: {len(filtered_docs)} documents")

    if has_abstract:
        filtered_docs = [d for d in filtered_docs if d.abstract]
        console.print(f"  Filtered by has abstract: {len(filtered_docs)} documents")

    if not filtered_docs:
        print_error("No documents remaining after filtering")
        raise click.Abort()

    if len(filtered_docs) < len(documents):
        console.print(f"\n  [yellow]Exporting {len(filtered_docs)} of {len(documents)} documents[/yellow]\n")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Export to each format
    exported_files = []

    for fmt in formats:
        console.print(f"[bold]Exporting to {fmt.upper()}...[/bold]")

        try:
            # Get exporter
            exporter = get_exporter(fmt)

            # Determine output path
            if output_path and len(formats) == 1:
                # Use specified path for single format
                out_file = output_path
            else:
                # Auto-generate filename
                stem = input_path.stem
                if fmt == "bibtex":
                    ext = ".bib"
                elif fmt == "ris":
                    ext = ".ris"
                elif fmt == "endnote":
                    ext = ".enw"
                elif fmt == "csv":
                    ext = ".csv"
                elif fmt == "jsonl":
                    ext = ".jsonl"
                else:
                    ext = f".{fmt}"

                out_file = output_dir / f"{stem}{ext}"

            # Export
            if out_file.parent != Path(""):
                out_file.parent.mkdir(parents=True, exist_ok=True)

            exporter.export_documents(filtered_docs, str(out_file))

            exported_files.append(str(out_file))
            print_success(f"Exported to {out_file}")

        except Exception as e:
            print_error(f"Failed to export to {fmt}: {e}")
            if ctx.verbose:
                raise

    # Print summary
    if exported_files:
        console.print()
        console.rule()
        print_success(f"Export complete!")
        console.print()
        console.print(f"  Exported {format_number(len(filtered_docs))} documents to {len(exported_files)} file(s)")
        for f in exported_files:
            console.print(f"  • [cyan]{f}[/cyan]")
        console.print()
    else:
        print_error("No files were exported")
        raise click.Abort()

