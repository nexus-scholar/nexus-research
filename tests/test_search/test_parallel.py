"""
Tests for parallel search logic.
"""

import unittest
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

from nexus.core.config import SLRConfig, ProvidersConfig, ProviderConfig
from nexus.cli.search import _search_provider_worker

class TestParallelSearch(unittest.TestCase):
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

    @patch('nexus.cli.search.save_documents')
    @patch('nexus.cli.search.get_provider')
    def test_worker_success(self, mock_get_provider, mock_save_documents):
        # Mock provider instance
        mock_provider = MagicMock()
        mock_doc = MagicMock()
        mock_doc.model_dump_json.return_value = '{"title": "Test Doc"}'
        mock_provider.search.return_value = iter([mock_doc])
        mock_get_provider.return_value = mock_provider

        # Mock progress
        mock_progress = MagicMock()

        # Run worker
        count = _search_provider_worker(
            "openalex",
            self.config,
            self.queries,
            self.output_dir,
            max_results=10,
            output_format="jsonl",
            progress=mock_progress,
            task_id=1
        )

        self.assertEqual(count, 1)
        
        # Verify save_documents was called
        # Once for query, once for all results
        self.assertEqual(mock_save_documents.call_count, 2)
        
        # Check call args
        # first call: per query
        args, kwargs = mock_save_documents.call_args_list[0]
        self.assertEqual(len(args[0]), 1) # one doc
        self.assertEqual(args[0][0], mock_doc)
        
    @patch('nexus.cli.search.get_provider')
    def test_worker_failure(self, mock_get_provider):
        # Mock initialization failure
        mock_get_provider.side_effect = Exception("Init failed")
        mock_progress = MagicMock()

        count = _search_provider_worker(
            "openalex",
            self.config,
            self.queries,
            self.output_dir,
            10,
            "jsonl",
            mock_progress,
            1
        )

        self.assertEqual(count, 0)
        mock_progress.console.print.assert_called()

if __name__ == '__main__':
    unittest.main()