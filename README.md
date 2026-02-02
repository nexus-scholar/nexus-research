# Nexus: AI Research Assistant

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange.svg)]()
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Nexus** is a modular, AI-powered command-line framework for conducting **Systematic Literature Reviews (SLR)**. It automates the tedious parts of research—searching, deduplicating, screening, and extracting data—allowing researchers to focus on synthesis and insight.

Unlike simple scrapers, Nexus is a complete pipeline that integrates **LLM-based screening** and **full-text PDF extraction** into a cohesive workflow.

---

## 🚀 Key Features

*   **🔍 Multi-Source Search:** Unified query DSL for **OpenAlex**, **Semantic Scholar**, **ArXiv**, and **Crossref**.
*   **🔗 Intelligent Deduplication:** Merges records using DOIs, ArXiv IDs, and fuzzy title matching with high precision.
*   **🤖 AI Screening:** Uses LLMs (OpenAI, Gemini) to screen papers based on inclusion/exclusion criteria.
*   **📥 PDF Retrieval:** Automatically fetches full-text PDFs from Open Access sources (Unpaywall, ArXiv) and direct metadata links.
*   **📄 Structural Extraction:** Converts PDFs into clean, semantic Markdown (preserving tables, math, and citations) for RAG pipelines.
*   **📊 Validation & Reporting:** Automatic PRISMA flow diagrams and data quality checks.

---

## 📦 Installation

### Prerequisites
*   Python 3.13+
*   (Optional) OpenAI API Key for screening features.

### From Source (Recommended)

```bash
# Clone the repository
git clone https://github.com/nexus-scholar/nexus-research.git
cd nexus-research

# Install with uv (faster)
uv pip install -e .

# OR with standard pip
pip install -e .
```

---

## 🛠️ Usage Workflow

### 1. Configuration
Nexus uses a simple YAML configuration. A default `nexus.yml` is created on initialization.

```yaml
# nexus.yml
mailto: "researcher@university.edu"
providers:
  openalex: { enabled: true }
  s2: { enabled: true }
```

### 2. Define Queries
Create a `queries.yml` file to structure your research questions.

```yaml
# queries.yml
queries:
  - id: Q01
    theme: domain_shift
    query: ("domain shift" OR "dataset shift") AND ("plant disease" OR "agriculture")
    priority: high
```

### 3. Run the Pipeline

**Step 1: Search**
Query all enabled providers.
```bash
nexus search --queries queries.yml
```

**Step 2: Deduplicate**
Merge overlapping results into a unique dataset.
```bash
nexus deduplicate --input results/outputs/latest
```

**Step 3: Screen (AI)**
Filter papers by relevance using an LLM.
```bash
export OPENAI_API_KEY="sk-..."
nexus screen --criteria "Include papers that propose lightweight CNN architectures."
```

**Step 4: Fetch PDFs**
Download full text for the screened papers.
```bash
nexus fetch --limit 10
```

**Step 5: Extract Content**
Convert PDFs to Markdown for analysis.
```bash
nexus extract --tables --images
```
For scientific extraction (clean text + LaTeX math + tables, no references/images).
You can override any defaults (e.g., disable math with `--no-math --no-math-ocr --no-inline-math`):
```bash
nexus extract --scientific
```
Chunks emitted by the extractor now include `section_tags`/`section_role` metadata
so downstream LLM/SLM field extraction (e.g., `full_text_extraction_schema.yaml`)
can target Introduction/Methods/Results/Discussion sections with fewer tokens.

**Step 6: Synthesize & Visualize**
Perform batch analysis and generate automated review drafts.
```bash
nexus analyze
nexus visualize
nexus synthesize
```

---

## 📂 Architecture

Nexus is built as a modular "monorepo" with distinct components:

| Module | Description |
| :--- | :--- |
| **`nexus.ingest`** | Metadata fetching from external APIs (OpenAlex, S2, etc.). |
| **`nexus.screener`** | LLM-based logic for title/abstract screening. |
| **`nexus.retrieval`** | PDF retrieval strategies (Unpaywall, Direct, ArXiv). |
| **`nexus.extraction`** | Advanced PDF processing pipeline (Math, Tables, Layout). |
| **`nexus.analysis`** | Cross-corpus synthesis, visualization, and reporting. |
| **`nexus.core`** | Shared data models (`Document`) and configuration. |

---

## 🗺️ Roadmap

- [x] **Core:** CLI, Config, Logging, Rich UI.
- [x] **Search:** OpenAlex, Semantic Scholar, ArXiv support.
- [x] **Deduplication:** Exact DOI/ArXiv matching.
- [x] **Retrieval:** Basic PDF fetching (OA + ArXiv).
- [x] **Extraction:** Integration of `pdf-struct-rag` pipeline.
- [x] **Analysis:** Batch metadata extraction and visualization.
- [x] **Synthesis:** Automated draft generation with LLMs.
- [ ] **Deduplication:** Semantic (embedding-based) matching.
- [ ] **Screening:** Support for local LLMs (Ollama/Llama.cpp).
- [ ] **Advanced AI:** "Chat with Papers" RAG interface.

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to set up your development environment.

1.  Fork the repo.
2.  Create a feature branch (`git checkout -b feature/amazing-feature`).
3.  Commit your changes (`git commit -m 'Add amazing feature'`).
4.  Push to the branch (`git push origin feature/amazing-feature`).
5.  Open a Pull Request.

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
