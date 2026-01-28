# Simple SLR - Future Development Roadmap

This document outlines the planned modules to expand **Simple SLR** from a metadata fetcher into a full-text research pipeline.

## Architectural Change: Modular Monorepo
We are moving to a modular structure where specialized components exist as sibling packages in `src/` to ensure separation of concerns.

```text
src/
├── slr/                 # Metadata fetching, project management, CLI entry point
├── screener/            # LLM-based title/abstract screening
├── retrieval/           # Full-text PDF fetching
└── extraction/          # PDF-to-Markdown conversion (External: pdf-struct-rag)
```

---

## 1. Screener Module (`src/screener`)
**Goal:** Automated initial screening of titles and abstracts using Large Language Models.

*   **Input:** `representatives.jsonl` (from `slr`).
*   **Logic:** 
    *   Classify papers into `Include`, `Exclude`, or `Maybe` based on research criteria.
    *   Provide a brief reasoning for the decision.
*   **Implementation:** Use structured JSON outputs from models (Gemini/OpenAI) via Pydantic.
*   **Output:** `results/screening/screening_results.jsonl`

## 2. Retrieval Module (`src/retrieval`)
**Goal:** Automate the retrieval of full-text PDF files for included/maybe papers.

*   **Logic:**
    *   Resolve DOIs to PDF URLs.
    *   Prioritize Open Access (OA) sources using APIs like **Unpaywall**.
    *   Direct downloads from arXiv for preprint records.
*   **Storage:** Save PDFs in `results/storage/pdfs/` indexed by DOI or ID.

## 3. Extraction Module (`src/extraction`)
**Goal:** Convert PDF documents into structured text (Markdown) for downstream analysis.

*   **Status:** **Cloned** from `nexus-scholar/pdf-struct-rag`.
*   **Action Items:**
    *   Review `src/extraction/README.md` and `pyproject.toml` (if present) to understand dependencies.
    *   Create an integration layer (adapter) so `slr` can invoke it.

---

## Strategic Pipeline Flow

1.  **Fetcher (`slr`):** Get metadata.
2.  **Deduplicator (`slr`):** Merge records.
3.  **LLM Screener (`screener`):** Filter candidates.
4.  **PDF Fetcher (`retrieval`):** Download only relevant full-text.
5.  **PDF Extractor (`extraction`):** Convert to machine-readable format.
6.  **Synthesis:** Full-text analysis/Review writing.

---
**Updated on:** Wednesday, January 28, 2026