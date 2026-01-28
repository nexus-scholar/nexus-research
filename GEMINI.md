# Simple SLR (lit-backend)

## Project Overview
**Simple SLR** is a modern, extensible CLI framework for conducting systematic literature reviews (SLR). It automates the search, deduplication, and export of academic papers from multiple providers.

*   **Type:** Python CLI Application
*   **Package Name:** `slr`
*   **Entry Point:** `src/slr/cli/main.py`
*   **Key Dependencies:** `click` (CLI), `rich` (UI), `pydantic` (Data Validation), `PyYAML` (Config).

## Architecture

The codebase is organized into modular components within `src/slr/`:

| Module | Description |
| :--- | :--- |
| **`cli/`** | Command-line interface logic using `click`. Handles user interaction, logging, and command dispatch. |
| **`core/`** | Core business logic, configuration management (`config.py`), and data models (`models.py`). |
| **`providers/`** | Interface with external APIs (OpenAlex, Crossref, Arxiv, Semantic Scholar). Contains query translation and normalization logic. |
| **`dedup/`** | Logic for identifying and merging duplicate records using exact, fuzzy, or semantic strategies. |
| **`export/`** | Handles data export to various formats (BibTeX, CSV, JSONL). |
| **`normalization/`** | Data cleaning and normalization utilities. |
| **`utils/`** | Shared utilities for logging, rate limiting, and retries. |

## Data & Output Structure

The following directories are created in the project root during the SLR workflow:

| Directory | Description |
| :--- | :--- |
| **`results/outputs/`** | Raw search results from providers. Organized by run ID. |
| **`results/dedup/`** | Deduplicated result clusters and unique representatives. |
| **`results/exports/`** | Final exported citation files (BibTeX, CSV). |
| **`data/`** | General storage for input files or local datasets. |

## Key Commands

The CLI is invoked via the `slr` command (after installation).

*   **Initialize:** `slr init [DIR]` - Sets up a new review project.
*   **Search:** `slr search --queries queries.yml` - Fetches papers from configured providers.
*   **Deduplicate:** `slr deduplicate --input outputs/latest/` - Identifies duplicates.
*   **Export:** `slr export --input dedup/latest/representatives.jsonl --format bibtex` - Generates final output files.
*   **Validate:** `slr validate [PATH]` - Checks data integrity.

## Configuration

Configuration is managed via `config.yml` (Pydantic-validated).

*   **File Location:** Default is `config.yml` in the project root or passed via `--config`.
*   **Environment Variables:** Supports expansion like `${API_KEY}` or `${VAR:-default}`.
*   **Key Sections:**
    *   `providers`: Toggle providers, set rate limits.
    *   `deduplication`: Configure strategies (conservative, semantic) and thresholds.
    *   `output`: directory paths and formats.

## Development & Setup

### Prerequisities
*   Python >= 3.13

### Installation
```bash
# Install in editable mode
pip install -e .
```

### Note on Dependencies
The `pyproject.toml` currently lists `dependencies = []`. You may need to manually install core libraries if they are not yet added:
```bash
pip install click rich pydantic pyyaml
```

### Conventions
*   **Type Hinting:** Extensive use of Python type hints.
*   **Validation:** Use `pydantic` models for all structured data and configuration.
*   **CLI UX:** Use `rich` for all terminal output (progress bars, tables, formatted text).
*   **Error Handling:** Custom exceptions in `utils/exceptions.py`.
