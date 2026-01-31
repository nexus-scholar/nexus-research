"""
Tests for resume functionality in search.
"""

import unittest
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from nexus.core.config import SLRConfig, ProvidersConfig, ProviderConfig
from nexus.cli.search import _search_provider_worker

class TestSearchResume(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.test_dir)
        
        self.config = SLRConfig(
            providers=ProvidersConfig(
                openalex=ProviderConfig(enabled=True)
            )
        )
        self.queries = [{"id": "Q1", "text": "test query"}]

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('nexus.cli.search.load_documents')
    @patch('nexus.cli.search.save_documents')
    @patch('nexus.cli.search.get_provider')
    def test_resume_skips_existing(self, mock_get_provider, mock_save_documents, mock_load_documents):
        # Setup: Create a fake existing results file
        prov_dir = self.output_dir / "openalex"
        prov_dir.mkdir(parents=True)
        results_file = prov_dir / "Q1_results.jsonl"
        results_file.write_text('{"title": "Existing Doc"}', encoding="utf-8")
        
        # Mock load_documents to return something when file is read
        mock_doc = MagicMock()
        mock_doc.title = "Existing Doc"
        mock_load_documents.return_value = [mock_doc]

        # Mock provider (should NOT be called for search)
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider

        # Mock progress
        mock_progress = MagicMock()

        # Run worker with resume=True
        count = _search_provider_worker(
            "openalex",
            self.config,
            self.queries,
            self.output_dir,
            max_results=10,
            output_format="jsonl",
            progress=mock_progress,
            task_id=1,
            resume=True
        )

        # Assertions
        self.assertEqual(count, 1) # Should count the existing doc
        
        # search() should NOT be called because we resumed
        mock_provider.search.assert_not_called()
        
        # load_documents should be called for the existing file
        mock_load_documents.assert_called_with(results_file)
        
        # save_documents should be called once at the end for aggregation
        # (It's NOT called for the individual query file since we skipped it)
        self.assertEqual(mock_save_documents.call_count, 1)

    @patch('nexus.cli.search.load_documents')
    @patch('nexus.cli.search.save_documents')
    @patch('nexus.cli.search.get_provider')
    def test_no_resume_overwrites(self, mock_get_provider, mock_save_documents, mock_load_documents):
        # Setup: Create a fake existing results file
        prov_dir = self.output_dir / "openalex"
        prov_dir.mkdir(parents=True)
        results_file = prov_dir / "Q1_results.jsonl"
        results_file.write_text('{"title": "Old Doc"}', encoding="utf-8")

        # Mock provider (SHOULD be called)
        mock_provider = MagicMock()
        mock_new_doc = MagicMock()
        mock_new_doc.title = "New Doc"
        mock_provider.search.return_value = iter([mock_new_doc])
        mock_get_provider.return_value = mock_provider

        # Mock progress
        mock_progress = MagicMock()

        # Run worker with resume=False
        count = _search_provider_worker(
            "openalex",
            self.config,
            self.queries,
            self.output_dir,
            max_results=10,
            output_format="jsonl",
            progress=mock_progress,
            task_id=1,
            resume=False
        )

        self.assertEqual(count, 1)
        
        # search() SHOULD be called
        mock_provider.search.assert_called()
        
        # load_documents should NOT be called
        mock_load_documents.assert_not_called()

if __name__ == '__main__':
    unittest.main()
