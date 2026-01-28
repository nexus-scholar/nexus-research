# Simple SLR Domain Specific Language (DSL) Reference

This document describes the file formats and options used to configure **Simple SLR** and define research queries.

## 1. Configuration (`config.yml`)

The configuration file controls the global behavior of the application, including provider settings, API limits, and deduplication strategies.

### Global Settings

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `mailto` | `string` | `None` | **Highly Recommended.** Email address used for "polite" API requests. Grants significantly higher rate limits for providers like OpenAlex and Crossref. |
| `year_min` | `int` | `None` | Default minimum publication year filter for all queries. |
| `year_max` | `int` | `None` | Default maximum publication year filter. |
| `language` | `string` | `"en"` | ISO 639-1 language code filter (e.g., "en", "es"). |

### Provider Configuration

The `providers` section configures specific academic databases.

**Structure:**
```yaml
providers:
  <provider_name>:
    enabled: <bool>
    rate_limit: <float>
    timeout: <int>
    api_key: <string>  # Optional
```

**Supported Providers:**

*   **`openalex`**: OpenAlex API.
    *   *Default Rate Limit:* 5.0 req/s (with `mailto`).
*   **`crossref`**: Crossref API.
    *   *Default Rate Limit:* 1.0 req/s (conservative).
*   **`arxiv`**: arXiv API.
    *   *Default Rate Limit:* 0.5 req/s (recommended 3s interval).
*   **`s2`** (or `semantic_scholar`): Semantic Scholar API.
    *   *Default Rate Limit:* 1.0 req/s (100.0 req/s with `api_key`).

### Deduplication Settings

The `deduplication` section controls how duplicate records are identified and merged.

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `strategy` | `enum` | `"conservative"` | Algorithm to use:<br>• `conservative`: Exact IDs (DOI, arXiv) + strict title matching.<br>• `semantic`: Embedding-based similarity (Coming Soon).<br>• `hybrid`: Combination of both (Coming Soon). |
| `fuzzy_threshold` | `int` | `97` | Similarity score (0-100) required for title matching in conservative mode. |
| `max_year_gap` | `int` | `1` | Maximum allowed difference in publication years for two records to be considered duplicates. |

### Output Configuration

The `output` section controls where and how results are saved.

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `directory` | `path` | `"results/outputs"` | Base directory for search results. |
| `format` | `enum` | `"csv"` | Output format(s): `"csv"`, `"jsonl"`, `"json"`, or `"both"`. |
| `include_raw` | `bool` | `false` | If `true`, includes the full raw API response in the saved data (increases file size). |

---

## 2. Query Definition (`queries.yml`)

Simple SLR supports a structured V1 format for defining research queries.

### Document Structure

```yaml
version: 1
project: <string>
defaults:               # Optional default overrides
  date_window:
    from: "YYYY-MM-DD"
    to: "YYYY-MM-DD"
  language: "en"
  
queries:
  - <Query Item>
  - <Query Item>
```

### Query Item

Each item in the `queries` list represents a specific research question.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `id` | `string` | **Yes** | Unique identifier for the query (e.g., `DS01`, `Q1`). Used in filenames and logs. |
| `query` | `string` | **Yes** | The search string. Supports standard Boolean operators (`AND`, `OR`). |
| `theme` | `string` | No | Category or theme for grouping results (e.g., "domain_shift"). |
| `priority` | `string` | No | Priority level (e.g., "high", "low"). Stored in metadata. |
| `include_any` | `list` | No | List of keywords/concepts that *should* be present. (Informational/Metadata). |
| `exclude_any` | `list` | No | List of keywords/concepts to exclude. (Informational/Metadata). |

**Example:**

```yaml
queries:
  - id: DS01
    theme: domain_shift
    priority: high
    query: >
      ("domain shift" OR "dataset shift")
      AND ("plant disease" OR "leaf disease")
```

### Legacy Format (Simple)

The tool also supports a simplified dictionary format for quick searches:

```yaml
Topic Name:
  - "query string 1"
  - "query string 2"
```

In this format:
*   `Topic Name` becomes the `category`.
*   IDs are auto-generated (`Q01`, `Q02`, ...).
