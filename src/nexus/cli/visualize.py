"""
Visualize command.
"""

from pathlib import Path
import click
from nexus.analysis.visualize import generate_charts

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
    "output_dir",
    type=click.Path(path_type=Path),
    default=Path("analysis_workspace/plots"),
    help="Output directory for plots.",
)
def visualize(input_path: Path, output_dir: Path):
    """Generate plots from analysis results."""
    generate_charts(input_path, output_dir)
