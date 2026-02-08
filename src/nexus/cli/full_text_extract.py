"""
Full-text LLM extraction command.

Runs schema-driven field extraction on extracted chunks.
"""

from pathlib import Path
from typing import Any, Optional

import click

from rich.table import Table

from nexus.cli.formatting import (
    console,
    format_number,
    print_error,
    print_header,
    print_info,
    print_section,
    print_success,
    print_warning,
)
from nexus.cli.main import pass_context
from nexus.cli.utils import load_config
from nexus.extraction.full_text_extractor import FullTextExtractor


@click.command()
@click.option(
    "--input",
    "input_dir",
    type=click.Path(exists=True, path_type=Path),
    default=Path("results/clean_extract"),
    help="Directory containing extracted paper folders with *_chunks.json.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=Path("results/full_text_extraction.json"),
    help="Output JSON file for extracted fields.",
)
@click.option(
    "--schema",
    "schema_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Schema YAML path (overrides config).",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="LLM model to use (overrides config).",
)
@click.option(
    "--max-tokens",
    type=int,
    default=None,
    help="Approximate max tokens per group (overrides config).",
)
@click.option(
    "--require-evidence/--no-require-evidence",
    default=None,
    help="Include evidence snippets per field.",
)
@click.option(
    "--resume/--no-resume",
    default=None,
    help="Skip papers already in output file.",
)
@click.option(
    "--log-prompts/--no-log-prompts",
    default=None,
    help="Store prompt/response metadata in output.",
)
@click.option(
    "--dry-run/--no-dry-run",
    default=False,
    help="Build prompts and print token estimates without calling the LLM.",
)
@click.option(
    "--groups",
    "groups",
    multiple=True,
    help="Only run these group ids (comma-separated or repeat).",
)
@pass_context
def full_text_extract(
    ctx,
    input_dir: Path,
    output_path: Path,
    schema_path: Optional[Path],
    model: Optional[str],
    max_tokens: Optional[int],
    require_evidence: Optional[bool],
    resume: Optional[bool],
    log_prompts: Optional[bool],
    dry_run: bool,
    groups: tuple[str, ...],
):
    """Run schema-driven full-text extraction."""
    print_header("Full-Text Extraction", "Schema-driven LLM extraction")

    if not input_dir.exists():
        print_error(f"Input directory not found: {input_dir}")
        return

    config = load_config(ctx.config_path).full_text_extraction
    if schema_path:
        config.schema_path = schema_path
    if model:
        config.model = model
    if max_tokens:
        config.max_tokens = max_tokens
    if require_evidence is not None:
        config.require_evidence = require_evidence
    if resume is not None:
        config.resume = resume
    if log_prompts is not None:
        config.log_prompts = log_prompts

    extractor = FullTextExtractor(config=config)
    group_ids = sorted({g.strip() for value in groups for g in value.split(",") if g.strip()}) or None

    if dry_run:
        print_info("Dry run: building prompts and estimating tokens (no API calls).")
        batches = extractor.plan_batches(input_dir, output_path, group_ids=group_ids)
        if not batches:
            print_warning("No batches to process. Check input directory and resume settings.")
            return

        group_stats: dict[str, dict[str, Any]] = {}
        total_prompt_tokens = 0
        total_excerpt_tokens = 0
        unique_papers: set[str] = set()

        for batch in batches:
            group_id = batch["group_id"]
            stats = group_stats.setdefault(
                group_id,
                {
                    "model": batch["model"],
                    "batches": 0,
                    "prompt_tokens": 0,
                    "excerpt_tokens": 0,
                    "papers": set(),
                },
            )
            stats["batches"] += 1
            stats["prompt_tokens"] += batch["prompt_tokens"]
            excerpt_tokens = sum(item["token_estimate"] for item in batch["payload"])
            stats["excerpt_tokens"] += excerpt_tokens
            stats["papers"].update(item["paper_id"] for item in batch["payload"])

            total_prompt_tokens += batch["prompt_tokens"]
            total_excerpt_tokens += excerpt_tokens
            unique_papers.update(item["paper_id"] for item in batch["payload"])

        print_section("Dry-Run Token Estimates")
        table = Table(show_header=True)
        table.add_column("Group", style="cyan")
        table.add_column("Model", style="green")
        table.add_column("Batches", justify="right")
        table.add_column("Papers", justify="right")
        table.add_column("Prompt Tokens", justify="right")
        table.add_column("Excerpt Tokens", justify="right")
        table.add_column("Avg Prompt/Batch", justify="right")

        for group_id, stats in group_stats.items():
            batches_count = stats["batches"] or 1
            avg_prompt = stats["prompt_tokens"] // batches_count
            table.add_row(
                group_id,
                str(stats["model"]),
                format_number(stats["batches"]),
                format_number(len(stats["papers"])),
                format_number(stats["prompt_tokens"]),
                format_number(stats["excerpt_tokens"]),
                format_number(avg_prompt),
            )

        console.print(table)
        console.print(
            f"Total papers: {format_number(len(unique_papers))} | "
            f"Total batches: {format_number(len(batches))} | "
            f"Prompt tokens (est.): {format_number(total_prompt_tokens)} | "
            f"Excerpt tokens (est.): {format_number(total_excerpt_tokens)}"
        )
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_path = extractor.extract_from_directory(input_dir, output_path, group_ids=group_ids)

    print_success(f"Extraction complete! Results saved to {result_path}")
    console.print(f"Schema: {config.schema_path}")
    console.print(f"Model: {config.model}")
