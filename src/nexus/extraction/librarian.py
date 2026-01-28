"""
Phase 5: The Librarian (Citation Resolution)

Parses references sections and links citations to their full bibliographic data.
- Extracts numbered reference lists from markdown
- Parses author, title, year, venue from each reference
- Injects citation metadata into chunks
"""

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import json


@dataclass
class Reference:
    """A parsed bibliographic reference."""
    number: int
    raw_text: str
    authors: str = ""
    title: str = ""
    year: int | None = None
    venue: str = ""
    doi: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def short_cite(self) -> str:
        """Short citation format: 'Author et al., Year'"""
        if self.authors and self.year:
            # Get first author's last name
            first_author = self.authors.split(",")[0].split(" ")[-1].strip()
            if "," in self.authors or " and " in self.authors.lower():
                return f"{first_author} et al., {self.year}"
            return f"{first_author}, {self.year}"
        elif self.year:
            return str(self.year)
        return f"[{self.number}]"


@dataclass
class ReferenceLibrary:
    """Collection of parsed references for a document."""
    references: dict[int, Reference] = field(default_factory=dict)
    source_file: str = ""

    def get(self, number: int) -> Reference | None:
        return self.references.get(number)

    def __len__(self) -> int:
        return len(self.references)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "count": len(self.references),
            "references": {str(k): v.to_dict() for k, v in self.references.items()}
        }


# =============================================================================
# Reference Parsing
# =============================================================================

# Pattern to match numbered references: "1.", "1)", "[1]", "1 "
NUMBERED_REF_PATTERN = re.compile(
    r'^(?:\[?(\d+)\]?[\.\)\s])\s*(.+?)$',
    re.MULTILINE
)

# Pattern to extract year (4-digit number between 1900-2099)
YEAR_PATTERN = re.compile(r'\b((?:19|20)\d{2})\b')

# Pattern to extract DOI
DOI_PATTERN = re.compile(r'(?:doi[:\s]*|https?://doi\.org/)([^\s]+)', re.IGNORECASE)

# Pattern to find title (often in quotes or after authors before year)
TITLE_PATTERN = re.compile(r'["""](.+?)["""]')


def parse_reference_text(number: int, text: str) -> Reference:
    """
    Parse a single reference entry into structured data.

    This uses heuristics since reference formats vary widely.
    """
    ref = Reference(number=number, raw_text=text.strip())

    # Extract year
    year_match = YEAR_PATTERN.search(text)
    if year_match:
        ref.year = int(year_match.group(1))

    # Extract DOI
    doi_match = DOI_PATTERN.search(text)
    if doi_match:
        ref.doi = doi_match.group(1).rstrip('.')

    # Extract title (often in quotes)
    title_match = TITLE_PATTERN.search(text)
    if title_match:
        ref.title = title_match.group(1).strip()

    # Heuristic: Authors are usually before the year
    if ref.year:
        year_pos = text.find(str(ref.year))
        if year_pos > 10:
            # Text before year is likely authors
            authors_text = text[:year_pos].strip()
            # Clean up trailing punctuation
            authors_text = re.sub(r'[\(\)\[\],.:]+$', '', authors_text).strip()
            ref.authors = authors_text

    # If no authors found, take first part before any parentheses
    if not ref.authors:
        paren_match = re.match(r'^([^(]+)', text)
        if paren_match:
            ref.authors = paren_match.group(1).strip().rstrip(',.:')

    return ref


