"""
Tests for normalization utilities.
"""

import unittest
from datetime import datetime
from nexus.normalization.standardizer import DateParser, AuthorParser, ResponseNormalizer

class TestNormalization(unittest.TestCase):
    def test_date_parser_year(self):
        self.assertEqual(DateParser.extract_year("2023-01-01"), 2023)
        self.assertEqual(DateParser.extract_year(2022), 2022)
        self.assertEqual(DateParser.extract_year({"year": 2021}), 2021)
        self.assertEqual(DateParser.extract_year("May 2020"), 2020)
        self.assertIsNone(DateParser.extract_year("invalid"))

    def test_date_parser_datetime(self):
        dt = DateParser.parse_date("2023-01-15")
        self.assertIsInstance(dt, datetime)
        self.assertEqual(dt.year, 2023)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)

    def test_author_parser(self):
        # "Last, First"
        p1 = AuthorParser.parse_author_name("Doe, John")
        self.assertEqual(p1["family"], "Doe")
        self.assertEqual(p1["given"], "John")

        # "First Last"
        p2 = AuthorParser.parse_author_name("Jane Smith")
        self.assertEqual(p2["family"], "Smith")
        self.assertEqual(p2["given"], "Jane")

        # "Last"
        p3 = AuthorParser.parse_author_name("SingleName")
        self.assertEqual(p3["family"], "SingleName")
        self.assertIsNone(p3["given"])

    def test_author_list_parsing(self):
        raw_authors = [
            {"name": "Alice Wonderland", "orcid": "0000-0000-0000-0000"},
            "Bob Builder"
        ]
        authors = AuthorParser.parse_authors(raw_authors)
        self.assertEqual(len(authors), 2)
        self.assertEqual(authors[0].family_name, "Wonderland")
        self.assertEqual(authors[0].given_name, "Alice")
        self.assertEqual(authors[0].orcid, "0000-0000-0000-0000")
        self.assertEqual(authors[1].family_name, "Builder")

if __name__ == '__main__':
    unittest.main()
