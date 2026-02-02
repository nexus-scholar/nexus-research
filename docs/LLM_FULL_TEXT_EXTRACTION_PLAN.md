# LLM Full-Text Extraction Module Plan

## Goal
Create a new extraction module that runs LLM/SLM full-text field extraction driven by the schema in `full_text_extraction_schema.yaml` (updated schema, bibliographic fields trimmed). The module should select only the most relevant chunks (Introduction/Methods/Results/Discussion, etc.) to minimize token usage while preserving extraction quality, and split extraction into smaller field groups to reduce hallucinations.

## Scope
- Inputs: processed extraction outputs (chunks JSON), schema YAML, and config settings.
- Outputs: structured JSON/JSONL per paper matching schema fields, plus optional metadata for auditability.
- Must leverage `section_tags`/`section_role` metadata added during chunking.

## Proposed Location
- New module: `src/nexus/extraction/full_text_extractor.py`
- Optional CLI: `src/nexus/cli/full_text_extract.py` (hooked into `nexus` CLI later)
- Plan stored in this file.

## Data Flow
1. Load schema from `full_text_extraction_schema.yaml`.
2. Load document chunks (`*_chunks.json`) from extraction output directory.
3. Select chunks by section priority and cap tokens (e.g., intro/methods/results/discussion).
4. Split schema fields into logical groups and build concise prompts per group.
5. Run LLM/SLM extraction per group with strict abstention ("NR") rules.
6. Post-process into validated structured output with sanity checks.
7. Save results as JSON/JSONL for downstream RAG/analytics.

## Chunk Selection Strategy
- Primary: `section_tags` and `section_role` metadata.
- Fallback: keyword scan of chunk text for headers if metadata missing.
- Heuristics: detect uppercase/numbered headings when tags are absent (e.g., "3. CONCLUSION").
- Token budgeting:
  - default: prefer Methods + Results + Discussion, then Introduction, then Abstract
  - hard cap per paper (configurable)
- Ensure table chunks are included if referenced or if `section_role == results`.

## Schema Parsing
- Parse `full_text_extraction_schema.yaml` into:
  - field id
  - description
  - type (+ object_fields if any)
- Use it to construct a deterministic prompt template.

## Field Grouping Strategy
Use grouped prompts to reduce hallucinations and control token usage:
- Group 1: research context and scope (objective, hypotheses, task, crops, diseases)
- Group 2: data and dataset details (datasets, data collection, splits, augmentation)
- Group 3: models and training (architectures, training details, domain shift, compression, data-centric)
- Group 4: evaluation and deployment (metrics, cross-dataset, inference, hardware, explainability, limits, future work, reproducibility)

Each group uses a compact, directive prompt that:
- requires JSON output with specified keys
- enforces "NR" for missing fields (no guessing)
- optionally includes short evidence snippets per field (safe passage)

## Model Invocation
- Use existing LLM client (`nexus.screener.client.LLMClient`) or add a new generic extraction client.
- Support local SLMs later (configurable in YAML).

## Output Format
- JSON per paper:
  - `paper_id`, `source_file`, `schema_name`, `extraction` (fields dict), `meta` (chunk ids used, token estimate, model, timestamp)
- Optional JSONL batch output for large corpora.
- Store prompt/response logs (optional) for auditability and cost tracking.
 - Optional evidence map: field -> supporting snippet(s)

## Config Additions (nexus.yml)
- `full_text_extraction:`
  - `schema_path`: default `full_text_extraction_schema.yaml`
  - `max_tokens`: extraction budget
  - `section_priority`: ordered list
  - `include_tables`: bool
  - `model`: model name
  - `group_models`: per-group model override (e.g., g1/g2/g3/g4)
  - `group_fields`: explicit field groups (override defaults)
  - `require_evidence`: bool (include evidence snippets)
  - `batch_size`: number of papers per call (if batching prompts)
  - `resume`: bool (skip already extracted papers)
  - `log_prompts`: bool (store prompt/response metadata)

## Testing Plan
- Unit tests for:
  - schema parsing
  - chunk selection ordering + token budgeting
  - output validation against schema types
  - sanity checks (year, metric ranges)

## Implementation Steps
1. Add schema loader + data models (Pydantic) for schema + output.
2. Implement chunk selector using section tags and token budgets.
3. Add group-aware prompt builder with abstention rules and evidence optionality.
4. Implement extraction runner using LLM client (with retries) and incremental group mode.
5. Add output writer (JSON/JSONL) and metadata summary + optional prompt logs.
6. Add basic tests and sanity validation.

## Milestones
- M1: schema loader + chunk selection (no LLM calls yet)
- M2: LLM extraction + output JSON
- M3: CLI wrapper + config integration + tests
 - M4: resume support + audit logs + validation pass
