# Nexus Research - Development Roadmap

This document tracks the evolution of **Nexus** from a simple fetcher to a full-stack AI research assistant.

## ✅ Completed Modules

### 1. Core & Metadata (`nexus.slr`)
- [x] Multi-provider search (OpenAlex, Semantic Scholar, ArXiv, Crossref).
- [x] Intelligent deduplication (DOI, ArXiv ID, Fuzzy Title).
- [x] Unified `Document` model and configuration.

### 2. Screener (`nexus.screener`)
- [x] LLM-based title/abstract screening.
- [x] Resumable workflows.
- [x] Customizable criteria via `nexus screen --criteria`.

### 3. Retrieval (`nexus.retrieval`)
- [x] Hybrid fetching strategy.
- [x] Open Access (Unpaywall, OpenAlex).
- [x] Direct Download (ArXiv).
- [x] **Browser Automation:** Headful/Headless Playwright integration for institutional proxies (SNDL).
- [x] Authentication state management (`auth.json`).

### 4. Extraction (`nexus.extraction`)
- [x] Integrated `pdf-struct-rag` pipeline.
- [x] PDF to Markdown conversion.
- [x] Table and citation extraction.
- [x] **Parallel Processing:** Multi-core batch extraction.

---

## 🚧 Upcoming: Analysis Phase

### 5. Archivist (Indexing)
**Goal:** Make the extracted content searchable.
- [ ] **Vector Store:** Index semantic chunks into ChromaDB.
- [ ] **Metadata Filtering:** Filter chunks by Year, Author, or Theme.

### 6. Oracle (Chat & Synthesis)
**Goal:** Interact with the literature.
- [ ] **`nexus chat`:** RAG-based Q&A over the entire document set.
- [ ] **`nexus synthesize`:** Generate literature review sections (Introduction, Methodology comparison) automatically.

### 7. User Interface (Optional)
- [ ] Simple Streamlit or Chainlit UI for non-CLI users.

---

## Technical Debt / Refactoring
- [ ] Centralize logging configuration.
- [ ] Add unit tests for the new `retrieval` and `extraction` modules.
- [ ] Create a Docker container for reproducible environments.

---
**Updated:** January 29, 2026
