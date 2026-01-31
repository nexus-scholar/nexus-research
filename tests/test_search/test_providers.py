"""
Tests for providers.
"""

import unittest
from unittest.mock import MagicMock, patch
from nexus.core.config import ProviderConfig
from nexus.core.models import Query
from nexus.providers.openalex import OpenAlexProvider
from nexus.providers.crossref import CrossrefProvider

class TestProviders(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig(enabled=True, rate_limit=10.0)

    def test_openalex_query_translation(self):
        provider = OpenAlexProvider(self.config)
        query = Query(text="machine learning", year_min=2020)
        params = provider._translate_query(query)
        
        self.assertEqual(params["search"], "machine learning")
        self.assertIn("publication_year:2020", params["filter"])
        self.assertIn("type:article", params["filter"])

    def test_openalex_search(self):
        # Mock API response
        mock_response_data = {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "display_name": "Test Paper",
                    "publication_year": 2021,
                    "authorships": [{"author": {"display_name": "John Doe"}}],
                    "ids": {"doi": "https://doi.org/10.1234/test"}
                }
            ],
            "meta": {"next_cursor": None}
        }

        provider = OpenAlexProvider(self.config)
        # Mock _make_request directly
        provider._make_request = MagicMock(return_value=mock_response_data)

        query = Query(text="test")
        results = list(provider.search(query))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Test Paper")
        self.assertEqual(results[0].year, 2021)
        self.assertEqual(results[0].authors[0].family_name, "Doe")
        self.assertEqual(results[0].external_ids.openalex_id, "W123")

    def test_crossref_query_translation(self):
        provider = CrossrefProvider(self.config)
        query = Query(text="deep learning", year_min=2021)
        params = provider._translate_query(query)

        self.assertEqual(params["query"], "deep learning")
        self.assertIn("from-pub-date:2021", params["filter"])

if __name__ == '__main__':
    unittest.main()
