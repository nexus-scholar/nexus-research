# Deduplication Upgrade: Intelligent Data Fusion

**Status:** Planned  
**Module:** `nexus.dedup`  
**Goal:** Achieve production-grade data integrity by creating a "Golden Record" for each duplicate cluster, preventing data loss from non-representative records.

## 1. The Problem: Data Loss in Selection
Currently, the deduplication logic uses a "Winner-Takes-All" approach:
1.  A cluster of duplicates is identified (e.g., 3 records for the same paper).
2.  One "Representative" is chosen based on a score (Provider Priority + Metadata Completeness).
3.  **Issue:** If a "loser" record has a better Abstract, a PDF link, or a corrected Title, that information is effectively hidden because the system only exposes the Representative downstream.

## 2. The Solution: Field-Level Fusion
Instead of selecting a single existing document, we will synthesize a new `Document` object that aggregates the best available data from *all* cluster members.

### 2.1 Provider Reliability Hierarchy
We define a hierarchy of trust for metadata correctness. This acts as a tie-breaker when data conflicts.

1.  **Crossref / PubMed:** (Gold Standard for published metadata, DOIs, Dates)
2.  **OpenAlex:** (High coverage, generally reliable)
3.  **Semantic Scholar (S2):** (Good for citations/graphs, sometimes messy metadata)
4.  **ArXiv:** (Self-reported, good for preprints, abstracts often raw LaTeX)
5.  **Scraper/Direct:** (Lowest trust for metadata, but high trust for full-text availability)

### 2.2 Fusion Logic by Field

| Field | Strategy | Logic |
| :--- | :--- | :--- |
| **Title** | **Canonical (Provider Priority)** | Crossref/OpenAlex titles are usually identical. Prefer Crossref for punctuation accuracy. |
| **Abstract** | **Best Available (Length + Quality)** | **Critical.** In real data, Crossref often has empty or truncated abstracts, while OpenAlex/Arxiv provides full text. Selection: `max(abstracts, key=len)` but exclude strings like "No abstract". |
| **Authors** | **Deep Merge** | 1. Use the author list from the most trusted provider (Crossref) as the base structure.<br>2. **Fill ORCIDs:** If an author in the base list lacks an ORCID, search for the same author (by name) in other records and pull their ORCID. |
| **External IDs** | **Union** | Combine `doi`, `arxiv_id`, `openalex_id`, `s2_id`, `pubmed_id`. If OpenAlex has a DOI and a record from Crossref has the same DOI, the fused record must have both the DOI and the `openalex_id`. |
| **Cited By** | **Max** | Use `max(cited_by_count)` to get the most up-to-date impact metric. |
| **URL** | **Priority List** | 1. Official DOI link (Crossref) is primary.<br>2. Keep the OpenAlex/S2 landing pages as fallback in a `related_urls` list. |

## 3. Implementation Plan (Refined)

### Phase 1: Enhanced Scorer
Update `_pick_representative` to not just pick a winner, but to identify the "Primary Source" (usually Crossref for DOIs) which will serve as the template for the fusion.

### Phase 2: Field Fusion Implementation
Implement the logic discovered in the data trial:
- **ORCID Enrichment:** Noticed OpenAlex had some ORCIDs but Crossref had others for the same paper.
- **Abstract Recovery:** OpenAlex is significantly better at providing abstracts for IEEE/ACM papers where Crossref might only have metadata.


## 4. Risks & Mitigations
*   **Risk:** Merging bad data (e.g., an abstract that is just "Copyright 2023").
    *   *Mitigation:* Add basic validation/heuristics for "valid abstract" (length > 50 chars, doesn't contain "Copyright").
*   **Risk:** Author list mismatch (different order or number).
    *   *Mitigation:* Stick to the atomic "List of Authors" from the most trusted provider rather than trying to stitch lists together.

## 5. Definition of Done
*   [x] `_fuse_documents` implemented.
*   [x] `Document` model updated if necessary (e.g., to hold multiple URLs).
*   [x] Tests added for "Abstract Gap" and "Metric Maximization".
*   [x] Deduplication logic updated to use fusion.
