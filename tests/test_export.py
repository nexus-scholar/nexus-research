"""
Tests for nexus.export module.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from datetime import datetime

from nexus.core.models import Document, Author, ExternalIds, DocumentCluster
from nexus.export.bibtex_exporter import BibTeXExporter
from nexus.export.jsonl_exporter import JSONExporter
from nexus.export.ris_exporter import RISExporter


class TestExporters(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.test_dir)

        # Create sample documents
        self.doc1 = Document(
            title="Deep Learning for Text",
            year=2020,
            authors=[
                Author(family_name="Smith", given_name="John"),
                Author(family_name="Doe", given_name="Jane")
            ],
            venue="Journal of AI",
            abstract="This is a very long abstract about deep learning " * 20,
            external_ids=ExternalIds(doi="10.1234/ai.2020.1"),
            url="https://example.com/1"
        )

        # Doc that would generate same key (Smith + 2020 + Deep)
        self.doc2 = Document(
            title="Deep Neural Networks",
            year=2020,
            authors=[Author(family_name="Smith", given_name="James")],
            venue="AI Conference",
            external_ids=ExternalIds(doi="10.5678/conf.2020.2")
        )

        self.documents = [self.doc1, self.doc2]

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_bibtex_collision_and_truncation(self):
        exporter = BibTeXExporter(output_dir=self.output_dir)
        
        # Test default behavior (no truncation, collision handling)
        output_file = exporter.export_documents(
            self.documents, 
            "test_bib", 
            max_abstract_length=50
        )

        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check keys
        self.assertIn("Smith2020Deep", content)
        self.assertIn("Smith2020Deepa", content)  # Collision resolved

        # Check abstract truncation
        # "This is a very long abstract about deep learning" is 48 chars
        # 50 chars limit -> 47 chars + "..."
        # "This is a very long abstract about deep learnin..."
        self.assertIn("This is a very long abstract about deep learnin...", content)
        self.assertNotIn("This is a very long abstract about deep learning " * 20, content)

    def test_json_stream_writing(self):
        exporter = JSONExporter(output_dir=self.output_dir)
        output_file = exporter.export_documents(self.documents, "test_json")

        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['title'], "Deep Learning for Text")
        self.assertEqual(data[1]['title'], "Deep Neural Networks")

    def test_ris_export(self):
        exporter = RISExporter(output_dir=self.output_dir)
        output_file = exporter.export_documents([self.doc1], "test_ris")

        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("TY  - JOUR", content)
        self.assertIn("TI  - Deep Learning for Text", content)
        self.assertIn("AU  - Smith, John", content)
        self.assertIn("AU  - Doe, Jane", content)
        self.assertIn("PY  - 2020", content)
        self.assertIn("DO  - 10.1234/ai.2020.1", content)
        self.assertIn("ER  -", content)

if __name__ == '__main__':
    unittest.main()
