"""
Journal Ranking and Impact Filtering.

This module provides tools to identify high-impact (Q1) venues
and filter documents accordingly.
"""

import logging
import re
from typing import List, Optional, Set, Dict
from rapidfuzz import process, fuzz

from nexus.core.models import Document

logger = logging.getLogger(__name__)

# A curated list of Q1 journals relevant to Plant Disease and AI.
# This serves as a primary database for impact filtering.
Q1_JOURNALS = [
    "Frontiers in Plant Science",
    "Plant Disease",
    "IEEE Access",
    "Computers and Electronics in Agriculture",
    "Plant Pathology",
    "Plant Pathology Journal",
    "Agriculture",
    "Plants",
    "AI Open",
    "Scientific Reports",
    "Nature Communications",
    "Sensors",
    "Agronomy",
    "Phytopathology",
    "Molecular Plant Pathology",
    "Journal of Experimental Botany",
    "New Phytologist",
    "Plant Cell and Environment",
    "Journal of Cleaner Production",
    "Remote Sensing of Environment",
    "Precision Agriculture",
    "Smart Agricultural Technology",
    "Engineering in Agriculture, Environment and Food",
    "Transactions of the ASABE",
    "Biosystems Engineering",
    "Information Processing in Agriculture",
    "Artificial Intelligence in Agriculture",
    "Applied Soft Computing",
    "Knowledge-Based Systems",
    "Expert Systems with Applications",
    "Pattern Recognition",
    "Computer Vision and Image Understanding",
    "IEEE Transactions on Pattern Analysis and Machine Intelligence",
    "IEEE Transactions on Image Processing",
    "International Journal of Computer Vision",
    "Neural Networks",
    "Neurocomputing",
    "Decision Support Systems",
    "PLOS ONE",
    "Scientific Data",
    "Nature Plants",
    "The Plant Journal",
    "The Plant Cell",
    "Plant Physiology",
    "Annals of Botany",
    "Current Biology",
    "Cell",
    "Science",
    "Nature",
    "PeerJ",
    "PloS Genetics",
    "Crop Protection",
    "Postharvest Biology and Technology",
    "Trends in Plant Science",
    "Annual Review of Plant Biology",
    "Annual Review of Phytopathology",
    "European Journal of Plant Pathology",
    "Australasian Plant Pathology",
    "Canadian Journal of Plant Pathology",
    "Plant Breeding",
    "Journal of Plant Research",
    "Plant Science",
    "Plant Biology",
    "Planta",
]

class JournalRanker:
    """Helper to identify Q1/High-Impact journals."""

    def __init__(self, q1_list: Optional[List[str]] = None):
        self.q1_journals = q1_list or Q1_JOURNALS
        # Normalize for faster matching
        self._norm_q1 = {j.lower(): j for j in self.q1_journals}

    def is_q1(self, venue: Optional[str], threshold: int = 90) -> bool:
        """
        Check if a venue name matches a known Q1 journal using fuzzy matching.
        """
        if not venue:
            return False

        venue_clean = venue.lower().strip()
        
        # 1. Exact Match (normalized)
        if venue_clean in self._norm_q1:
            return True

        # 2. Strip "MDPI", "Frontiers in", etc.
        simple_name = re.sub(r"\(mdpi\)|mdpi|frontiers in|elsevier|springer|nature", "", venue_clean).strip()
        if simple_name in self._norm_q1:
            return True

        # 3. Fuzzy Match
        match, score, _ = process.extractOne(venue_clean, self.q1_journals, scorer=fuzz.token_set_ratio)
        if score >= threshold:
            logger.debug(f"Fuzzy match: '{venue}' -> '{match}' ({score}%)")
            return True

        return False

    def filter_q1(self, documents: List[Document], threshold: int = 90) -> List[Document]:
        """Filter a list of documents to only those in Q1 venues."""
        return [doc for d in documents if self.is_q1(doc.venue, threshold=threshold)]
