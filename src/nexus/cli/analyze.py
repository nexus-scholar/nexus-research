"""
Analysis command.

Extracts structured insights from processed Markdown files.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Optional

import click
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from nexus.cli.formatting import console, print_header, print_success
from nexus.cli.main import pass_context
from nexus.analysis.engine import AnalysisEngine

@click.command()
@click.option(
    "--input",
    "input_dir",
    type=click.Path(exists=True, path_type=Path),
    default=Path("results/extraction"),
    help="Directory containing extracted paper folders.",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=Path("analysis_workspace"),
    help="Directory for aggregated analysis reports.",
)
@click.option(
    "--limit",
    type=int,
    help="Limit number of papers to analyze.",
)
@click.option(
    "--model",
    type=str,
    default="google/gemini-2.0-flash-001",
    help="LLM model to use.",
)
@pass_context
def analyze(ctx, input_dir: Path, output_dir: Path, limit: Optional[int], model: str):
    """Analyze papers to extract structured insights.

    Reads markdown files from the extraction folder, uses an LLM to extract
    metadata (models, accuracy, datasets), and aggregates them into a CSV.
    """
    print_header("Nexus Analysis", "LLM-based Literature Synthesis")

    # Find papers
    # Look for any folder containing a *_body.md file
    paper_dirs = []
    for d in input_dir.iterdir():
        if d.is_dir():
            if list(d.glob("*_body.md")):
                paper_dirs.append(d)
    
    if limit:
        paper_dirs = paper_dirs[:limit]
        console.print(f"[yellow]Limiting to first {limit} papers[/yellow]")

    console.print(f"Found {len(paper_dirs)} processed papers.")
    
    # Init engine
    engine = AnalysisEngine(model=model)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    analyzed_data = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Analyzing...", total=len(paper_dirs))
        
        for p_dir in paper_dirs:
            # Find the markdown file
            md_files = list(p_dir.glob("*_body.md"))
            if not md_files:
                progress.advance(task)
                continue
            md_file = md_files[0]
            
            json_file = p_dir / "analysis.json"
            
            # Skip if already analyzed
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        data["source"] = p_dir.name
                        analyzed_data.append(data)
                    progress.advance(task)
                    continue
                except:
                    pass

            # Analyze
            result = engine.analyze_markdown(md_file)
            
            if result:
                # Validation Check
                if not result.models_used:
                    console.print(f"  [yellow]Warning: No models found in {p_dir.name}[/yellow]")
                
                # Save individual result
                with open(json_file, "w", encoding="utf-8") as f:
                    f.write(result.model_dump_json(indent=2))
                
                # Add to aggregate list
                flat = result.model_dump()
                flat["source"] = p_dir.name
                analyzed_data.append(flat)
            
            progress.advance(task)

    # Aggregate Results
    if analyzed_data:
        df = pd.DataFrame(analyzed_data)
        
        # Validation Stats
        valid_models = df[df["models_used"].apply(lambda x: len(x) > 0)]
        console.print(f"\n[bold]Validation:[/bold] {len(valid_models)}/{len(df)} papers have extracted models.")
        
        # Flatten lists for CSV readability
        for col in ["models_used", "datasets", "limitations"]:
            df[col] = df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
            
        csv_path = output_dir / "literature_matrix.csv"
        df.to_csv(csv_path, index=False)
        
        print_success(f"Analysis complete! Aggregated data saved to: {csv_path}")
        
        # Simple stats
        console.print("\n[bold]Top Models Used:[/bold]")
        all_models = []
        for item in analyzed_data:
            all_models.extend(item["models_used"])
        from collections import Counter
        for m, c in Counter(all_models).most_common(5):
            console.print(f"  - {m}: {c}")

    else:
        console.print("[red]No analysis data generated.[/red]")
