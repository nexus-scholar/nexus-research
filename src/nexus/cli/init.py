"""
Project initialization command.

This command sets up a new SLR project with proper structure and config files.
"""

from pathlib import Path
from typing import Optional

import click

from nexus.cli.formatting import (
    console,
    confirm,
    print_error,
    print_header,
    print_success,
    print_file_tree,
)
from nexus.cli.main import pass_context


# Template files content
CONFIG_TEMPLATE = """# Simple SLR Configuration
# Documentation: https://simple-slr.readthedocs.io

# General Settings
mailto: {mailto}  # Required for polite API crawling
year_min: {year_min}
language: en

# Provider Configuration
providers:
  openalex:
    enabled: {enable_openalex}
    rate_limit: 5.0  # requests per second
    timeout: 30

  crossref:
    enabled: {enable_crossref}
    rate_limit: 1.0
    timeout: 30

  arxiv:
    enabled: {enable_arxiv}
    rate_limit: 0.5  # arXiv requests slower rate
    timeout: 30

  semantic_scholar:
    enabled: {enable_s2}
    rate_limit: 1.0
    timeout: 30
    # api_key: ${{S2_API_KEY}}  # Uncomment and set in .env if needed

# Deduplication Settings
deduplication:
  strategy: conservative  # Options: conservative, semantic (v1.1+), hybrid (v1.1+)
  fuzzy_threshold: 97  # 0-100, higher = more strict
  max_year_gap: 1      # Maximum year difference for potential duplicates

# Screener Heuristics
screener:
  include_groups:
    - [
        "plant", "leaf", "crop", "fruit", "disease", "leaf spot", "rust",
        "mildew", "blight", "wilt", "tomato", "rice", "wheat", "maize",
        "banana", "grape", "apple", "potato"
      ]
    - [
        "deep learning", "cnn", "vgg", "resnet", "densenet", "efficientnet",
        "mobilenet", "convnext", "transformer", "vit", "swin", "yolo",
        "yolov8", "segmentation", "mask r-cnn", "graph neural network",
        "attention", "few-shot", "meta-learning", "self-supervised",
        "semi-supervised", "self-training", "representation learning",
        "transfer learning", "pruning", "quantization", "lightweight",
        "edge", "gan", "diffusion", "data augmentation"
      ]
  include_patterns: []
  exclude_patterns:
    - "weed"
    - "insect"
    - "pest"
    - "aphid"
    - "virus"
    - "fungus"
    - "remote sensing"
    - "hyperspectral imaging"
    - "hyperspectral"
    - "satellite"
    - "uav"
    - "drone"
    - "aerial"
    - "weed detection"
    - "weed control"
    - "pest detection"
    - "pest infestation"
    - "insect pest"
    - "yield prediction"
  models: []

# Output Settings
output:
  directory: outputs
  format: both  # Options: csv, jsonl, both, json
  include_raw: false
"""

QUERIES_TEMPLATE = """# Search Queries
# Each category contains multiple query variants

Example Category 1:
  - "machine learning AND agriculture"
  - "deep learning AND crop disease"
  - "computer vision AND plant pathology"

Example Category 2:
  - "systematic review AND methodology"
  - "literature review AND best practices"
"""

ENV_TEMPLATE = """# Environment Variables
# Copy this to .env and fill in your values

# Semantic Scholar API key (optional, but recommended for higher rate limits)
# S2_API_KEY=your_key_here

# Email for polite API crawling (can also be set in config.yml)
# MAILTO=your.email@example.com
"""

GITIGNORE_TEMPLATE = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
dist/
build/

# Virtual environments
venv/
env/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Simple SLR
outputs/
dedup/
exports/
*.log

# Environment
.env

# OS
.DS_Store
Thumbs.db
"""

README_TEMPLATE = """# {project_name}

Systematic Literature Review project using Simple SLR.

## Setup

1. Install dependencies:
   ```bash
   pip install simple-slr
   ```

2. Configure your search:
   - Edit `config.yml` with your email and preferences
   - Edit `queries.yml` with your search queries

3. Run the workflow:
   ```bash
   # Search academic databases
   slr search --queries queries.yml

   # Deduplicate results
   slr deduplicate --input outputs/latest/

   # Export to BibTeX
   slr export --input dedup/latest/representatives.jsonl --format bibtex
   ```

## Project Structure

- `config.yml` - Main configuration
- `queries.yml` - Search queries
- `outputs/` - Raw search results
- `dedup/` - Deduplicated results
- `exports/` - Final exports (BibTeX, CSV, etc.)

## Documentation

