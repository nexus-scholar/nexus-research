# Export Module Improvement Plan

## Objective
Upgrade the `nexus.export` module from "Prototype" to "Production Ready" status, ensuring reliability, data integrity, and broad compatibility with reference management software (Zotero, EndNote).

## 1. Quality Assurance (Testing)
**Goal:** Achieve >90% code coverage for the export module.

*   [ ] **Create Test Suite (`tests/test_export/`)**
    *   `test_base.py`: Verify `BaseExporter` interface and directory creation.
    *   `test_bibtex.py`: Verify citation key generation, LaTeX escaping, and entry type logic.
    *   `test_csv.py`: Verify flat-table generation, header consistency, and special character handling.
    *   `test_jsonl.py`: Verify JSON structure, serialization of date objects, and large file streaming.
    *   `test_integration.py`: end-to-end export test using dummy `Document` objects.

## 2. Robustness & Bug Fixes
**Goal:** Prevent silent data loss and invalid output generation.

*   [ ] **BibTeX: Fix Citation Key Collisions**
    *   Current behavior: `Smith2020Deep` overwrites previous entries with the same key.
    *   Fix: Implement a collision detection cache during export.
    *   Logic: If `Smith2020Deep` exists, try `Smith2020Deepa`, `Smith2020Deepb`, etc.
*   [ ] **BibTeX: Configurable Truncation**
    *   Current behavior: Hardcoded 500-char limit on abstracts.
    *   Fix: Add `max_abstract_length` parameter to `__init__` or `export_documents`. Default to `None` (unlimited).
*   [ ] **JSON: Memory Optimization**
    *   Current behavior: `JSONExporter` builds a full list in memory before dumping.
    *   Fix: Stream writing for standard JSON arrays (write `[`, then iterate and write objects separated by `,`, then `]`).

## 3. Feature Expansion (EndNote Support)
**Goal:** First-class support for EndNote users via RIS format.

*   [ ] **Implement `RISExporter` (`src/nexus/export/ris_exporter.py`)**
    *   Map `Document` fields to RIS tags (e.g., `TI` for Title, `AU` for Authors, `DO` for DOI).
    *   Handle list fields (Authors, Keywords) correctly (multiple lines).
    *   Register in `src/nexus/export/__init__.py`.

## 4. Execution Plan
1.  Run `slr deduplicate` to generate real test data (Done in parallel).
2.  Implement `RISExporter`.
3.  Apply fixes to `BibTeXExporter` and `JSONExporter`.
4.  Write and run tests.
