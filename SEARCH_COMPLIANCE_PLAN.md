# Search Compliance & Enhancement Plan

## Status Assessment
*   **Production Grade:** Mostly Yes. Parallel search and robust error handling are in place.
    *   *Gap:* Missing `resume` functionality makes long-running searches fragile.
*   **Scientifically Correct:** Yes. Query translation is accurate.
    *   *Gap:* Metadata does not store the *exact* translated query sent to each provider, which is crucial for reproducibility.
*   **PRISMA Compliant:** Yes. Generates counts and flow data.

## 1. Resilience: Implement `resume` Functionality
**Goal:** Allow interrupted searches to continue without re-fetching existing results.

*   [ ] **Update `_search_provider_worker` in `src/nexus/cli/search.py`**:
    *   Check if output file (e.g., `openalex/Q01_results.jsonl`) exists.
    *   If exists and `--resume` flag is active:
        *   Count lines in existing file.
        *   Skip processing if query is fully complete (check metadata or assume complete if file exists? Better: check separate state file).
        *   *Simpler approach:* Read existing IDs into a set `seen_ids` and skip fetching/saving them.

## 2. Reproducibility: Enrich Metadata
**Goal:** Store the exact query string sent to each provider (e.g., the `all:(...)` string for arXiv).

*   [ ] **Update `Provider` Interface**:
    *   Add `get_translated_query(query: Query) -> str` method.
*   [ ] **Update `search` command**:
    *   Collect these translated strings during execution.
    *   Store them in `metadata.json` under `query_details` section:
        ```json
        "query_details": {
          "Q01": {
            "openalex": "search=(machine learning)...",
            "arxiv": "all:(machine learning)..."
          }
        }
        ```

## 3. Provider Expansion Recommendations
Based on analysis of free, high-value academic APIs:

*   **PubMed (E-Utilities)**:
    *   *Value:* Essential for medical/biological domain queries (like "plant disease").
    *   *API:* Free, robust XML/JSON API.
*   **CORE**:
    *   *Value:* Huge aggregator of open access papers.
    *   *API:* Free REST API.
*   **DOAJ (Directory of Open Access Journals)**:
    *   *Value:* High-quality open access journals.
    *   *API:* Free JSON API.

**Recommendation:** Prioritize **PubMed** implementation next, as it aligns closely with the "plant disease" test cases found in `queries.yml`.
