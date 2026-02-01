"""
Search command for querying academic databases.

This command executes searches across configured providers in parallel.
"""

import concurrent.futures
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import click
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

from nexus.cli.formatting import (
    console,
    create_progress,
    format_duration,
    format_number,
    print_config,
    print_error,
    print_header,
    print_provider_results,
    print_success,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import (
    generate_run_id,
    load_config,
    load_documents,
    load_queries,
    save_documents,
    save_metadata,
)
from nexus.core.config import ProviderConfig, SLRConfig
from nexus.core.models import Query, Document
from nexus.providers import get_provider


def _search_provider_worker(
    provider_name: str,
    config: SLRConfig,
    all_queries: List[Dict[str, Any]],
    output_dir: Path,
    max_results: Optional[int],
    output_format: str,
    progress: Progress,
    task_id: Any,
    resume: bool = False,
) -> tuple[int, Dict[str, str]]:
    """Worker function to search a single provider.
    
    Returns:
        Tuple of (total_count, query_id_to_translated_string_map)
    """
    
    # Get provider config
    prov_config = config.providers.get_provider(provider_name)
    if not prov_config:
        prov_config = ProviderConfig()

    # Override mailto if set in main config
    if config.mailto:
        prov_config.mailto = config.mailto

    # Create provider instance
    try:
        provider_instance = get_provider(provider_name, prov_config)
    except Exception as e:
        progress.console.print(f"[red]Failed to initialize {provider_name}: {e}[/red]")
        return 0, {}

    # Create provider output directory
    provider_dir = output_dir / provider_name
    provider_dir.mkdir(exist_ok=True)

    provider_total = 0
    all_provider_docs = []
    translated_queries = {}

    for q_info in all_queries:
        query_file = provider_dir / f"{q_info['id']}_results.jsonl"
        
        # Create Query object
        query_obj = Query(
            text=q_info["text"],
            year_min=config.year_min,
            year_max=config.year_max,
            max_results=max_results,
        )

        # Check resume condition
        if resume and query_file.exists() and query_file.stat().st_size > 0:
            try:
                # Load existing documents to maintain counts and aggregation
                existing_docs = load_documents(query_file)
                if existing_docs:
                    all_provider_docs.extend(existing_docs)
                    provider_total += len(existing_docs)
                    
                    # Capture the query translation even if resuming
                    # We run translation but skip the search
                    try:
                        provider_instance._translate_query(query_obj)
                        translated_queries[q_info['id']] = provider_instance.get_last_query()
                    except:
                        pass

                    progress.update(task_id, advance=1)
                    continue
            except Exception:
                # If load fails, ignore and re-run search
                pass

        # Execute search
        try:
            # Fetch results
            raw_docs = list(provider_instance.search(query_obj))
            
            # Store translated query
            translated_queries[q_info['id']] = provider_instance.get_last_query()

            # Hydrate documents with query context
            for d in raw_docs:
                d.query_id = q_info['id']
                d.query_text = q_info['text']

            # Apply post-search quality filters (include_any / exclude_any)
            filtered_docs = [
                d for d in raw_docs if _passes_quality_filters(d, q_info)
            ]

            if filtered_docs:
                # Save per-query results
                save_documents(filtered_docs, query_file, format="jsonl")

                all_provider_docs.extend(filtered_docs)
                provider_total += len(filtered_docs)

    # Save aggregated results
    if all_provider_docs:
        all_results_file = provider_dir / "all_results.jsonl"
        save_documents(all_provider_docs, all_results_file, format="jsonl")

        # Save CSV if requested
        if output_format in ("csv", "both"):
            csv_file = provider_dir / "all_results.csv"
            save_documents(all_provider_docs, csv_file, format="csv")

    return provider_total, translated_queries


@click.command()
@click.option(
    "--queries",
    type=click.Path(exists=True, path_type=Path),
    help="Path to queries file (YAML/JSON)",
)
@click.option(
    "--query",
    type=str,
    help="Single query string (quick search)",
)
@click.option(
    "--query-id",
    type=str,
    help="Search specific query ID from queries file",
)
@click.option(
    "--provider",
    multiple=True,
    help="Specific provider(s) to use (can repeat)",
)
@click.option(
    "--skip-provider",
    multiple=True,
    help="Provider(s) to skip",
)
@click.option(
    "--year-min",
    type=int,
    help="Minimum publication year",
)
@click.option(
    "--year-max",
    type=int,
    help="Maximum publication year",
)
@click.option(
    "--max-results",
    type=int,
    help="Maximum results per query (per provider)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=Path("results/outputs"),
    help="Output directory",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "jsonl", "both"], case_sensitive=False),
    default="both",
    help="Output format",
)
@click.option(
    "--run-id",
    type=str,
    help="Custom run identifier",
)
@click.option(
    "--resume",
    is_flag=True,
    help="Resume interrupted search",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be searched without executing",
)
@click.option(
    "--parallel/--no-parallel",
    default=True,
    help="Enable/disable parallel execution",
)
@pass_context
def search(
    ctx,
    queries: Optional[Path],
    query: Optional[str],
    query_id: Optional[str],
    provider: tuple,
    skip_provider: tuple,
    year_min: Optional[int],
    year_max: Optional[int],
    max_results: Optional[int],
    output: Path,
    output_format: str,
    run_id: Optional[str],
    resume: bool,
    dry_run: bool,
    parallel: bool,
):
    """Search academic databases.

    Execute searches across configured providers and save results.

    \b
    Examples:
      # Search with queries file
      slr search --queries queries.yml

      # Quick single query search
      slr search --query "machine learning AND agriculture"

      # Search specific providers only
      slr search --queries queries.yml --provider openalex --provider arxiv

      # Search with filters
      slr search --queries queries.yml --year-min 2020 --max-results 500
    """
    start_time = time.time()

    print_header("Simple SLR Search", "Multi-provider academic database search")

    # Load configuration
    config = load_config(ctx.config_path)

    # Override config with CLI options
    if year_min is not None:
        config.year_min = year_min
    if year_max is not None:
        config.year_max = year_max

    # Determine queries to search
    queries_data = {}
    if query:
        # Single query from command line
        queries_data = {"cli_query": [query]}
    elif queries:
        # Load from file
        queries_data = load_queries(queries)
    else:
        print_error("Either --queries or --query must be specified")
        raise click.Abort()

    # Flatten queries for processing
    all_queries = []
    
    # Check for new structured format
    if isinstance(queries_data, dict) and "queries" in queries_data and isinstance(queries_data["queries"], list):
        # New structured format: {"queries": [{"id": "...", "query": "..."}]}
        for q_item in queries_data["queries"]:
            # Filter by query_id if specified
            if query_id and q_item.get("id") != query_id:
                continue
            
            # Extract query text (handle 'query' or 'text' keys)
            text = q_item.get("query") or q_item.get("text")
            if not text:
                continue

            all_queries.append({
                "id": q_item.get("id", f"Q{len(all_queries)+1:02d}"),
                "category": q_item.get("theme", "general"),
                "text": text,
                "metadata": {
                    "priority": q_item.get("priority"),
                    "include_any": q_item.get("include_any"),
                    "exclude_any": q_item.get("exclude_any"),
                }
            })
            
    else:
        # Legacy format: Dict[category, List[str]]
        # or simplified structured format if load_queries returns dict
        query_counter = 1
        
        # If filtering by query_id (category name in legacy mode)
        if query_id and query_id in queries_data:
             queries_data = {query_id: queries_data[query_id]}
        elif query_id and query_id not in queries_data and not query:
             print_error(f"Category '{query_id}' not found in queries file")
             raise click.Abort()

        for category, query_list in queries_data.items():
            if not isinstance(query_list, list):
                continue
                
            for q in query_list:
                all_queries.append({
                    "id": f"Q{query_counter:02d}",
                    "category": category,
                    "text": q,
                })
                query_counter += 1

    if not all_queries:
        print_error("No queries to search")
        raise click.Abort()

    # Determine which providers to use
    enabled_providers = []
    if provider:
        # Use specified providers
        enabled_providers = list(provider)
    else:
        # Use all enabled providers from config
        enabled_providers = config.providers.get_enabled_providers()

    # Remove skipped providers
    if skip_provider:
        enabled_providers = [p for p in enabled_providers if p not in skip_provider]

    if not enabled_providers:
        print_error("No providers enabled")
        raise click.Abort()

    # Calculate unique categories
    unique_categories = {q['category'] for q in all_queries}
    num_categories = len(unique_categories)

    # Generate run ID
    if not run_id:
        run_id = generate_run_id()

    # Set up output directory
    output_dir = output / run_id

    # Print configuration
    print_config({
        "Queries": f"{len(all_queries)} queries from {num_categories} categories",
        "Providers": ", ".join(enabled_providers),
        "Year range": f"{config.year_min or 'any'}-{config.year_max or 'current'}",
        "Max results": max_results or "unlimited",
        "Output": str(output_dir),
        "Parallel": str(parallel),
    })

    if dry_run:
        console.print("\n[yellow]DRY RUN - No searches will be executed[/yellow]\n")
        console.print("[bold]Queries to be executed:[/bold]")
        for q in all_queries:
            console.print(f"  {q['id']} ({q['category']}): {q['text']}")
        return

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Execute searches
    provider_results: Dict[str, int] = {}
    query_details: Dict[str, Dict[str, str]] = {}
    
    console.print(f"\n[bold]Starting search execution...[/bold]\n")

    # Use ThreadPoolExecutor for parallel execution
    max_workers = len(enabled_providers) if parallel else 1
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        console=console,
    ) as progress:
        
        futures = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for prov_name in enabled_providers:
                # Add task for this provider
                task_id = progress.add_task(
                    f"[cyan]{prov_name}[/cyan]", 
                    total=len(all_queries)
                )
                
                # Submit worker
                future = executor.submit(
                    _search_provider_worker,
                    prov_name,
                    config,
                    all_queries,
                    output_dir,
                    max_results,
                    output_format,
                    progress,
                    task_id,
                    resume,
                )
                futures[future] = prov_name

            # Wait for completion and gather results
            for future in concurrent.futures.as_completed(futures):
                prov_name = futures[future]
                try:
                    count, translations = future.result()
                    provider_results[prov_name] = count
                    
                    # Merge translations into query_details map: QID -> {provider: string}
                    for qid, q_str in translations.items():
                        if qid not in query_details:
                            query_details[qid] = {}
                        query_details[qid][prov_name] = q_str
                        
                except Exception as e:
                    print_error(f"Provider {prov_name} crashed: {e}")
                    provider_results[prov_name] = 0

    # Save metadata
    metadata = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "queries": all_queries,
        "query_details": query_details, # New field for scientific provenance
        "providers": enabled_providers,
        "config": {
            "year_min": config.year_min,
            "year_max": config.year_max,
            "max_results": max_results,
        },
        "results": provider_results,
    }
    save_metadata(output_dir, metadata)

    # Save summary
    summary_lines = [
        f"Simple SLR Search Results",
        f"=" * 70,
        f"",
        f"Run ID: {run_id}",
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"Queries: {len(all_queries)} queries from {num_categories} categories",
        f"Providers: {', '.join(enabled_providers)}",
        f"",
        f"Results by Provider:",
    ]

    total_docs = 0
    for prov_name, count in provider_results.items():
        summary_lines.append(f"  {prov_name}: {count:,} documents")
        total_docs += count

    summary_lines.extend([
        f"",
        f"Total: {total_docs:,} documents",
        f"Duration: {format_duration(time.time() - start_time)}",
    ])

    summary_path = output_dir / "summary.txt"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    # Print final summary
    console.print()
    console.rule()
    print_success("Search complete!")
    console.print()
    print_provider_results(provider_results)
    console.print()
    console.print(f"  Output: [cyan]{output_dir}[/cyan]")
    console.print(f"  Duration: [cyan]{format_duration(time.time() - start_time)}[/cyan]")
    console.print()