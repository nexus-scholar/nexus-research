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
    type=click.Choice(["conservative", "semantic", "hybrid"], case_sensitive=False),
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
    if dedup_config.strategy in (DeduplicationStrategy.SEMANTIC, DeduplicationStrategy.HYBRID):
        try:
            import sentence_transformers  # noqa
        except ImportError:
            print_error(
                "Semantic deduplication requires additional dependencies.\n"
                "Install with: pip install simple-slr[semantic]"
            )
            raise click.Abort()

    # Load documents
    console.print("[bold]Loading documents...[/bold]")

    if input_path.is_file():
        documents = load_documents(input_path)
    else:
        documents = load_documents_from_directory(input_path)

    if not documents:
        print_error("No documents found in input")
        raise click.Abort()

    console.print(f"  Loaded {format_number(len(documents))} documents\n")

    # Print configuration
    print_config({
        "Input": str(input_path),
        "Documents": format_number(len(documents)),
        "Strategy": dedup_config.strategy.value,
        "Fuzzy threshold": f"{dedup_config.fuzzy_threshold}%",
        "Max year gap": dedup_config.max_year_gap,
    })

    if dry_run:
        console.print("\n[yellow]DRY RUN - No files will be modified[/yellow]\n")

    # Create deduplicator
    deduplicator = Deduplicator(dedup_config)

    # Execute deduplication
    console.print()
    print_section("Phase 1: Exact matching (DOI, arXiv ID)")

    with create_progress() as progress:
        task = progress.add_task("Deduplicating...", total=100)

        # Deduplicate
        clusters = deduplicator.deduplicate(documents)

        progress.update(task, completed=100)

    # Calculate statistics
    num_clusters = len(clusters)
    num_unique = sum(1 for c in clusters if len(c.members) == 1)
    num_duplicates = num_clusters - num_unique
    total_docs = sum(len(c.members) for c in clusters)
    avg_cluster_size = total_docs / num_clusters if num_clusters > 0 else 0

    # Count duplicate types
    exact_doi = 0
    exact_arxiv = 0
    fuzzy_title = 0

    for cluster in clusters:
        if len(cluster.members) > 1:
            # Check first two members to determine match type
            m1, m2 = cluster.members[0], cluster.members[1]

            if m1.external_ids.doi and m1.external_ids.doi == m2.external_ids.doi:
                exact_doi += 1
            elif m1.external_ids.arxiv_id and m1.external_ids.arxiv_id == m2.external_ids.arxiv_id:
                exact_arxiv += 1
            else:
                fuzzy_title += 1

    # Print statistics
    console.print()
    console.rule()
    print_success("Deduplication complete!")
    console.print()

    stats = {
        "Input documents": format_number(total_docs),
        "Unique documents": f"{format_number(num_unique)} ({num_unique/total_docs*100:.1f}%)",
        "Duplicate clusters": format_number(num_duplicates),
        "Average cluster size": f"{avg_cluster_size:.2f}",
    }
    print_statistics(stats, title="Statistics")

    console.print()
    console.print("[bold]Duplicates by type:[/bold]")
    if num_duplicates > 0:
        console.print(f"  Exact DOI matches:    {exact_doi:,} ({exact_doi/num_duplicates*100:.1f}%)")
        console.print(f"  Exact arXiv matches:  {exact_arxiv:,} ({exact_arxiv/num_duplicates*100:.1f}%)")
        console.print(f"  Fuzzy title matches:  {fuzzy_title:,} ({fuzzy_title/num_duplicates*100:.1f}%)")
    else:
        console.print("  No duplicates found")

    if dry_run:
        console.print("\n[yellow]Dry run complete - no files written[/yellow]")
        return

    # Generate output ID
    dedup_id = generate_dedup_id()
    output_dir = output_path / dedup_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save clusters (full format with all members)
    console.print()
    print_section("Saving results")

    clusters_file = output_dir / "clusters.jsonl"
    with open(clusters_file, "w", encoding="utf-8") as f:
        for cluster in clusters:
            cluster_data = {
                "cluster_id": cluster.cluster_id,
                "representative": cluster.representative.model_dump(),
                "members": [m.model_dump() for m in cluster.members],
                "size": len(cluster.members),
            }
            f.write(json.dumps(cluster_data, ensure_ascii=False) + "\n")
    console.print(f"  ✓ Clusters: [cyan]{clusters_file}[/cyan]")

    # Save representatives
    representatives = [c.representative for c in clusters]

    if export_format in ("jsonl", "all"):
        repr_jsonl = output_dir / "representatives.jsonl"
        save_documents(representatives, repr_jsonl, format="jsonl")
        console.print(f"  ✓ Representatives (JSONL): [cyan]{repr_jsonl}[/cyan]")

    if export_format in ("csv", "all"):
        repr_csv = output_dir / "representatives.csv"
        save_documents(representatives, repr_csv, format="csv")
        console.print(f"  ✓ Representatives (CSV): [cyan]{repr_csv}[/cyan]")

    if export_format in ("json", "all"):
        repr_json = output_dir / "representatives.json"
        save_documents(representatives, repr_json, format="json")
        console.print(f"  ✓ Representatives (JSON): [cyan]{repr_json}[/cyan]")

    # Save cluster mapping
    cluster_mapping = {}
    for cluster in clusters:
        cluster_mapping[cluster.cluster_id] = {
            "representative_title": cluster.representative.title,
            "member_count": len(cluster.members),
            "providers": list(set(m.provider for m in cluster.members)),
        }

    mapping_file = output_dir / "cluster_mapping.json"
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(cluster_mapping, f, indent=2, ensure_ascii=False)
    console.print(f"  ✓ Cluster mapping: [cyan]{mapping_file}[/cyan]")

    # Generate PRISMA counts
    prisma_counts = {
        "identification": {
            "total_records": total_docs,
            "records_by_provider": {},
        },
        "screening": {
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

