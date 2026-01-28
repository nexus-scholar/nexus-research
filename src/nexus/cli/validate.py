"""
Validation command.

This command validates data and shows statistics at any stage.
"""

from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import click

from nexus.cli.formatting import (
    console,
    format_number,
    print_error,
    print_header,
    print_section,
    print_success,
    print_warning,
    print_year_distribution,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import load_documents, load_documents_from_directory
from nexus.core.models import Document


def validate_documents(documents: List[Document]) -> Dict[str, any]:
    """Validate a list of documents and return statistics.

    Args:
        documents: List of documents to validate

    Returns:
        Dictionary with validation results and statistics
    """
    stats = {
        "total": len(documents),
        "with_doi": 0,
        "with_abstract": 0,
        "with_arxiv_id": 0,
        "with_authors": 0,
        "with_venue": 0,
        "with_url": 0,
        "providers": Counter(),
        "years": Counter(),
        "languages": Counter(),
    }

    errors = []
    warnings = []

    # Validate each document
    title_counts = Counter()

    for i, doc in enumerate(documents):
        # Required fields
        if not doc.title:
            errors.append(f"Document {i+1}: Missing title")
        else:
            title_counts[doc.title.lower().strip()] += 1

        if not doc.year:
            warnings.append(f"Document {i+1}: Missing year")

        # Count fields
        if doc.external_ids.doi:
            stats["with_doi"] += 1
            # Validate DOI format
            if not doc.external_ids.doi.startswith("10."):
                warnings.append(f"Document {i+1}: Invalid DOI format: {doc.external_ids.doi}")

        if doc.abstract:
            stats["with_abstract"] += 1

        if doc.external_ids.arxiv_id:
            stats["with_arxiv_id"] += 1

        if doc.authors:
            stats["with_authors"] += 1

        if doc.venue:
            stats["with_venue"] += 1

        if doc.url:
            stats["with_url"] += 1

        # Count providers
        if doc.provider:
            stats["providers"][doc.provider] += 1

        # Count years
        if doc.year:
            stats["years"][doc.year] += 1

        # Count languages
        if doc.language:
            stats["languages"][doc.language] += 1

    # Check for duplicate titles
    duplicate_titles = {title: count for title, count in title_counts.items() if count > 1}
    if duplicate_titles:
        num_dups = sum(duplicate_titles.values())
        warnings.append(f"{num_dups} documents have duplicate titles (potential duplicates)")

    # Check year distribution
    if stats["years"]:
        min_year = min(stats["years"].keys())
        max_year = max(stats["years"].keys())
        if min_year < 1900:
            warnings.append(f"Suspiciously old year detected: {min_year}")
        if max_year > 2030:
            warnings.append(f"Future year detected: {max_year}")

    return {
        "stats": stats,
        "errors": errors,
        "warnings": warnings,
        "duplicate_titles": len(duplicate_titles),
    }


@click.command()
@click.argument(
    "path",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--type",
    "data_type",
    type=click.Choice(["search", "dedup", "export", "auto"], case_sensitive=False),
    default="auto",
    help="Data type",
)
@click.option(
    "--show-errors",
    is_flag=True,
    help="Show detailed error messages",
)
@click.option(
    "--fix-common",
    is_flag=True,
    help="Attempt to fix common issues (not implemented yet)",
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    help="Save validation report to file",
)
@click.option(
    "--stats-only",
    is_flag=True,
    help="Show statistics only (skip validation)",
)
@pass_context
def validate(
    ctx,
    path: Path,
    data_type: str,
    show_errors: bool,
    fix_common: bool,
    report: Optional[Path],
    stats_only: bool,
):
    """Validate data and show statistics.

    Validate documents and show quality statistics at any stage
    of the workflow.

    \b
    Examples:
      # Validate search results
      slr validate outputs/run_2025-11-15_143022/

      # Show statistics only
      slr validate dedup/latest/ --stats-only

      # Generate validation report
      slr validate outputs/latest/ --report validation_report.txt
    """
    print_header("Simple SLR Validation", "Data quality and statistics")

    # Load documents
    console.print("[bold]Loading documents...[/bold]")

    if path.is_file():
        documents = load_documents(path)
        data_source = str(path)
    else:
        documents = load_documents_from_directory(path)
        data_source = str(path)

    console.print(f"  Loaded {format_number(len(documents))} documents\n")

    # Validate
    if not stats_only:
        console.print("[bold]Validating...[/bold]\n")

    results = validate_documents(documents)
    stats = results["stats"]
    errors = results["errors"]
    warnings = results["warnings"]

    # Print statistics
    print_section("Document Statistics")
    console.print(f"  Total documents:         {format_number(stats['total'])}")
    console.print(f"  Documents with DOI:      {format_number(stats['with_doi'])} "
                 f"({stats['with_doi']/stats['total']*100:.1f}%)")
    console.print(f"  Documents with abstract: {format_number(stats['with_abstract'])} "
                 f"({stats['with_abstract']/stats['total']*100:.1f}%)")
    console.print(f"  Documents with arXiv ID: {format_number(stats['with_arxiv_id'])} "
                 f"({stats['with_arxiv_id']/stats['total']*100:.1f}%)")
    console.print(f"  Documents with authors:  {format_number(stats['with_authors'])} "
                 f"({stats['with_authors']/stats['total']*100:.1f}%)")
    console.print(f"  Documents with venue:    {format_number(stats['with_venue'])} "
                 f"({stats['with_venue']/stats['total']*100:.1f}%)")

    # Provider distribution
    if stats["providers"]:
        console.print()
        print_section("Provider Distribution")
        for provider, count in stats["providers"].most_common():
            percentage = count / stats["total"] * 100
            console.print(f"  {provider}: {format_number(count)} ({percentage:.1f}%)")

    # Year distribution
    if stats["years"]:
        console.print()
        print_year_distribution(dict(stats["years"]))

    # Language distribution
    if stats["languages"]:
        console.print()
        print_section("Language Distribution")
        for lang, count in stats["languages"].most_common():
            percentage = count / stats["total"] * 100
            console.print(f"  {lang or 'unknown'}: {format_number(count)} ({percentage:.1f}%)")

    # Print validation results
    if not stats_only:
        console.print()
        print_section("Data Quality")

        quality_checks = []

        # All documents have titles
        if all(d.title for d in documents):
            quality_checks.append(("✓", "All documents have titles"))
        else:
            quality_checks.append(("✗", "Some documents missing titles"))

        # All documents have years
        if all(d.year for d in documents):
            quality_checks.append(("✓", "All documents have years"))
        else:
            quality_checks.append(("⚠", f"{stats['total'] - len([d for d in documents if d.year])} documents missing years"))

        # Check DOI validity
        invalid_dois = [d for d in documents if d.external_ids.doi and not d.external_ids.doi.startswith("10.")]
        if not invalid_dois:
            quality_checks.append(("✓", "No invalid DOIs found"))
        else:
            quality_checks.append(("⚠", f"{len(invalid_dois)} documents with invalid DOI format"))

        # Check for abstracts
        if stats['with_abstract'] < stats['total']:
            missing_abstracts = stats['total'] - stats['with_abstract']
            quality_checks.append(("⚠", f"{missing_abstracts} documents missing abstracts"))

        # Check for duplicates
        if results['duplicate_titles'] > 0:
            quality_checks.append(("⚠", f"{results['duplicate_titles']} documents with duplicate titles (potential duplicates)"))

        for symbol, message in quality_checks:
            if symbol == "✓":
                console.print(f"  [green]{symbol}[/green] {message}")
            elif symbol == "⚠":
                console.print(f"  [yellow]{symbol}[/yellow] {message}")
            else:
                console.print(f"  [red]{symbol}[/red] {message}")

        # Print errors and warnings if requested
        if show_errors:
            if errors:
                console.print()
                print_section("Errors")
                for error in errors[:10]:  # Show first 10
                    print_error(error)
                if len(errors) > 10:
                    console.print(f"  ... and {len(errors) - 10} more errors")

            if warnings:
                console.print()
                print_section("Warnings")
                for warning in warnings[:10]:  # Show first 10
                    print_warning(warning)
                if len(warnings) > 10:
                    console.print(f"  ... and {len(warnings) - 10} more warnings")

    # Final summary
    console.print()
    console.rule()

    if not stats_only:
        if errors:
            print_error(f"Validation complete - {len(warnings)} warnings, {len(errors)} errors")
        elif warnings:
            print_warning(f"Validation complete - {len(warnings)} warnings, 0 errors")
        else:
            print_success("Validation complete - no warnings or errors")
    else:
        print_success("Statistics generated")

    console.print()

    # Save report if requested
    if report:
        report_lines = [
            "Simple SLR Validation Report",
            "=" * 70,
            "",
            f"Source: {data_source}",
            f"Total documents: {stats['total']:,}",
            "",
            "Document Statistics:",
            f"  Documents with DOI:      {stats['with_doi']:,} ({stats['with_doi']/stats['total']*100:.1f}%)",
            f"  Documents with abstract: {stats['with_abstract']:,} ({stats['with_abstract']/stats['total']*100:.1f}%)",
            f"  Documents with arXiv ID: {stats['with_arxiv_id']:,} ({stats['with_arxiv_id']/stats['total']*100:.1f}%)",
            "",
            "Provider Distribution:",
        ]

        for provider, count in stats["providers"].most_common():
            percentage = count / stats["total"] * 100
            report_lines.append(f"  {provider}: {count:,} ({percentage:.1f}%)")

        report_lines.extend(["", "Year Distribution:"])
        for year in sorted(stats["years"].keys()):
            count = stats["years"][year]
            percentage = count / stats["total"] * 100
            report_lines.append(f"  {year}: {count:,} ({percentage:.1f}%)")

        if not stats_only:
            report_lines.extend(["", "Validation Results:"])
            report_lines.append(f"  Errors: {len(errors)}")
            report_lines.append(f"  Warnings: {len(warnings)}")

            if errors:
                report_lines.extend(["", "Errors:"])
                report_lines.extend(f"  {e}" for e in errors)

            if warnings:
                report_lines.extend(["", "Warnings:"])
                report_lines.extend(f"  {w}" for w in warnings)

        report.write_text("\n".join(report_lines), encoding="utf-8")
        console.print(f"  Report saved to [cyan]{report}[/cyan]")
        console.print()

