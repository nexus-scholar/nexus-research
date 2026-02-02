"""LLM/SLM full-text extraction driven by a schema YAML.

This module selects relevant chunks (Introduction/Methods/Results/Discussion)
and runs grouped LLM extraction to reduce hallucinations and token usage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import os
import yaml
from pydantic import BaseModel, ConfigDict, Field, create_model

from nexus.core.config import FullTextExtractionConfig
from nexus.extraction.chunker import Chunk, load_chunks
from nexus.screener.client import LLMClient

logger = logging.getLogger(__name__)


DEFAULT_GROUPS: dict[str, dict[str, Any]] = {
    "group1_context": {
        "fields": [
            "research_objective",
            "hypotheses",
            "task_type",
            "crop_species",
            "disease_names",
        ],
        "section_priority": ["introduction", "related_work", "abstract"],
    },
    "group2_data": {
        "fields": [
            "datasets",
            "data_collection",
            "train_test_split",
            "augmentation_methods",
        ],
        "section_priority": ["methods", "results"],
    },
    "group3_models": {
        "fields": [
            "architectures",
            "training_details",
            "domain_shift_handling",
            "model_compression",
            "generative_augmentation",
            "data_centric_methods",
        ],
        "section_priority": ["methods"],
    },
    "group4_eval": {
        "fields": [
            "evaluation_metrics",
            "cross_dataset_evaluation",
            "inference_performance",
            "hardware_deployment",
            "explainability_methods",
            "limitations",
            "future_work",
            "reproducibility",
            "peer_review_status",
        ],
        "section_priority": ["results", "discussion", "conclusion"],
    },
}


SECTION_FALLBACK_PATTERNS = {
    "abstract": ["abstract"],
    "introduction": ["introduction", "background", "motivation", "problem statement"],
    "methods": [
        "methods",
        "methodology",
        "materials and methods",
        "experimental setup",
        "implementation",
        "approach",
        "proposed method",
    ],
    "results": ["results", "evaluation", "experiments", "performance"],
    "discussion": ["discussion", "analysis", "interpretation"],
    "related_work": ["related work", "literature review", "prior work"],
    "conclusion": ["conclusion", "concluding", "summary", "future work"],
}


SYSTEM_PROMPT = (
    "You are an AI assistant specialized in extracting structured information "
    "from scientific papers about plant-disease diagnosis using deep learning. "
    "Use only the provided text. If a field is not reported, output \"NR\". "
    "Return a JSON object with the specified keys and no extra commentary."
)


GROUP_TEMPLATES = {
    "group1_context": (
        "Paper_excerpt:\n\"\"\"\n{excerpt}\n\"\"\"\n\n"
        "Extract the following fields as JSON with these keys:\n"
        "- research_objective\n"
        "- hypotheses\n"
        "- task_type (classification, detection, segmentation, severity estimation, or other)\n"
        "- crop_species (list)\n"
        "- disease_names (list)\n\n"
        "If any information is missing, set the value to \"NR\". Do not infer or guess."
    ),
    "group2_data": (
        "Paper_excerpt:\n\"\"\"\n{excerpt}\n\"\"\"\n\n"
        "Extract dataset information and data handling details. Return JSON with:\n"
        "- datasets: list of objects {name, domain (lab/field/mixed/NR), samples, classes}\n"
        "- data_collection\n"
        "- train_test_split\n"
        "- augmentation_methods (list)\n\n"
        "Use only the excerpt and set missing values to \"NR\"."
    ),
    "group3_models": (
        "Paper_excerpt:\n\"\"\"\n{excerpt}\n\"\"\"\n\n"
        "Identify models and training strategies. Return JSON with:\n"
        "- architectures: list of objects {architecture, pretrained (true/false), variant}\n"
        "- training_details: {optimizer, learning_rate, epochs, batch_size, regularization}\n"
        "- domain_shift_handling (list)\n"
        "- model_compression (list)\n"
        "- generative_augmentation (list)\n"
        "- data_centric_methods (list)\n\n"
        "Set missing values to \"NR\" or empty lists as appropriate. Do not guess."
    ),
    "group4_eval": (
        "Paper_excerpt:\n\"\"\"\n{excerpt}\n\"\"\"\n\n"
        "Extract evaluation results and deployment details. Return JSON with:\n"
        "- evaluation_metrics: {accuracy, precision, recall, f1_score, mAP, IoU, cross_dataset, others}\n"
        "- cross_dataset_evaluation\n"
        "- inference_performance: {latency_ms, throughput_fps, model_size_mb, memory_usage_mb}\n"
        "- hardware_deployment\n"
        "- explainability_methods (list)\n"
        "- limitations\n"
        "- future_work\n"
        "- reproducibility\n"
        "- peer_review_status\n\n"
        "Only use the excerpt; if missing, use \"NR\"."
    ),
}

GROUP_INSTRUCTIONS = {
    "group1_context": (
        "Extract the following fields from each paper:\n"
        "- research_objective\n"
        "- hypotheses\n"
        "- task_type (classification, detection, segmentation, severity estimation, or other)\n"
        "- crop_species (list)\n"
        "- disease_names (list)\n"
    ),
    "group2_data": (
        "Extract dataset and data handling details:\n"
        "- datasets: list of objects {name, domain (lab/field/mixed/NR), samples, classes}\n"
        "- data_collection\n"
        "- train_test_split\n"
        "- augmentation_methods (list)\n"
    ),
    "group3_models": (
        "Extract models and training strategies:\n"
        "- architectures: list of objects {architecture, pretrained (true/false), variant}\n"
        "- training_details: {optimizer, learning_rate, epochs, batch_size, regularization}\n"
        "- domain_shift_handling (list)\n"
        "- model_compression (list)\n"
        "- generative_augmentation (list)\n"
        "- data_centric_methods (list)\n"
    ),
    "group4_eval": (
        "Extract evaluation and deployment details:\n"
        "- evaluation_metrics: {accuracy, precision, recall, f1_score, mAP, IoU, cross_dataset, others}\n"
        "- cross_dataset_evaluation\n"
        "- inference_performance: {latency_ms, throughput_fps, model_size_mb, memory_usage_mb}\n"
        "- hardware_deployment\n"
        "- explainability_methods (list)\n"
        "- limitations\n"
        "- future_work\n"
        "- reproducibility\n"
        "- peer_review_status\n"
    ),
}


@dataclass
class ExtractionGroup:
    group_id: str
    fields: list[str]
    section_priority: list[str]


class FieldSpec(BaseModel):
    id: str
    description: str
    type: str
    object_fields: Dict[str, str] | None = None

    model_config = ConfigDict(extra="allow")


class SchemaSpec(BaseModel):
    name: str
    description: str = ""
    fields: list[FieldSpec]

    model_config = ConfigDict(extra="allow")

    def field_by_id(self, field_id: str) -> FieldSpec | None:
        for f in self.fields:
            if f.id == field_id:
                return f
        return None


def load_schema(schema_path: Path) -> SchemaSpec:
    data = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    return SchemaSpec(**data)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _chunk_matches_tag(chunk: Chunk, tag: str) -> bool:
    meta = chunk.metadata or {}
    tags = meta.get("section_tags") or []
    role = meta.get("section_role")
    if tag in tags or role == tag:
        return True

    # Fallback: keyword scan in header or chunk text
    patterns = SECTION_FALLBACK_PATTERNS.get(tag, [])
    haystack = _normalize_text(chunk.text[:400].lower())
    return any(pat in haystack for pat in patterns)


def _select_chunks(
    chunks: list[Chunk],
    *,
    section_priority: list[str],
    max_tokens: int,
    include_tables: bool,
    include_table_tags: bool,
) -> list[Chunk]:
    selected: list[Chunk] = []
    seen_ids = set()
    token_budget = max_tokens

    sorted_chunks = sorted(
        chunks,
        key=lambda c: (c.metadata.get("page_number", 0) or 0, c.id),
    )

    # Select by section priority
    for tag in section_priority:
        for chunk in sorted_chunks:
            if chunk.id in seen_ids:
                continue
            if _chunk_matches_tag(chunk, tag):
                tokens = _estimate_tokens(chunk.text)
                if tokens > token_budget:
                    continue
                selected.append(chunk)
                seen_ids.add(chunk.id)
                token_budget -= tokens
        if token_budget <= 0:
            break

    # Optionally add table chunks
    if include_tables and token_budget > 0:
        for chunk in sorted_chunks:
            if chunk.id in seen_ids:
                continue
            if chunk.metadata.get("type") == "table":
                if include_table_tags and not any(
                    _chunk_matches_tag(chunk, tag) for tag in section_priority
                ):
                    continue
                tokens = _estimate_tokens(chunk.text)
                if tokens > token_budget:
                    continue
                selected.append(chunk)
                seen_ids.add(chunk.id)
                token_budget -= tokens

    return selected


def _object_model_from_field(field: FieldSpec) -> type[BaseModel]:
    object_fields = field.object_fields or {}
    fields: dict[str, tuple[Any, Any]] = {}
    for key in object_fields.keys():
        fields[key] = (Any, None)
    return create_model(f"{field.id.title().replace('_', '')}Model", **fields)


def _field_type(field: FieldSpec) -> Any:
    if field.type == "string":
        return str
    if field.type == "integer":
        return int | str
    if field.type == "float":
        return float | int | str
    if field.type == "list of strings":
        return list[str] | str
    if field.type == "list of objects":
        obj_model = _object_model_from_field(field)
        return list[obj_model] | str
    if field.type == "object":
        return _object_model_from_field(field) | str
    return Any


def _build_group_model(fields: list[FieldSpec], require_evidence: bool) -> type[BaseModel]:
    model_fields: dict[str, tuple[Any, Any]] = {}
    for field in fields:
        model_fields[field.id] = (_field_type(field), None)
    if require_evidence:
        model_fields["evidence"] = (dict[str, str], None)
    return create_model("ExtractionGroupResult", **model_fields)


class FullTextExtractor:
    def __init__(
        self,
        config: FullTextExtractionConfig | None = None,
        client: LLMClient | None = None,
    ) -> None:
        self.config = config or FullTextExtractionConfig()
        self._client = client

    @property
    def client(self) -> LLMClient:
        if self._client is None:
            self._client = LLMClient(model=self.config.model)
        return self._client

    def _client_for_group(self, group_id: str) -> LLMClient:
        if not self.config.group_clients:
            return self.client
        override = self.config.group_clients.get(group_id)
        if not override:
            return self.client
        api_key = None
        api_key_env = override.get("api_key_env") if isinstance(override, dict) else None
        if api_key_env:
            api_key = os.getenv(api_key_env)
        base_url = override.get("base_url") if isinstance(override, dict) else None
        return LLMClient(api_key=api_key, base_url=base_url, model=self.config.model)

    def _get_groups(self, schema: SchemaSpec) -> list[ExtractionGroup]:
        groups: list[ExtractionGroup] = []
        group_definitions = DEFAULT_GROUPS
        if self.config.group_fields:
            group_definitions = {
                group_id: {
                    "fields": fields,
                    "section_priority": self.config.section_priority,
                }
                for group_id, fields in self.config.group_fields.items()
            }

        for group_id, data in group_definitions.items():
            fields = [f for f in data["fields"] if schema.field_by_id(f)]
            if not fields:
                continue
            groups.append(
                ExtractionGroup(
                    group_id=group_id,
                    fields=fields,
                    section_priority=data.get("section_priority", self.config.section_priority),
                )
            )
        return groups

    def extract_from_chunks(
        self,
        chunks: list[Chunk],
        schema: SchemaSpec,
        *,
        source_file: str | None = None,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        meta: dict[str, Any] = {
            "source_file": source_file,
            "schema": schema.name,
            "groups": {},
        }

        groups = self._get_groups(schema)
        for group in groups:
            group_fields = [schema.field_by_id(fid) for fid in group.fields]
            field_specs = [f for f in group_fields if f is not None]

            selected_chunks = _select_chunks(
                chunks,
                section_priority=group.section_priority,
                max_tokens=self.config.max_tokens,
                include_tables=self.config.include_tables,
                include_table_tags=group.group_id in {"group2_data", "group4_eval"},
            )

            excerpt = "\n\n".join(c.text for c in selected_chunks)
            if not excerpt.strip():
                continue

            model_name = self.config.group_models.get(group.group_id, self.config.model)
            response_model = _build_group_model(field_specs, self.config.require_evidence)

            system_prompt = SYSTEM_PROMPT
            user_template = GROUP_TEMPLATES.get(group.group_id, "Paper_excerpt:\n\"\"\"\n{excerpt}\n\"\"\"\n")
            if self.config.require_evidence:
                user_template += (
                    "\nInclude an 'evidence' object mapping field -> short supporting snippet."
                )
            user_prompt = user_template.format(excerpt=excerpt)

            try:
                completion = self.client.client.beta.chat.completions.parse(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format=response_model,
                )
                parsed = completion.choices[0].message.parsed
                group_data = parsed.model_dump() if isinstance(parsed, BaseModel) else parsed
            except Exception as e:
                logger.error("Extraction failed for %s: %s", group.group_id, e)
                group_data = {}

            results.update({k: v for k, v in group_data.items() if k != "evidence"})
            meta["groups"][group.group_id] = {
                "model": model_name,
                "chunk_ids": [c.id for c in selected_chunks],
                "token_estimate": sum(_estimate_tokens(c.text) for c in selected_chunks),
                "evidence": group_data.get("evidence") if isinstance(group_data, dict) else None,
            }
            if self.config.log_prompts:
                meta["groups"][group.group_id]["prompt"] = {
                    "system": system_prompt,
                    "user": user_prompt,
                }

        return {"extraction": results, "meta": meta}

    def _build_batch_prompt(
        self,
        group: ExtractionGroup,
        items: list[dict[str, Any]],
    ) -> str:
        instruction = GROUP_INSTRUCTIONS.get(group.group_id, "Extract the fields listed.")
        prompt = (
            "You will extract fields for multiple papers. "
            "Use only the provided text. If a field is not reported, output \"NR\". "
            "Return a JSON object with key \"items\" as a list of objects. "
            "Each item must include \"paper_id\" plus the requested fields.\n\n"
        )
        prompt += instruction
        if self.config.require_evidence:
            prompt += "\nInclude an 'evidence' object mapping field -> short supporting snippet."
        prompt += "\n\n"

        for item in items:
            prompt += f"<<<PAPER id={item['paper_id']}>>>\n{item['excerpt']}\n<<<END>>>\n\n"
        return prompt

    def extract_from_directory(
        self,
        input_dir: Path,
        output_path: Path,
    ) -> Path:
        schema = load_schema(self.config.schema_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        outputs: list[dict[str, Any]] = []
        existing_ids = set()
        if output_path.exists() and self.config.resume:
            try:
                existing = json.loads(output_path.read_text(encoding="utf-8"))
                if isinstance(existing, list):
                    outputs.extend(existing)
                    existing_ids = {item.get("paper_id") for item in existing if isinstance(item, dict)}
            except Exception:
                pass

        paper_items = []
        for paper_dir in input_dir.iterdir():
            if not paper_dir.is_dir():
                continue
            if self.config.resume and paper_dir.name in existing_ids:
                continue
            chunks_files = list(paper_dir.glob("*_chunks.json"))
            if not chunks_files:
                continue
            chunks = load_chunks(chunks_files[0])
            paper_items.append(
                {
                    "paper_id": paper_dir.name,
                    "source_file": paper_dir.name,
                    "chunks": chunks,
                }
            )

        if not paper_items:
            output_path.write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding="utf-8")
            return output_path

        groups = self._get_groups(schema)
        results_map: dict[str, dict[str, Any]] = {
            item["paper_id"]: {
                "paper_id": item["paper_id"],
                "schema": schema.name,
                "extraction": {},
                "meta": {
                    "source_file": item["source_file"],
                    "schema": schema.name,
                    "groups": {},
                },
            }
            for item in paper_items
        }

        for group in groups:
            group_fields = [schema.field_by_id(fid) for fid in group.fields]
            field_specs = [f for f in group_fields if f is not None]
            if not field_specs:
                continue

            model_name = self.config.group_models.get(group.group_id, self.config.model)
            response_item_model = _build_group_model(field_specs, self.config.require_evidence)
            BatchItem = create_model(
                f"BatchItem_{group.group_id}",
                paper_id=(str, ...),
                **{f.id: (_field_type(f), None) for f in field_specs},
                **({"evidence": (dict[str, str], None)} if self.config.require_evidence else {}),
            )
            BatchResponse = create_model(
                f"BatchResponse_{group.group_id}",
                items=(list[BatchItem], ...),
            )

            batch_size = max(1, self.config.batch_size)
            for batch_start in range(0, len(paper_items), batch_size):
                batch = paper_items[batch_start:batch_start + batch_size]
                batch_payload = []
                for item in batch:
                    selected_chunks = _select_chunks(
                        item["chunks"],
                        section_priority=group.section_priority,
                        max_tokens=self.config.max_tokens,
                        include_tables=self.config.include_tables,
                        include_table_tags=group.group_id in {"group2_data", "group4_eval"},
                    )
                    excerpt = "\n\n".join(c.text for c in selected_chunks)
                    batch_payload.append(
                        {
                            "paper_id": item["paper_id"],
                            "excerpt": excerpt,
                            "chunk_ids": [c.id for c in selected_chunks],
                            "token_estimate": sum(_estimate_tokens(c.text) for c in selected_chunks),
                        }
                    )

                user_prompt = self._build_batch_prompt(group, batch_payload)
                system_prompt = SYSTEM_PROMPT

                try:
                    client = self._client_for_group(group.group_id)
                    completion = client.client.beta.chat.completions.parse(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format=BatchResponse,
                    )
                    parsed = completion.choices[0].message.parsed
                    group_items = parsed.model_dump().get("items", []) if isinstance(parsed, BaseModel) else []
                except Exception as e:
                    logger.error("Batch extraction failed for %s: %s", group.group_id, e)
                    group_items = []

                # Merge results
                for item in batch_payload:
                    entry = results_map[item["paper_id"]]
                    entry["meta"]["groups"][group.group_id] = {
                        "model": model_name,
                        "chunk_ids": item["chunk_ids"],
                        "token_estimate": item["token_estimate"],
                    }
                    if self.config.log_prompts and batch_size == 1:
                        entry["meta"]["groups"][group.group_id]["prompt"] = {
                            "system": system_prompt,
                            "user": user_prompt,
                        }

                for extracted in group_items:
                    paper_id = extracted.get("paper_id")
                    if not paper_id or paper_id not in results_map:
                        continue
                    evidence = extracted.pop("evidence", None)
                    results_map[paper_id]["extraction"].update(extracted)
                    if evidence:
                        results_map[paper_id]["meta"]["groups"][group.group_id]["evidence"] = evidence

        outputs.extend(results_map.values())
        output_path.write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path
