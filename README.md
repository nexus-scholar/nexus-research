# Nexus: AI Research Assistant

**Nexus** is a modular, extensible CLI framework for conducting systematic literature reviews (SLR) and managing academic research workflows. It goes beyond simple fetching by integrating LLM screening and full-text PDF processing.

## 🚀 Features

*   **🔍 Search:** Query multiple databases (OpenAlex, Semantic Scholar, ArXiv, Crossref) with a unified DSL.
*   **🔗 Deduplicate:** Intelligent merging of records using DOI, ArXiv ID, and fuzzy title matching.
*   **🤖 Screen:** Automate title/abstract screening using LLMs (OpenAI/Gemini).
*   **📥 Fetch:** Retrieve full-text PDFs from Open Access sources (Unpaywall, ArXiv) and direct links.
*   **📄 Extract:** Convert PDFs to structured Markdown (tables, math, citations) for RAG/Analysis.
*   **✅ Validate:** Automatic PRISMA counts and data quality checks.

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/nexus-scholar/nexus-research.git
cd nexus-research

# Install in editable mode (requires uv or pip)
uv pip install -e .
# OR
pip install -e .
```

## 🛠️ Usage Workflow

### 1. Initialize & Search
Define your queries in `queries.yml` and configure providers in `nexus.yml`.

```bash
# Run a multi-provider search
nexus search --queries queries.yml
```

### 2. Deduplicate
Merge overlapping results from different providers.

```bash
nexus deduplicate --input results/outputs/latest
```

### 3. Screen (AI-Assisted)
Filter papers based on relevance using an LLM.

```bash
export OPENAI_API_KEY="sk-..."
nexus screen --criteria "Include papers focusing on lightweight CNNs for crop disease."
```

### 4. Fetch PDFs
Download full-text for the screened papers.

```bash
nexus fetch --limit 10
```

### 5. Extract Content
Convert PDFs to Markdown for analysis.

```bash
nexus extract --tables --images
```

## 📂 Project Structure

```text
src/nexus/
├── cli/            # Command-line interface
├── core/           # Configuration & Data Models
├── ingest/         # Metadata Fetchers (OpenAlex, S2, etc.)
├── screener/       # LLM Screening Logic
├── retrieval/      # PDF Fetching (Unpaywall, ArXiv)
└── extraction/     # PDF Processing Pipeline (formerly pdf-struct-rag)
```

## 📄 Configuration

**`nexus.yml`**:
```yaml
mailto: "researcher@example.com"
year_min: 2024
providers:
  openalex: { enabled: true }
  s2: { enabled: true }
output:
  directory: "results/outputs"
```

**`queries.yml`**:
```yaml
queries:
  - id: Q01
    theme: domain_shift
    query: ("domain shift" OR "dataset shift") AND "plant disease"
```

## 🤝 Contributing

Contributions are welcome! This project uses a modular "monorepo" style architecture.
