"""
Tests for unified DSL query translation across providers.
"""

import unittest
from nexus.core.models import Query
from nexus.providers.arxiv import ArxivProvider
from nexus.providers.pubmed import PubMedProvider
from nexus.providers.ieee import IEEEProvider
from nexus.providers.core import CoreProvider
from nexus.providers.doaj import DOAJProvider
from nexus.core.config import ProviderConfig

class TestDSLTranslation(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig(enabled=True)
        self.query = Query(text='title:"Deep Learning" AND author:Smith')

    def test_arxiv_translation(self):
        provider = ArxivProvider(self.config)
        params = provider._translate_query(self.query)
        # Arxiv uses ti: and au:
        self.assertIn('ti:"Deep Learning"', params["search_query"])
        self.assertIn('au:Smith', params["search_query"])
        self.assertIn('AND', params["search_query"])

    def test_pubmed_translation(self):
        provider = PubMedProvider(self.config)
        params = provider._translate_query(self.query)
        # PubMed uses [Title] and [Author]
        self.assertIn('"Deep Learning"[Title]', params["term"])
        self.assertIn('Smith[Author]', params["term"])
        self.assertIn('AND', params["term"])

    def test_ieee_translation(self):
        provider = IEEEProvider(self.config)
        # IEEE requires API key to even init search params usually, 
        # but let's test just the translation if possible
        provider.config.api_key = "test"
        # We need to reach the params part
        translation = provider.translator.translate(self.query)
        q = translation["q"]
        self.assertIn('article_title:"Deep Learning"', q)
        self.assertIn('author:Smith', q)

    def test_nested_parentheses(self):
        nested_query = Query(text='(title:Deep OR title:Neural) AND author:Smith')
        provider = ArxivProvider(self.config)
        params = provider._translate_query(nested_query)
        # Check for parentheses preservation
        q = params["search_query"]
        self.assertIn('(ti:Deep OR ti:Neural)', q)
        self.assertIn('AND au:Smith', q)

if __name__ == '__main__':
    unittest.main()
