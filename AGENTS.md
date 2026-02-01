# Repository Guidelines

## Project Structure & Module Organization
- `src/nexus/` hosts the application modules (cli, core, providers, retrieval, extraction, dedup, normalization, analysis, export).
- `tests/` contains pytest suites (e.g., `tests/test_search/` and `tests/test_export.py`).
- `docs/` stores design and research notes; `data/` and `results/` hold datasets and pipeline outputs.
- Root configs include `pyproject.toml`, `nexus.yml` (runtime config), and `queries.yml` (search inputs).

## Build, Test, and Development Commands
- `uv pip install -e .` or `pip install -e .`: install in editable mode for local development.
- `nexus --help`: verify CLI wiring and available subcommands.
- `nexus search --queries queries.yml`: run the search pipeline with configured providers.
- `pytest`: run the full test suite.

## Coding Style & Naming Conventions
- Python 3.13+; follow Black-style formatting for consistency.
- Use `snake_case` for functions/variables and `PascalCase` for classes.
- Keep modules focused (e.g., provider-specific logic in `src/nexus/providers/`).

## Testing Guidelines
- Framework: pytest (declared in dev dependencies).
- Naming: files are `test_*.py`, functions are `test_*`.
- Add tests for new CLI flags, provider logic, and data transforms; no explicit coverage threshold is configured.

## Commit & Pull Request Guidelines
- Commit messages follow a Conventional Commit style like `feat(search): ...` or `fix(cli): ...` (see recent history). Prefer that format over free-form messages.
- PRs should include a concise summary, linked issues when available, and test results (e.g., `pytest`).
- If a change affects outputs or docs, update relevant files under `docs/` or `results/` as needed.

## Security & Configuration Tips
- Keep API keys in `.env`; use `.env.example` as the template and avoid committing secrets.
- Provider limits and behavior can change; validate config in `nexus.yml` when adding new sources.
