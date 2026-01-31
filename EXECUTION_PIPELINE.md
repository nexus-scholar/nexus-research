# Nexus Scoping Review: Execution Pipeline

## 1. Define Scope
**Goal:** Articulate your research questions and keywords.
*   **Action:** Create or edit your query configuration file.
*   **File:** `queries.yml`
*   **Example:**
    ```yaml
    queries:
      - id: Q01
        theme: "lightweight_architectures"
        query: "('MobileNet' OR 'ShuffleNet') AND ('plant disease' OR 'crop')"
    ```

## 2. Identify Sources
**Goal:** Select academic databases.
*   **Action:** Enable relevant providers in the configuration.
*   **File:** `nexus.yml`
*   **Supported:** OpenAlex, Semantic Scholar (S2), ArXiv, Crossref.
*   **Config:**
    ```yaml
    providers:
      openalex: { enabled: true }
      s2: { enabled: true }
    ```

## 3. Develop Search Strategy
**Goal:** Refine search strings and filters.
*   **Action:** Use the `dry-run` feature to test your boolean logic without making API calls.
*   **Command:**
    ```bash
    nexus search --queries queries.yml --dry-run
    ```

## 4. Execute Searches & Deduplicate
**Goal:** Retrieve metadata and remove duplicates across databases.
*   **Step A: Search**
    ```bash
    nexus search --queries queries.yml
    ```
    *Result:* Raw JSONL files in `results/outputs/`.
*   **Step B: Deduplicate**
    ```bash
    nexus deduplicate --input results/outputs/latest
    ```
    *Result:* `representatives.jsonl` in `results/dedup/`.

## 5. Screen Titles/Abstracts (AI-Assisted)
**Goal:** Filter irrelevant papers based on inclusion/exclusion criteria.
*   **Action:** Use the LLM Screener.
*   **Config:** Set `OPENAI_API_KEY` (or OpenRouter key) in `.env`.
*   **Command:**
    ```bash
    nexus screen --criteria "Include papers focusing on deep learning for plant disease detection. Exclude reviews and non-visual sensors."
    ```
    *Result:* `results/screening/screening_....jsonl` (with `decision: include/exclude`).

## 6. Screen Full Texts (Fetch & Validate)
**Goal:** Obtain full-text PDFs for included papers.
*   **Step A: Fetch PDFs** (Automatic + SNDL Proxy)
    ```bash
    nexus login  # (Once) To capture SNDL cookies
    nexus fetch --include-only --input results/screening/latest
    ```
*   **Step B: Manual Recovery** (Optional)
    *   If failures exist, generate a report: `python generate_failed_report.py`
    *   Manually download PDFs to `failed_pdfs/`
    *   Import them: `python import_manual_pdfs.py`

## 7. Extract Data
**Goal:** Convert PDFs into structured, machine-readable text (Markdown).
*   **Command:**
    ```bash
    nexus extract --tables --input results/pdfs --output results/extraction
    ```
    *Result:* Clean Markdown (`paper_body.md`) and JSON chunks for every paper.

## 8. Synthesize Findings
**Goal:** Analyze trends, architectures, and datasets across the entire corpus.
*   **Step A: Batch Analysis** (Extract Models, Accuracy, etc.)
    ```bash
    nexus analyze
    ```
    *Result:* `analysis_workspace/literature_matrix.csv`
*   **Step B: Visualization**
    ```bash
    nexus visualize
    ```
    *Result:* Charts in `analysis_workspace/plots/`.

## 9. Report Results
**Goal:** Generate the final literature review draft.
*   **Command:**
    ```bash
    nexus synthesize
    ```
    *Result:* `analysis_workspace/DRAFT_REVIEW.md` (A complete, cited draft).
