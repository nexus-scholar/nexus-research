#!/usr/bin/env python3
"""
Generate extraction prompts for a set of screened documents.

This script reads one or more JSONL files containing screening results, merges
records by title (later files overwrite earlier ones), filters for documents
where the `decision` field is "include", and constructs a prompt for each
document according to a data‑extraction schema.  The prompts instruct a
language model to extract structured information from the title and abstract
and return a JSON object.  The output is written as a JSONL file where each
line contains a dictionary with the document's identifier and the prompt text.

Example usage:

    python generate_prompts.py \
        --input screening_dedup.jsonl screening_screening.jsonl \
        --output extraction_prompts.jsonl

Author: ChatGPT
Date: 2026-02-02
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List


SCHEMA_FIELDS = [
    "title",
    "year",
    "authors",
    "journal",
    "doi",
    "task_type",
    "crop_and_disease",
    "datasets",
    "models",
    "training_details",
    "performance_metrics",
    "domain_shift_handling",
    "hardware_deployment",
    "data_centric_methods",
    "generative_methods",
    "explainability",
    "study_quality_notes",
    "q1_status",
]


def load_screening_files(paths: List[Path]) -> Dict[str, Dict]:
    """Load screening records from the given JSONL files and merge by title.

    Later files in the list overwrite earlier ones if titles collide.

    Parameters
    ----------
    paths: list of Path
        Paths to JSONL files containing screening results.

    Returns
    -------
    dict
        Mapping from document title to the record dictionary.
    """
    records: Dict[str, Dict] = {}
    for path in paths:
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                record = json.loads(line.strip())
                title = record.get('title')
                if not title:
                    continue
                # Use the last occurrence of a title as authoritative
                records[title] = record
    return records


def build_prompt(record: Dict) -> str:
    """Construct a prompt instructing a language model to extract fields.

    Parameters
    ----------
    record: dict
        The document record with at least 'title' and 'abstract' keys.

    Returns
    -------
    str
        The prompt string to send to the language model.
    """
    title = record.get('title', '').strip()
    abstract = (record.get('abstract') or '').strip()
    if not abstract:
        abstract = "NR"
    # Describe the extraction schema explicitly to the model
    schema_description = ", ".join(SCHEMA_FIELDS)
    prompt = (
        f"You are an expert assistant extracting structured information from scientific articles.\n"
        f"Given the TITLE and ABSTRACT below, extract the following fields: {schema_description}.\n"
        f"If a field is not reported in the text, write 'NR'.\n"
        f"Return the result as a JSON object with keys exactly matching the field names.\n"
        f"\n"
        f"TITLE: {title}\n"
        f"ABSTRACT: {abstract}"
    )
    return prompt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        nargs='+',
        required=True,
        type=Path,
        help="One or more JSONL files containing screening results."
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to the JSONL file where extraction prompts will be saved."
    )
    args = parser.parse_args()
    # Load records and merge by title
    records = load_screening_files(args.input)
    # Filter records where decision == 'include'
    included_records = [rec for rec in records.values() if rec.get('decision') == 'include']
    with args.output.open('w', encoding='utf-8') as f_out:
        for idx, rec in enumerate(included_records, start=1):
            prompt = build_prompt(rec)
            out_obj = {
                "id": idx,
                "title": rec.get('title'),
                "prompt": prompt,
            }
            f_out.write(json.dumps(out_obj, ensure_ascii=False) + "\n")
    print(f"Generated {len(included_records)} prompts in {args.output}")


if __name__ == "__main__":
    main()