# SLR Execution Pipeline & Paging Strategy

## 1. Search Identification Phase
The search module executes queries in parallel across 8 academic providers. Each provider has a specialized paging strategy to ensure data completeness while respecting API limits.

### Provider Paging Specifications
*   **OpenAlex**: Deep paging via `cursor`. Batch size: 200. Max results: Unlimited.
*   **Crossref**: Deep paging via `cursor`. Batch size: 100. Max results: Unlimited (Fixed).
*   **arXiv**: Offset-based (`start`). Cap: 10,000 records (API limit).
*   **PubMed**: History-based (`WebEnv`). Batch size: 200. Max results: Unlimited.
*   **CORE**: Offset-based (`offset`). Batch size: 100. Max results: Unlimited (Fixing).
*   **DOAJ**: Page-based. Batch size: 100. Max results: Unlimited.
*   **IEEE Xplore**: Offset-based (`start_record`). Batch size: 100. Max results: Unlimited (Fixing).
*   **Semantic Scholar**: Token-based (Bulk API). Max results: Unlimited.

## 2. Deduplication Phase
*   **Phase 1 (Exact)**: Matches on DOI and Arxiv ID.
*   **Phase 2 (Fuzzy)**: Fuzzy title matching (default 97%) within 1-year publication windows.
*   **Phase 3 (Semantic)**: Embedding-based similarity check (Specter model).

## 3. Screening & Retrieval Phase
*   **AI Screener**: Parallel abstract screening against inclusion criteria.
*   **PDF Fetcher**: Multi-source retrieval (Direct, Unpaywall, CORE).

## 4. Synthesis Phase
*   **Analysis Engine**: Structured metadata extraction from full-text.
*   **Synthesizer**: Automated PRISMA counts and Literature Review draft generation.