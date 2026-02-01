# Simple SLR CLI

A modern, beautiful command-line interface for conducting systematic literature reviews.

## Features

- 🔍 **Multi-Provider Search** - Query OpenAlex, Crossref, arXiv, Semantic Scholar
- 🔗 **Intelligent Deduplication** - Remove duplicates with exact and fuzzy matching
- 📤 **Multi-Format Export** - BibTeX, CSV, JSON, JSONL support
- ✅ **Validation** - Data quality checks and statistics
- 🎨 **Beautiful Output** - Progress bars, tables, color-coded messages
- ⚡ **Fast & Efficient** - Rate limiting, caching, parallel processing ready

## Quick Start

```bash
# Install
pip install simple-slr

# Initialize project
slr init my_review --interactive

# Search databases
cd my_review
slr search --queries queries.yml

# Deduplicate
slr deduplicate --input outputs/latest/

# Export
slr export --input dedup/latest/representatives.jsonl --format bibtex
```

## Commands

### `slr init` - Initialize Project

Create a new SLR project with templates and configuration.

```bash
slr init [DIR] [OPTIONS]

Options:
  --template minimal|standard|full  Project template
  --interactive, -i                 Interactive wizard
  --no-git                          Skip git initialization
  --force                           Overwrite existing files
```

### `slr search` - Search Databases

Search academic databases with multi-provider support.

```bash
slr search [OPTIONS]

Options:
  --queries PATH        YAML/JSON queries file
  --query TEXT          Single query string
  --provider TEXT       Specific provider(s) [repeatable]
  --year-min INT        Minimum publication year
  --max-results INT     Max results per query
  --output PATH         Output directory
  --dry-run            Preview without executing
```

### `slr deduplicate` - Remove Duplicates

Identify and cluster duplicate papers.

```bash
slr deduplicate [OPTIONS]

Options:
  --input PATH              Input directory/file [required]
  --strategy TEXT           conservative|semantic|hybrid
  --fuzzy-threshold INT     Fuzzy matching threshold (0-100)
  --max-year-gap INT        Max year difference
  --output PATH             Output directory
  --dry-run                Show stats only
```

### `slr export` - Export Results

Export to citation management formats.

```bash
slr export [OPTIONS]

Options:
  --input PATH          Input file [required]
  --format TEXT         bibtex|csv|json|jsonl [repeatable]
  --has-doi            Only export with DOI
  --min-year INT       Filter by year
  --output PATH        Output file

### `slr screen` - Screen Papers

Screen papers with an LLM based on title and abstract.

```bash
slr screen [OPTIONS]

Options:
  --input PATH             Input file (deduplicated JSONL)
  --output PATH            Output directory
  --criteria TEXT          Criteria for single-pass screener
  --model TEXT             LLM model to use
  --layered/--no-layered    Use layered screener with heuristic pre-filtering
  --include-group TEXT      Comma-separated keyword group (repeatable)
  --include-pattern TEXT    Keyword include pattern (repeatable)
  --exclude-pattern TEXT    Keyword exclude pattern (repeatable)
  --layer-model TEXT        Model per layer (repeatable)
```
```

### `slr validate` - Validate Data

Show statistics and quality checks.

```bash
slr validate PATH [OPTIONS]

Options:
  --stats-only         Skip validation, show stats only
  --show-errors       Show detailed errors
  --report PATH       Save report to file
```

## Global Options

Available for all commands:

```bash
--config PATH     Custom config file
--verbose, -v     Verbose logging (-vv, -vvv for more)
--quiet, -q       Suppress output
--version         Show version
--help            Show help
```

## Example Workflows

### Basic Workflow

```bash
# 1. Create project
slr init my_review

# 2. Edit queries
cd my_review
nano queries.yml

# 3. Search
slr search --queries queries.yml

# 4. Check results
slr validate outputs/latest/ --stats-only

# 5. Deduplicate
slr deduplicate --input outputs/latest/

# 6. Export
slr export --input dedup/latest/representatives.jsonl --format bibtex
```

### Quick Search

```bash
# Single query with specific provider
slr search --query "machine learning agriculture" \
           --provider openalex \
           --year-min 2020
```

### Advanced Deduplication

```bash
# Custom threshold with dry run
slr deduplicate --input outputs/latest/ \
                --fuzzy-threshold 95 \
                --max-year-gap 2 \
                --dry-run

# Then run for real
slr deduplicate --input outputs/latest/ \
                --fuzzy-threshold 95 \
                --max-year-gap 2
```

