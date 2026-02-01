# Deduplication Performance Upgrade Plan

## Objective
Optimize the `nexus deduplicate` command to handle 30k+ records in reasonable time (minutes vs hours).

## 1. Algorithmic Optimizations
**Goal:** Reduce the number of fuzzy comparisons from $O(N^2)$ to something closer to $O(N)$.

*   [ ] **Pre-Blocking by Exact Title**: 
    *   Normalize all titles.
    *   Group documents by exact normalized title.
    *   Automatically union documents in these groups before entering fuzzy phase.
*   [ ] **Fast-Path Set Intersection**:
    *   Before running `rapidfuzz.fuzz.ratio`, perform a quick set intersection of words in the titles.
    *   Only run fuzzy logic if they share $>50\%$ of their unique words.
*   [ ] **Union-Find Path Compression & Ranking**:
    *   Ensure Union-Find is using path compression and union by rank for $O(\alpha(N))$ performance.

## 2. UX & Progress Reporting
**Goal:** Provide feedback during long-running operations.

*   [ ] **Per-Year Progress Bar**:
    *   Update the `Deduplicator` to report progress per year block.
    *   Use `rich` to show which year is currently being processed.

## 3. Execution Order
1.  Implement Union-Find improvements.
2.  Implement Exact-Title Pre-Blocking (The biggest speedup).
3.  Implement Set-Intersection pruning.
4.  Add detailed progress reporting.