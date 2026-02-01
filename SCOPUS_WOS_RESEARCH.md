# Scopus & Web of Science Integration Research

Integrating Scopus and Web of Science (WoS) is highly valuable for systematic literature reviews, as they are considered "gold standard" databases. However, unlike OpenAlex or PubMed, they have significant authentication and licensing barriers.

## 1. Scopus (Elsevier)
**Status:** Highly Recommended (but restricted)
**Access Requirements:** Institutional subscription + API Key + (IP validation or InstToken).

### Technical Details
*   **Base URL:** `https://api.elsevier.com/content/search/scopus`
*   **Authentication:** 
    *   Header: `X-ELS-APIKey: <API_KEY>`
    *   Header: `X-ELS-Insttoken: <INSTTOKEN>` (optional, depends on institutional setup)
    *   Scopus often validates the requesting IP against institutional ranges.
*   **Search Syntax:** 
    *   Field-based: `TITLE-ABS-KEY("machine learning")`
    *   Boolean: `AND`, `OR`, `AND NOT`
    *   Proximity: `W/n` (within n words), `PRE/n` (precedes by n words)
*   **Response Format:** JSON (standard) or XML.
*   **Python Library:** `pybliometrics` (Comprehensive and handles caching/throttling).

### Implementation Strategy
1.  **Direct API Implementation**: Use `requests` to call the Search API.
2.  **Normalization**: Map Elsevier's `prism:publicationName`, `dc:title`, `prism:doi`, etc., to the `Document` model.
3.  **Config**: User must provide `api_key` and potentially `insttoken`.

---

## 2. Web of Science (Clarivate)
**Status:** Recommended (but restricted)
**Access Requirements:** Institutional subscription + API Key.

### Technical Details
*   **APIs Available:**
    *   **Starter API:** Free/Lightweight, basic metadata, limited search.
    *   **Expanded API:** Full metadata, cited counts, rich search (requires paid license).
*   **Base URL (Starter):** `https://api.clarivate.com/api/wos-starter/v1`
*   **Authentication:** Header `X-API-Key: <API_KEY>`.
*   **Search Syntax:**
    *   Field Tags: `TI` (Title), `AU` (Author), `TS` (Topic), `PY` (Year).
    *   Boolean: `AND`, `OR`, `NOT`.
*   **Response Format:** JSON.
*   **Python Library:** Official `wosstarter` or third-party `wos` (SOAP-based, older).

### Implementation Strategy
1.  **Starter API Implementation**: Good for basic checks and linking.
2.  **Expanded API Implementation**: Needed for full SLR functionality (abstracts, etc.).
3.  **Normalization**: Map WoS JSON structure to the `Document` model.

---

## Challenges & Solutions

| Challenge | Impact | Proposed Solution |
| :--- | :--- | :--- |
| **Institutional IP Validation** | CLI might only work on University VPN/Network. | Support `insttoken` for Scopus; warn user if request fails due to IP mismatch. |
| **API Key Registration** | User needs to manually go to Elsevier/Clarivate portals. | Add documentation/guide in `nexus` on how to obtain these keys. |
| **Complex Syntaxes** | Scopus/WoS have unique proximity/field codes. | Implement specialized query translators for each (similar to `ArxivProvider`). |

## Recommendation
1.  **Scopus First**: Scopus is generally easier to integrate than WoS and has better documentation for developers via the Elsevier portal.
2.  **WoS Starter**: Implement WoS Starter API as a secondary source, as it is more accessible than the Expanded version.
