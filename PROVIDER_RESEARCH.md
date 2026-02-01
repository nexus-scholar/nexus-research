# Provider Research Report

## 1. PubMed (NCBI E-Utilities)
**Status:** Highly Recommended
**Domain:** Medicine, Biology, Life Sciences

### Technical Details
*   **Base URL:** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`
*   **Endpoints:**
    *   `esearch.fcgi`: Search for IDs (`term=...`).
    *   `efetch.fcgi`: Retrieve full records by ID (`id=...`).
*   **Authentication:**
    *   Optional but recommended.
    *   **Rate Limits:**
        *   No Key: 3 requests/second.
        *   With Key: 10 requests/second.
*   **Search Syntax:**
    *   Boolean: `AND`, `OR`, `NOT` (uppercase).
    *   Fields: `term[field]`, e.g., `cancer[Title]`, `2023[Date - Publication]`.
    *   Logic: `(A OR B) AND C`.
*   **Response Formats:** XML (default), JSON (`retmode=json`).
*   **Python Libraries:**
    *   `eutils`: High-level wrapper (recommended).
    *   `biopython` (`Bio.Entrez`): Traditional standard.

### Implementation Strategy
1.  **Search Phase:** Use `esearch` with `retmax` to get list of PMIDs.
2.  **Fetch Phase:** Use `efetch` with list of PMIDs to get metadata (XML).
3.  **Normalization:** Parse XML to extract Title, Abstract, Authors, DOI, Year.

---

## 2. DOAJ (Directory of Open Access Journals)
**Status:** Recommended for Open Access coverage
**Domain:** Multidisciplinary Open Access

### Technical Details
*   **Base URL:** `https://doaj.org/api/v1`
*   **Endpoints:**
    *   `/search/articles/{query}`: Search articles.
*   **Authentication:** None required for read-only search.
*   **Rate Limits:**
    *   Implicit limits (fair use).
    *   Page size limit: 1000 records/request.
*   **Search Syntax:**
    *   Elasticsearch Simple Query String syntax.
    *   Fields: `title:`, `bibjson.author.name:`, `bibjson.year:`.
    *   Range: `bibjson.year:[2020 TO 2025]`.
*   **Response Formats:** JSON.

### Implementation Strategy
1.  **Search:** Direct calls to `/search/articles/` with `pageSize=100`.
2.  **Pagination:** Use `page` parameter.
3.  **Normalization:** Map JSON fields (`bibjson` object) to `Document` model.

---

## 3. CORE
**Status:** Implemented (API v3)
**Domain:** Multidisciplinary (Open Access Repositories)

### Technical Details
*   **API Version:** v3
*   **Base URL:** `https://api.core.ac.uk/v3`
*   **Endpoints:**
    *   `/search/works`: Unified search for research works.
*   **Authentication:** `Authorization: Bearer <API_KEY>`
*   **Rate Limits:** 10 requests / 10 seconds.
*   **Search Syntax:** Lucene-like. Supports `yearPublished:[2020 TO 2025]`.
*   **Response Formats:** JSON.

### Implementation Strategy
1.  **Direct Integration**: `CoreProvider` uses the `/search/works` endpoint.
2.  **Rich Metadata**: Extracts `downloadUrl` for direct PDF access.
3.  **Normalization**: Maps CORE `Work` objects to `Document` model.

## Recommendation for Next Steps
1.  **Implement PubMed Provider:** It has the most distinct coverage (biomedical) from existing providers and fits the "plant disease" queries well.
2.  **Implement DOAJ Provider:** Good fallback for open access.