def parse_references_markdown(text: str) -> list[Reference]:
    """
    Parse a references section markdown text into structured references.

    Handles formats like:
    - "1. Author Name (2020) Title..."
    - "[1] Author Name. Title. Journal, 2020."
    - "1) Author Name, Title, 2020"
    """
    references = []

    if not text.strip():
        return references

    # Split by lines and look for numbered entries
    lines = text.split('\n')
    current_ref_num = None
    current_ref_text = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this line starts a new numbered reference
        # Patterns: "1.", "1)", "[1]", "1 AuthorName"
        num_match = re.match(r'^(?:\[?(\d+)\]?[\.\)\s])\s*(.*)$', line)

        if num_match:
            # Save previous reference if exists
            if current_ref_num is not None and current_ref_text:
                full_text = ' '.join(current_ref_text)
                references.append(parse_reference_text(current_ref_num, full_text))

            # Start new reference
            current_ref_num = int(num_match.group(1))
            current_ref_text = [num_match.group(2)] if num_match.group(2) else []
        elif current_ref_num is not None:
            # Continuation of current reference
            current_ref_text.append(line)

    # Don't forget the last reference
    if current_ref_num is not None and current_ref_text:
        full_text = ' '.join(current_ref_text)
        references.append(parse_reference_text(current_ref_num, full_text))

    return references


def build_reference_library(references_text: str, source_file: str = "") -> ReferenceLibrary:
    """
    Build a ReferenceLibrary from references markdown text.
    """
    refs = parse_references_markdown(references_text)
    library = ReferenceLibrary(
        references={r.number: r for r in refs},
        source_file=source_file
    )
    return library


# =============================================================================
# Citation Injection
# =============================================================================

# Pattern to find citations in text: [1], [12], [1,2,3], [1-3]
CITATION_PATTERN = re.compile(r'\[(\d+(?:[,\-–]\s*\d+)*)\]')

try:
    from rapidfuzz import process, fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


def extract_citation_numbers(text: str) -> set[int]:
    """Extract all citation numbers from text."""
    numbers = set()
    for match in CITATION_PATTERN.finditer(text):
        citation_str = match.group(1)
        # Handle ranges like "1-3" or "1–3"
        if '-' in citation_str or '–' in citation_str:
            parts = re.split(r'[-–]', citation_str)
            if len(parts) == 2:
                try:
                    start, end = int(parts[0].strip()), int(parts[1].strip())
                    numbers.update(range(start, end + 1))
                except ValueError:
                    pass
        else:
            # Handle comma-separated like "1,2,3"
            for num_str in citation_str.split(','):
                try:
                    numbers.add(int(num_str.strip()))
                except ValueError:
                    pass
    return numbers


def extract_author_date_citations(text: str) -> list[str]:
    """
    Extract author-date citations like "(Smith, 2020)" or "(Smith et al., 2020)".
    
    This is a heuristic extraction to find candidates for fuzzy matching.
    """
    # Pattern: (Author et al., 20xx) or (Author, 20xx)
    candidates = []
    
    # Heuristic regex: parens containing text ending with a 4-digit year
    # Matches: (Smith, 2020), (Smith et al, 2020), (A. Smith, 2020)
    # Does NOT match: (see Figure 1), (equation 2)
    
    # Look for parens with year at end
    pattern = re.compile(r'\(([A-Za-z\s\.,]+?)\s*,?\s*((?:19|20)\d{2})\)')
    
    for match in pattern.finditer(text):
        full_match = match.group(0)
        author_part = match.group(1).strip()
        year_part = match.group(2)
        
        # specific blacklist
        if any(x in author_part.lower() for x in ["fig", "table", "eq", "section", "chapter", "page"]):
            continue
            
        candidates.append(f"{author_part}, {year_part}")
        
    return candidates


def find_citation_by_fuzzy_match(
    citation_text: str,
    library: ReferenceLibrary,
    threshold: int = 85
) -> Reference | None:
    """
    Find a reference in the library that matches the citation text fuzzily.
    
    Args:
        citation_text: Text like "Smith et al., 2020"
        library: ReferenceLibrary to search
    
    Returns:
        Reference object if found, else None
    """
    if not HAS_RAPIDFUZZ:
        return None
        
    # Build search corpus: "Author et al., Year" or "Author, Title, Year"
    choices = {}
    for ref in library.references.values():
        # Create a rich string for matching
        # Include short cite (e.g. "Smith et al., 2020") explicitly to catch exact format matches
        # Include Title and Authors for disambiguation
        match_str = f"{ref.short_cite()} {ref.authors} {ref.year} {ref.title}"
        choices[ref.number] = match_str
        
    if not choices:
        return None
        
    # Run fuzzy match
    # extractOne returns (match, score, index) or (match, score, key) depending on input
    result = process.extractOne(
        citation_text, 
        choices, 
        scorer=fuzz.token_set_ratio,
        score_cutoff=threshold
    )
    
    if result:
        match_str, score, key = result
        return library.get(key)
        
    return None