See https://simple-slr.readthedocs.io for full documentation.
"""


@click.command()
@click.argument(
    "project_dir",
    type=click.Path(path_type=Path),
    default=".",
)
@click.option(
    "--template",
    type=click.Choice(["minimal", "standard", "full"], case_sensitive=False),
    default="standard",
    help="Template to use",
)
@click.option(
    "--no-git",
    is_flag=True,
    help="Don't initialize git repository",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing files",
)
@click.option(
    "--interactive", "-i",
    is_flag=True,
    help="Interactive configuration wizard",
)
@pass_context
def init(ctx, project_dir: Path, template: str, no_git: bool, force: bool, interactive: bool):
    """Initialize a new SLR project.

    Creates project structure with configuration files, query templates,
    and directory structure.

    \b
    Examples:
      slr init                    # Initialize in current directory
      slr init my_review          # Initialize in new directory
      slr init --interactive      # Interactive setup wizard
    """
    print_header("Initialize Simple SLR Project", f"Template: {template}")

    # Resolve project directory
    project_dir = project_dir.resolve()

    # Check if directory exists and has files
    if project_dir.exists() and not force:
        if list(project_dir.iterdir()):
            if not confirm(
                f"Directory {project_dir} is not empty. Continue?",
                default=False
            ):
                console.print("[yellow]Initialization cancelled[/yellow]")
                return

    # Interactive wizard
    config_values = {}
    if interactive:
        console.print("\n[bold]Configuration Wizard[/bold]\n")

        config_values["mailto"] = console.input(
            "Email address (for polite API crawling): "
        ).strip() or "your.email@example.com"

        config_values["year_min"] = console.input(
            "Minimum publication year [2019]: "
        ).strip() or "2019"

        console.print("\n[bold]Select providers to enable:[/bold]")
        config_values["enable_openalex"] = confirm("  OpenAlex?", default=True)
        config_values["enable_crossref"] = confirm("  Crossref?", default=True)
        config_values["enable_arxiv"] = confirm("  arXiv?", default=True)
        config_values["enable_s2"] = confirm("  Semantic Scholar?", default=False)

        project_name = console.input("\nProject name [My SLR Project]: ").strip()
        config_values["project_name"] = project_name or "My SLR Project"
    else:
        # Use defaults
        config_values = {
            "mailto": "your.email@example.com",
            "year_min": "2019",
            "enable_openalex": "true",
            "enable_crossref": "true",
            "enable_arxiv": "true",
            "enable_s2": "false",
            "project_name": project_dir.name if project_dir.name != "." else "My SLR Project",
        }

    # Create project directory
    try:
        project_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print_error(f"Failed to create directory: {e}")
        raise click.Abort()

    # Create files based on template
    files_created = []

    # Always create config.yml
    config_path = project_dir / "config.yml"
    if force or not config_path.exists():
        config_content = CONFIG_TEMPLATE.format(**config_values)
        config_path.write_text(config_content, encoding="utf-8")
        files_created.append("config.yml")

    # Always create queries.yml
    queries_path = project_dir / "queries.yml"
    if force or not queries_path.exists():
        queries_path.write_text(QUERIES_TEMPLATE, encoding="utf-8")
        files_created.append("queries.yml")

    # Create .env.example
    env_path = project_dir / ".env.example"
    if force or not env_path.exists():
        env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
        files_created.append(".env.example")

    # Create .gitignore
    gitignore_path = project_dir / ".gitignore"
    if force or not gitignore_path.exists():
        gitignore_path.write_text(GITIGNORE_TEMPLATE, encoding="utf-8")
        files_created.append(".gitignore")

    # Create README.md for standard/full templates
    if template in ("standard", "full"):
        readme_path = project_dir / "README.md"
        if force or not readme_path.exists():
            readme_content = README_TEMPLATE.format(**config_values)
            readme_path.write_text(readme_content, encoding="utf-8")
            files_created.append("README.md")

    # Create directory structure
    directories = ["outputs", "dedup", "exports"]
    if template == "full":
        directories.extend(["data", "docs", "notebooks"])

    for dir_name in directories:
        dir_path = project_dir / dir_name
        dir_path.mkdir(exist_ok=True)
        # Create .gitkeep to track empty directories
        (dir_path / ".gitkeep").touch()
        files_created.append(f"{dir_name}/")

    # Initialize git repository
    if not no_git:
        try:
            import subprocess
            result = subprocess.run(
                ["git", "init"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                files_created.append(".git/")
                console.print("[dim]  ✓ Initialized git repository[/dim]")
        except Exception:
            console.print("[yellow]  ⚠ Could not initialize git repository[/yellow]")

    # Print summary
    console.print()
    print_success("Project initialized successfully!")
    console.print()
    print_file_tree(str(project_dir), files_created)

    # Print next steps
    console.print("\n[bold]Next Steps:[/bold]\n")
    console.print("  1. Edit [cyan]config.yml[/cyan] with your email and preferences")
    console.print("  2. Edit [cyan]queries.yml[/cyan] with your search queries")
    console.print("  3. Run [green]slr search --queries queries.yml[/green]")
    console.print()

