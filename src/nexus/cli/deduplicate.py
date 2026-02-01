"""
Deduplication command.

This command identifies and clusters duplicate papers across providers.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import click

from nexus.cli.formatting import (
    console,
    create_progress,
    format_duration,
    format_number,
    print_config,
    print_error,
    print_header,
    print_section,
    print_statistics,
    print_success,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import (
    generate_dedup_id,
    get_latest_run,
    load_config,
    load_documents,
    load_documents_from_directory,
    save_documents,
    save_metadata,
)
from nexus.core.config import DeduplicationConfig, DeduplicationStrategy
from nexus.core.models import Document
from nexus.dedup import Deduplicator


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Input directory or file (search output)",
)
@click.option(
    "--format",
    "input_format",
    type=click.Choice(["auto", "jsonl", "csv"], case_sensitive=False),
    default="auto",
    help="Input format",
)
@click.option(
    "--strategy",
    type=click.Choice(["conservative", "semantic"], case_sensitive=False),
    help="Deduplication strategy",
)
@click.option(
    "--fuzzy-threshold",
    type=click.IntRange(0, 100),
    help="Fuzzy matching threshold 0-100",
)
@click.option(
    "--max-year-gap",
    type=int,
    help="Max year difference for duplicates",
)
@click.option(
    "--semantic-threshold",
    type=click.FloatRange(0.0, 1.0),
    help="Semantic similarity threshold 0.0-1.0",
)
@click.option(
    "--embedding-model",
    type=str,
    help="Model for embeddings",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=Path("results/dedup"),
    help="Output directory",
)
@click.option(
    "--export-format",
    type=click.Choice(["csv", "jsonl", "json", "all"], case_sensitive=False),
    default="all",
    help="Export formats",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show stats without writing output",
)
@pass_context
def deduplicate(
    ctx,
    input_path: Path,
    input_format: str,
    strategy: Optional[str],
    fuzzy_threshold: Optional[int],
    max_year_gap: Optional[int],
    semantic_threshold: Optional[float],
    embedding_model: Optional[str],
    output_path: Path,
    export_format: str,
    dry_run: bool,
):
    """Remove duplicate papers.

    Identify and cluster duplicate papers across providers using
    intelligent matching strategies.

    \b
    Examples:
      # Basic deduplication
      slr deduplicate --input outputs/run_2025-11-15_143022/

      # Conservative strategy with custom threshold
      slr deduplicate --input outputs/latest/ --fuzzy-threshold 95

      # Dry run to see statistics
      slr deduplicate --input outputs/latest/ --dry-run
    """
    start_time = time.time()

    print_header("Simple SLR Deduplication", "Intelligent duplicate detection")

    # Load configuration
    config = load_config(ctx.config_path)
    dedup_config = config.deduplication

    # Override config with CLI options
    if strategy:
        dedup_config.strategy = DeduplicationStrategy(strategy)
    if fuzzy_threshold is not None:
        dedup_config.fuzzy_threshold = fuzzy_threshold
    if max_year_gap is not None:
        dedup_config.max_year_gap = max_year_gap
    if semantic_threshold is not None:
        dedup_config.semantic_threshold = semantic_threshold
    if embedding_model:
        dedup_config.embedding_model = embedding_model

    # Check for semantic dependencies
    if dedup_config.strategy == DeduplicationStrategy.SEMANTIC:
        try:
            import sentence_transformers  # noqa
        except ImportError:
            print_error(
                "Semantic deduplication requires additional dependencies.\n"
                "Install with: pip install simple-slr[semantic]"
            )
            raise click.Abort()

    # Load documents and potentially metadata
    console.print("[bold]Loading documents...[/bold]")
    query_metadata = {}

    if input_path.is_file():
        documents = load_documents(input_path)
    else:
        documents = load_documents_from_directory(input_path)
        
        # Try to load query metadata for quality filtering
        meta_file = input_path / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    run_meta = json.load(f)
                    # Convert queries list to dict for fast lookup: QID -> query_info
                    if "queries" in run_meta:
                        query_metadata = {q["id"]: q for q in run_meta["queries"]}
                        console.print(f"  Loaded quality criteria for {len(query_metadata)} queries")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load query metadata: {e}[/yellow]")

    if not documents:
        print_error("No documents found in input")
        raise click.Abort()

    console.print(f"  Loaded {format_number(len(documents))} documents\n")

    # Print configuration
    # ... (print_config)

    # Create deduplicator
    deduplicator = Deduplicator(dedup_config)

    # Execute deduplication
    console.print()
    
    with create_progress() as progress:
        task = progress.add_task("[cyan]Deduplicating...", total=100)

        def progress_callback(message, percentage):
            progress.update(task, description=f"[cyan]{message}", completed=percentage)

        # Deduplicate with progress reporting AND quality filters
        clusters = deduplicator.deduplicate(
            documents, 
            query_metadata=query_metadata, 
            progress_callback=progress_callback
        )

        progress.update(task, description="[green]Deduplication complete", completed=100)

    # Calculate statistics
    num_removed_by_filters = deduplicator.removed_by_filters
    num_clusters = len(clusters)
    num_unique = sum(1 for c in clusters if len(c.members) == 1)
    num_duplicates = num_clusters - num_unique
    total_docs_initial = len(documents)
    total_docs_after_filters = sum(len(c.members) for c in clusters)
    avg_cluster_size = total_docs_after_filters / num_clusters if num_clusters > 0 else 0

    # ... (Count duplicate types loop)

    # Print statistics
    console.print()
    console.rule()
    print_success("Deduplication complete!")
    console.print()

    stats = {
        "Input documents": format_number(total_docs_initial),
        "Removed by filters": format_number(num_removed_by_filters),
        "Unique documents": f"{format_number(num_unique)} ({num_unique/total_docs_initial*100:.1f}%)",
        "Duplicate clusters": format_number(num_duplicates),
        "Average cluster size": f"{avg_cluster_size:.2f}",
    }
    print_statistics(stats, title="Statistics")

    # ... (Duplicates by type)

    # Generate PRISMA counts
    prisma_counts = {
        "identification": {
            "total_records": total_docs_initial,
            "records_by_provider": {},
        },
        "screening": {
            "records_after_quality_filter": total_docs_after_filters,
            "quality_filter_removed": num_removed_by_filters,
            "records_after_deduplication": num_unique,
            "duplicates_removed": num_duplicates,
        },
    }

    # Count by provider
    provider_counts = {}
    for doc in documents:
        provider_counts[doc.provider] = provider_counts.get(doc.provider, 0) + 1
    prisma_counts["identification"]["records_by_provider"] = provider_counts

    prisma_file = output_dir / "prisma_counts.json"
    with open(prisma_file, "w", encoding="utf-8") as f:
        json.dump(prisma_counts, f, indent=2)
    console.print(f"  ✓ PRISMA counts: [cyan]{prisma_file}[/cyan]")

    # Save metadata
    metadata = {
        "dedup_id": dedup_id,
        "timestamp": datetime.now().isoformat(),
        "input": str(input_path),
        "strategy": dedup_config.strategy.value,
        "config": {
            "fuzzy_threshold": dedup_config.fuzzy_threshold,
            "max_year_gap": dedup_config.max_year_gap,
            "semantic_threshold": dedup_config.semantic_threshold,
        },
        "statistics": {
            "input_documents": total_docs,
            "unique_documents": num_unique,
            "duplicate_clusters": num_duplicates,
            "average_cluster_size": avg_cluster_size,
            "exact_doi_matches": exact_doi,
            "exact_arxiv_matches": exact_arxiv,
            "fuzzy_title_matches": fuzzy_title,
        },
    }
    save_metadata(output_dir, metadata)

    # Save summary
    summary_lines = [
        "Simple SLR Deduplication Results",
        "=" * 70,
        "",
        f"Dedup ID: {dedup_id}",
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Strategy: {dedup_config.strategy.value}",
        f"Fuzzy threshold: {dedup_config.fuzzy_threshold}%",
        f"Max year gap: {dedup_config.max_year_gap}",
        "",
        "Statistics:",
        f"  Input documents:     {total_docs:,}",
        f"  Unique documents:    {num_unique:,} ({num_unique/total_docs*100:.1f}%)",
        f"  Duplicate clusters:  {num_duplicates:,}",
        f"  Average cluster size: {avg_cluster_size:.2f}",
        "",
        "Duplicates by type:",
        f"  Exact DOI matches:   {exact_doi:,} ({exact_doi/num_duplicates*100:.1f}%)" if num_duplicates > 0 else "  No duplicates",
        f"  Exact arXiv matches: {exact_arxiv:,} ({exact_arxiv/num_duplicates*100:.1f}%)" if num_duplicates > 0 else "",
        f"  Fuzzy title matches: {fuzzy_title:,} ({fuzzy_title/num_duplicates*100:.1f}%)" if num_duplicates > 0 else "",
        "",
        f"Duration: {format_duration(time.time() - start_time)}",
    ]

    summary_path = output_dir / "summary.txt"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    console.print()
    console.print(f"  Output: [cyan]{output_dir}[/cyan]")
    console.print(f"  Duration: [cyan]{format_duration(time.time() - start_time)}[/cyan]")
    console.print()

