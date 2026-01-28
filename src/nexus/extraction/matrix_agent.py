
"""
Phase 3: The Literature Matrix Generator (Agent)

This module transforms unstructured Rich Chunks into a continuous structured table (CSV).
It uses an LLM to "fill in the blanks" defined by a YAML schema.
"""

import json
import yaml
import csv
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, List, Dict

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

@dataclass
class ColumnSchema:
    name: str
    description: str
    type: str  # text, number, boolean
    required: bool = False

@dataclass
class MatrixSchema:
    columns: List[ColumnSchema]
    
    @classmethod
    def from_yaml(cls, path: str | Path):
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        cols = []
        for c in data.get('columns', []):
            cols.append(ColumnSchema(
                name=c['name'],
                description=c['description'],
                type=c.get('type', 'text'),
                required=c.get('required', False)
            ))
        return cls(columns=cols)

class MatrixAgent:
    def __init__(
        self, 
        schema_path: str | Path,
        base_url: str | None = None, # e.g. "http://localhost:11434/v1" for Ollama
        api_key: str | None = None,
        model: str = "gpt-4o-mini"
    ):
        if OpenAI is None:
            raise ImportError("The 'openai' library is required. Run: pip install openai")
            
        self.schema = MatrixSchema.from_yaml(schema_path)
        
        # Default to local if no key provided
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "ollama") # Ollama needs any non-empty string
            if not base_url and "ollama" in api_key:
                base_url = "http://localhost:11434/v1"
                
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def _build_system_prompt(self) -> str:
        prompt = "You are a precise data extraction assistant for a systematic literature review.\n"
        prompt += "Your goal is to extract specific fields from a research paper based on the provided text and tables.\n\n"
        prompt += "SCHEMA (Fields to extract):\n"
        for col in self.schema.columns:
            prompt += f"- {col.name} ({col.type}): {col.description}\n"
        
        prompt += "\nRULES:\n"
        prompt += "1. Return the result as a strictly valid JSON object.\n"
        prompt += "2. If a field is not found, use null.\n"
        prompt += "3. Checks tables carefully. If a metric is in a table, prefer the table value.\n"
        prompt += "4. Do not hallucinate. If uncertain, leave null or add a note.\n"
        return prompt

    def _prepare_context(self, chunks: List[Dict]) -> str:
        """Filter and compress chunks for the context window."""
        # Heuristic: Focus on Abstract, Introduction, Results, Conclusions
        # And Chunks with Tables
        
        context = ""
        for chunk in chunks:
            # We assume small papers for now. For large ones, we'd need RAG retrieval here.
            # But the user wants to "extract juice", so we dump mostly everything relevant.
            
            section = chunk.get("metadata", {}).get("section", "")
            text = chunk.get("text", "")
            
            # Add table data if present (High Value!)
            tables = chunk.get("metadata", {}).get("tables_on_page", [])
            table_str = ""
            if tables:
                table_str = "\n[TABLE DATA FOUND]: " + json.dumps(tables)
            
            context += f"--- Section: {section} ---\n{text}{table_str}\n\n"
            
        return context[:50000] # Hard limit characters to avoid blowing up context window (approx 12k tokens)

    def extract_row(self, chunks: List[Dict], paper_id: str) -> Dict:
        """Extract a single row for the matrix from the paper's chunks."""
        context = self._prepare_context(chunks)
        system_prompt = self._build_system_prompt()
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract data for paper ID: {paper_id}\n\nDOCUMENT CONTENT:\n{context}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            result_json = response.choices[0].message.content
            data = json.loads(result_json)
            
            # Ensure all schema columns exist
            row = {"Paper ID": paper_id}
            for col in self.schema.columns:
                row[col.name] = data.get(col.name, None)
                
            return row
            
        except Exception as e:
            print(f"Error extracting row for {paper_id}: {e}")
            return {"Paper ID": paper_id, "Error": str(e)}

    def generate_matrix(self, chunks_dir: str | Path, output_csv: str | Path):
        """Process all chunks.json files in a directory and save to CSV."""
        chunks_dir = Path(chunks_dir)
        output_csv = Path(output_csv)
        
        rows = []
        chunk_files = list(chunks_dir.glob("*_chunks.json"))
        
        print(f"Processing {len(chunk_files)} papers...")
        
        for f in chunk_files:
            print(f"  - Analyzing {f.name}...")
            with open(f, 'r', encoding='utf-8') as cf:
                chunks = json.load(cf)
            
            paper_id = f.stem.replace("_chunks", "")
            row = self.extract_row(chunks, paper_id)
            rows.append(row)
            
        # Write to CSV
        fieldnames = ["Paper ID"] + [c.name for c in self.schema.columns]
        
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
            
        print(f"✅ Matrix saved to {output_csv}")

if __name__ == "__main__":
    # Test stub
    pass  
