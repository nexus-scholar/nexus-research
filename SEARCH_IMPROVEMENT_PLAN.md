# Search & Provider Improvement Plan

## Objective
Upgrade the `search`, `providers`, and `normalization` modules to "Production Ready" status, focusing on performance (parallelism), architectural cleanliness, and robust query handling.

## 1. Architectural Refactoring
**Goal:** Clean separation of concerns.

*   [ ] **Move Normalizer:** Move `src/nexus/providers/normalizer.py` to `src/nexus/normalization/standardizer.py`.
*   [ ] **Update Imports:** Fix all references to the old `normalizer` path.

## 2. Performance: Parallel Search
**Goal:** Reduce total search time by querying providers concurrently.

*   [ ] **Update `src/nexus/cli/search.py`**:
    *   Use `concurrent.futures.ThreadPoolExecutor`.
    *   Execute provider searches in parallel threads.
    *   Aggregate results thread-safely.
    *   Maintain distinct progress bars (using `rich`'s multiple progress bars support).

## 3. Provider Enhancements
**Goal:** Ensure all providers are robust and handle complex queries.

*   [ ] **Crossref Provider (`src/nexus/providers/crossref.py`)**:
    *   Review pagination logic (cursor vs offset).
    *   Verify complex query translation.
*   [ ] **Arxiv Provider (`src/nexus/providers/arxiv.py`)**:
    *   Verify XML parsing (Arxiv returns Atom XML).
    *   Check for "max results" limits (Arxiv API has strict limits).
*   [ ] **Query Translation**:
    *   Ensure boolean logic (`AND`, `OR`) is respected or warned if unsupported.

## 4. Quality Assurance
**Goal:** >90% test coverage.

*   [ ] **Create Test Suite (`tests/test_search/`)**:
    *   `test_providers.py`: Mock API responses for OpenAlex, Crossref, Arxiv.
    *   `test_normalization.py`: Test date parsing, author parsing, ID extraction.
    *   `test_parallel_search.py`: Verify parallel execution logic.

## Execution Order
1.  Refactor Normalization (Move files).
2.  Scan and fix Crossref/Arxiv providers.
3.  Implement Parallel Search.
4.  Write Tests.