def inject_citations_into_chunk(
    chunk: dict,
    library: ReferenceLibrary,
) -> dict:
    """
    Add citation metadata to a chunk based on [N] references AND fuzzy author-date matches.

    Returns a new chunk dict with 'citations' field added.
    """
    text = chunk.get("text", "")
    citations_map = {}
    
    # 1. Exact Numbered Matches [1]
    citation_numbers = extract_citation_numbers(text)
    for num in citation_numbers:
        ref = library.get(num)
        if ref:
            citations_map[str(num)] = {
                "authors": ref.authors,
                "title": ref.title,
                "year": ref.year,
                "short": ref.short_cite(),
                "type": "exact_number"
            }
            
    # 2. Fuzzy Author-Date Matches (Smith, 2020)
    # Only if rapidfuzz is available and we have references
    if HAS_RAPIDFUZZ and len(library) > 0:
        candidates = extract_author_date_citations(text)
        for cand in candidates:
            # Try to match
            match = find_citation_by_fuzzy_match(cand, library)
            if match:
                # Use number as key if available, else generate a hash
                key = str(match.number)
                if key not in citations_map:
                    citations_map[key] = {
                        "authors": match.authors,
                        "title": match.title,
                        "year": match.year,
                        "short": match.short_cite(),
                        "type": "fuzzy_match",
                        "matched_text": cand
                    }

    # Create new chunk with citations
    new_chunk = dict(chunk)
    new_chunk["citations"] = citations_map
    return new_chunk


def inject_citations_into_chunks(
    chunks: list[dict],
    library: ReferenceLibrary,
) -> list[dict]:
    """
    Add citation metadata to all chunks.
    """
    return [inject_citations_into_chunk(c, library) for c in chunks]


# =============================================================================
# File I/O
# =============================================================================

def save_reference_library(library: ReferenceLibrary, output_path: str | Path) -> Path:
    """Save reference library to JSON file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(library.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return output_path


def load_reference_library(input_path: str | Path) -> ReferenceLibrary:
    """Load reference library from JSON file."""
    input_path = Path(input_path)
    data = json.loads(input_path.read_text(encoding="utf-8"))

    refs = {}
    for num_str, ref_data in data.get("references", {}).items():
        num = int(num_str)
        refs[num] = Reference(
            number=num,
            raw_text=ref_data.get("raw_text", ""),
            authors=ref_data.get("authors", ""),
            title=ref_data.get("title", ""),
            year=ref_data.get("year"),
            venue=ref_data.get("venue", ""),
            doi=ref_data.get("doi", ""),
        )

    return ReferenceLibrary(
        references=refs,
        source_file=data.get("source_file", "")
    )


if __name__ == "__main__":
    # Test with a sample references section
    sample_refs = """
## **References**

1. Vaswani A, Shazeer N, Parmar N (2017) Attention is all you need. In: Advances in neural information processing systems, pp 5998–6008

2. Devlin J, Chang MW, Lee K, Toutanova K (2019) BERT: pre-training of deep bidirectional transformers for language understanding. arXiv:1810.04805

3. Brown T, Mann B, Ryder N et al (2020) Language models are few-shot learners. Advances in neural information processing systems 33:1877–1901
    """

    library = build_reference_library(sample_refs, "test.pdf")
    print(f"Parsed {len(library)} references:")
    for num, ref in library.references.items():
        print(f"  [{num}] {ref.short_cite()}")
        print(f"       Authors: {ref.authors}")
        print(f"       Year: {ref.year}")