### Filtered Export

```bash
# Export only papers with DOI from 2020 onwards
slr export --input dedup/latest/representatives.jsonl \
           --format bibtex --format csv \
           --has-doi \
           --min-year 2020
```

## Configuration

### Config File (`config.yml`)

```yaml
mailto: your.email@example.com
year_min: 2019

providers:
  openalex:
    enabled: true
    rate_limit: 5.0
  crossref:
    enabled: true
    rate_limit: 1.0

deduplication:
  strategy: conservative
  fuzzy_threshold: 97
  max_year_gap: 1

screener:
  include_groups:
    - ["plant", "leaf", "crop", "disease"]
    - ["deep learning", "cnn", "vit", "segmentation"]
  exclude_patterns: ["remote sensing", "aerial"]
```

### Queries File (`queries.yml`)

```yaml
Machine Learning:
  - "machine learning AND agriculture"
  - "deep learning AND crops"

Computer Vision:
  - "computer vision AND plant disease"
  - "image recognition AND agriculture"
```

## Output Structure

### Search Output

```
outputs/
└── run_2025-11-15_143022/
    ├── metadata.json
    ├── summary.txt
    ├── openalex/
    │   ├── Q01_results.jsonl
    │   ├── Q02_results.jsonl
    │   └── all_results.jsonl
    └── crossref/
        └── ...
```

### Deduplication Output

```
dedup/
└── dedup_2025-11-15_144532/
    ├── metadata.json
    ├── summary.txt
    ├── clusters.jsonl
    ├── representatives.jsonl
    ├── representatives.csv
    ├── cluster_mapping.json
    └── prisma_counts.json
```

## Programmatic Usage

Use the CLI from Python code:

```python
from click.testing import CliRunner
from src.slr import cli

runner = CliRunner()

# Initialize project
result = runner.invoke(cli, ['init', 'my_review', '--no-git'])
assert result.exit_code == 0

# Run search (dry run)
result = runner.invoke(cli, [
    'search',
    '--queries', 'my_review/queries.yml',
    '--dry-run'
])
print(result.output)
```

## Tips & Tricks

### Use Latest Shortcuts

The CLI recognizes `latest` in paths:

```bash
slr deduplicate --input outputs/latest/
slr validate dedup/latest/
```

### Chain Commands

```bash
# Search and immediately deduplicate
slr search --queries queries.yml && \
slr deduplicate --input outputs/latest/
```

### Verbose Logging

Get detailed logs for debugging:

```bash
slr search --queries queries.yml -vvv
```

### Dry Run Everything

Preview before executing:

```bash
slr search --queries queries.yml --dry-run
slr deduplicate --input outputs/latest/ --dry-run
```

## Troubleshooting

### No providers enabled

**Problem:** `Error: No providers enabled`

**Solution:** Check `config.yml` providers section or use `--provider` flag:
```bash
slr search --queries queries.yml --provider openalex
```

### Rate limit exceeded

**Problem:** `RateLimitError: Rate limit exceeded`

**Solution:** Adjust rate limits in `config.yml` or wait between requests

### Semantic strategy not available

**Problem:** `semantic strategy requires additional dependencies`

**Solution:** Install semantic extras:
```bash
pip install simple-slr[semantic]
```

## Contributing

The CLI is modular and extensible:

```
slr/cli/
├── main.py          # Add new commands here
├── your_command.py  # Create new command file
└── utils.py         # Add shared utilities
```

To add a new command:

1. Create `slr/cli/your_command.py`
2. Define command with `@click.command()`
3. Register in `main.py`'s `main()` function

## Documentation

- **Quick Reference**: [docs/CLI_QUICK_REFERENCE.md](./CLI_QUICK_REFERENCE.md)
- **Implementation**: [CLI_IMPLEMENTATION.md](../CLI_IMPLEMENTATION.md)
- **Examples**: [examples/cli_usage_example.py](../examples/cli_usage_example.py)
- **Tests**: [tests/test_cli.py](../tests/test_cli.py)

## Support

- **Issues**: https://github.com/yourusername/simple_slr/issues
- **Docs**: https://simple-slr.readthedocs.io
- **Email**: your.email@example.com

## License

MIT License - See LICENSE file for details

---

**Made with ❤️ using Click and Rich**
