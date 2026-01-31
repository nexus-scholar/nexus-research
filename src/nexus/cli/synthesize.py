"""
Synthesize command.
"""

from pathlib import Path
import click
from nexus.analysis.synthesis import Synthesizer
from nexus.cli.formatting import console, print_header, print_success

@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("analysis_workspace/literature_matrix.csv"),
    help="Input CSV file.",
)
@click.option(
    "--output",
    "output_file",
    type=click.Path(path_type=Path),
    default=Path("analysis_workspace/DRAFT_REVIEW.md"),
    help="Output Markdown file.",
)
@click.option(
    "--model",
    type=str,
    default="google/gemini-2.0-flash-001",
    help="LLM model to use.",
)
def synthesize(input_path: Path, output_file: Path, model: str):
    """Generate a draft literature review from analysis data."""
    print_header("Nexus Synthesis", "Drafting Literature Review")
    
    synthesizer = Synthesizer(model=model)
    success = synthesizer.generate_review(input_path, output_file)
    
    if success:
        print_success(f"Draft generated: {output_file}")
    else:
        console.print("[red]Synthesis failed.[/red]")
