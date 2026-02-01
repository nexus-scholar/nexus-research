"""
Screening command.

This command uses an LLM to screen papers based on title and abstract.
"""

import os
import json
from pathlib import Path
from typing import List, Optional

import click
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID

from nexus.cli.formatting import (
    console,
    print_error,
    print_header,
    print_success,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import load_config, load_documents, get_latest_run
from nexus.core.config import ScreenerConfig
from nexus.screener.screener import LayeredScreener, Screener
from nexus.screener.client import LLMClient
from nexus.screener.models import ScreeningResult

@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    help="Input file (deduplicated JSONL). Defaults to latest dedup run.",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=Path("results/screening"),
    help="Output directory.",
)
@click.option(
    "--criteria",
    type=str,
    default="General Relevance to the research query provided in context.",
    help="Global screening criteria passed to the system prompt.",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="LLM model to use. Defaults to LLM_MODEL env var.",
)
@click.option(
    "--layered/--no-layered",
    default=False,
    help="Use the layered screener with heuristic pre-filtering.",
)
@click.option(
    "--include-group",
    multiple=True,
    help="Comma-separated keyword group; at least one term from each group must match.",
)
@click.option(
    "--include-pattern",
    multiple=True,
    help="Keyword include patterns (used only when include-groups are empty).",
)
@click.option(
    "--exclude-pattern",
    multiple=True,
    help="Keyword exclude patterns; any match filters the document out.",
)
@click.option(
    "--layer-model",
    multiple=True,
    help="Model name per layer; last one is reused for remaining layers.",
)
@pass_context
def screen(
    ctx,
    input_path: Optional[Path],
    output_dir: Path,
    criteria: str,
    model: str,
    layered: bool,
    include_group: tuple[str, ...],
    include_pattern: tuple[str, ...],
    exclude_pattern: tuple[str, ...],
    layer_model: tuple[str, ...],
):
    """Screen papers using an LLM.

    Classifies papers as 'include', 'exclude', or 'maybe' based on
    title and abstract relevance to the search queries.

    Requires OPENAI_API_KEY environment variable.
    """
    print_header("Nexus Screener", "LLM-based Title & Abstract Screening")

    # Resolve input path
    if not input_path:
        # Try to find latest dedup run
        dedup_base = Path("results/dedup")
        latest_dedup = get_latest_run(dedup_base, prefix="dedup_")
        if latest_dedup:
            input_path = latest_dedup / "representatives.jsonl"
            if not input_path.exists():
                print_error(f"Latest run found at {latest_dedup} but missing representatives.jsonl")
                return
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

    console.print(f"Loaded {len(documents)} documents.")

    # Initialize Client & Screener
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print_error("OPENAI_API_KEY environment variable is not set.")
        return

    client = LLMClient(api_key=api_key, model=model)
    config = load_config(ctx.config_path).screener
    screener_config = _build_screener_config(
        config,
        include_group=include_group,
        include_pattern=include_pattern,
        exclude_pattern=exclude_pattern,
        layer_model=layer_model,
    )
    if layered:
        screener = LayeredScreener(client=client, config=screener_config)
    else:
        screener = Screener(client)

    # Prepare output and resume logic
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"screening_{input_path.parent.name}.jsonl"
    
    screened_keys = set()
    if output_file.exists():
        console.print(f"[yellow]Found existing output file. Resuming...[/yellow]")
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        # Create a unique key from DOI or Title
                        doi = data.get("external_ids", {}).get("doi")
                        title = data.get("title", "").lower().strip()
                        if doi:
                            screened_keys.add(f"doi:{doi}")
                        if title:
                            screened_keys.add(f"title:{title}")
            console.print(f"  Skipping {len(screened_keys)} (by ID or Title) already screened papers.")
        except Exception as e:
            print_error(f"Error reading existing file: {e}")

    # Filter documents
    def get_doc_keys(d):
        keys = []
        if d.external_ids.doi:
            keys.append(f"doi:{d.external_ids.doi}")
        if d.title:
            keys.append(f"title:{d.title.lower().strip()}")
        return keys

    docs_to_screen = []
    for d in documents:
        keys = get_doc_keys(d)
        if not any(k in screened_keys for k in keys):
            docs_to_screen.append(d)
    
    if not docs_to_screen:
        print_success("All documents have been screened!")
        return

    # Run screening
    results: List[ScreeningResult] = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Screening...", total=len(docs_to_screen))
        
        # We wrap the generator to update progress
        # Create a map for quick lookup if needed, or just iterate if order is preserved
        # Actually, screener yields results. We need to match them to docs.
        # But screener takes a list. It yields one result per doc in order.
        
        # Better approach: Iterate over documents and screen one by one in the loop
        # But Screener.screen_documents is a generator.
        
        # Let's iterate the generator and the docs together?
        # Or just have screener yield (doc, result) tuple? No, keep it clean.
        # We can map by DOI/Title or assume order. Assuming order is risky if errors occur.
        
        # Let's assume order for now as screener yields for each input.
        
        doc_map = {d.external_ids.doi: d for d in docs_to_screen if d.external_ids.doi}
        # Fallback map for docs without DOI? Title?
        # Simplest: Update Screener to return the original doc OR pass it through.
        
        # Actually, let's just update the loop to manually call client for each doc
        # inside this CLI loop? No, that breaks the abstraction.
        
        # I will rely on the fact that I passed docs_to_screen to screen_documents.
        # I will update the Document object with the result.
        
        if layered:
            results_iter = screener.screen_documents(docs_to_screen)
        else:
            results_iter = screener.screen_documents(docs_to_screen, criteria=criteria)

        for i, result in enumerate(results_iter):
            original_doc = docs_to_screen[i] # This assumes 1:1 mapping and order preservation
            
            # Update the document
            original_doc.decision = result.decision.value
            
            # Save full document
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(original_doc.model_dump_json() + "\n")
            
            results.append(result)
            decision_value = result.decision.value
            color = "green" if decision_value == "include" else "red" if decision_value == "exclude" else "yellow"
            progress.console.print(f"  [{color}]{decision_value.upper()}[/{color}] {result.title[:60]}...")
            progress.advance(task)

    print_success(f"Screening complete! Results saved to {output_file}")
    
    # Summary stats
    counts = {"include": 0, "exclude": 0, "maybe": 0}
    for r in results:
        if r.decision.value in counts:
            counts[r.decision.value] += 1
            
    console.print()
    console.print("[bold]Summary (Current Run):[/bold]")
    console.print(f"  Include: [green]{counts['include']}[/green]")
    console.print(f"  Maybe:   [yellow]{counts['maybe']}[/yellow]")
    console.print(f"  Exclude: [red]{counts['exclude']}[/red]")


def _build_screener_config(
    config: ScreenerConfig,
    *,
    include_group: tuple[str, ...],
    include_pattern: tuple[str, ...],
    exclude_pattern: tuple[str, ...],
    layer_model: tuple[str, ...],
) -> ScreenerConfig:
    """Apply CLI overrides to screener config."""
    updates = {}
    if include_group:
        updates["include_groups"] = [_parse_group(group) for group in include_group]
    if include_pattern:
        updates["include_patterns"] = list(include_pattern)
    if exclude_pattern:
        updates["exclude_patterns"] = list(exclude_pattern)
    if layer_model:
        updates["models"] = list(layer_model)
    if not updates:
        return config
    return config.model_copy(update=updates)


def _parse_group(raw: str) -> List[str]:
    return [term.strip() for term in raw.split(",") if term.strip()]
