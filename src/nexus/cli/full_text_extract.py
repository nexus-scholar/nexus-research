"""
Full-text LLM extraction command.

Runs schema-driven field extraction on extracted chunks.
"""

from pathlib import Path
from typing import Optional

import click

from nexus.cli.formatting import console, print_error, print_header, print_success
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_path = extractor.extract_from_directory(input_dir, output_path)

    print_success(f"Extraction complete! Results saved to {result_path}")
    console.print(f"Schema: {config.schema_path}")
    console.print(f"Model: {config.model}")
