"""
Phase 9: The Cartographer (Table Extraction & Parsing)

Extracts and structures tables from PDF documents.
- Uses PyMuPDF's find_tables() for bordered table detection
- Uses pymupdf4llm for text-based table extraction
- Multi-strategy approach picks the best result
- Exports to multiple formats: Markdown, CSV, JSON, DataFrame
- Preserves table structure including merged cells
- Links tables to page numbers for citation
- Stores table metadata for RAG queries

TODO / Future Improvements:
-------------------------
1. COMPLEX TABLES: Handle multi-span tables (merged cells spanning multiple columns/rows)
   - Current limitation: Pages with complex spanning tables (e.g., pages 4, 5)
     produce sparse/incorrect results
   - Potential solution: Use Table Transformer models (Microsoft TATR) for
     ML-based table structure recognition

2. PYMUPDF-LAYOUT ML MODEL: Investigate using DocumentLayoutAnalyzer.predict()
   - The model exists (BoxRFDGNN) but requires correct input format
   - Could improve table detection accuracy

3. IMAGE-BASED EXTRACTION: For tables without clear structure
   - Render page as image, use OCR + table detection
   - Useful for scanned PDFs or tables rendered as graphics

4. ROTATED HEADERS: Tables with vertical/rotated header text
   - Requires image-based OCR approach

5. MULTI-PAGE TABLES: Tables spanning multiple pages
   - Currently treated as separate tables
   - Need heuristics to detect and merge continuation tables

6. DOMAIN-SPECIFIC PATTERNS: Scientific paper table conventions
   - Standard patterns like "Table 1:", footnotes, units in headers
   - Could improve caption detection and header parsing
"""

import json
import csv
import io
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

import pymupdf

# Try to import pymupdf4llm for enhanced extraction
try:
    import pymupdf4llm
    HAS_PYMUPDF4LLM = True
except ImportError:
    HAS_PYMUPDF4LLM = False


@dataclass
class TableCell:
    """A single cell in a table."""
    text: str
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractedTable:
    """A table extracted from a PDF page."""
    table_id: str
    page_number: int
    row_count: int
    col_count: int
    headers: list[str]
    rows: list[list[str]]
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    caption: str = ""
    source_file: str = ""

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "page_number": self.page_number,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "headers": self.headers,
            "rows": self.rows,
            "bbox": list(self.bbox),
            "caption": self.caption,
            "source_file": self.source_file,
        }

    def to_markdown(self) -> str:
        """Convert table to Markdown format."""
        if not self.rows and not self.headers:
            return ""

        lines = []

        # Add caption if present
        if self.caption:
            lines.append(f"**{self.caption}**\n")

        # Determine column widths for better formatting
        all_rows = [self.headers] + self.rows if self.headers else self.rows
        if not all_rows:
            return ""

        col_count = max(len(row) for row in all_rows)

        # Headers
        if self.headers:
            header_row = self.headers + [""] * (col_count - len(self.headers))
            lines.append("| " + " | ".join(str(h) for h in header_row) + " |")
            lines.append("| " + " | ".join(["---"] * col_count) + " |")
        else:
            # No headers, create a separator anyway
            lines.append("| " + " | ".join(["---"] * col_count) + " |")

        # Data rows
        for row in self.rows:
            padded_row = list(row) + [""] * (col_count - len(row))
            # Clean cell content (replace newlines, pipes)
            cleaned = [str(cell).replace("\n", " ").replace("|", "\\|") for cell in padded_row]
            lines.append("| " + " | ".join(cleaned) + " |")

        return "\n".join(lines)

    def to_csv(self) -> str:
        """Convert table to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)

        if self.headers:
            writer.writerow(self.headers)

        for row in self.rows:
            writer.writerow(row)

        return output.getvalue()

    def to_dataframe(self):
        """Convert table to pandas DataFrame (if pandas available)."""
        try:
            import pandas as pd

            if self.headers:
                return pd.DataFrame(self.rows, columns=self.headers)
            else:
                return pd.DataFrame(self.rows)
        except ImportError:
            raise ImportError("pandas is required for to_dataframe(). Install with: pip install pandas")

    def to_text(self) -> str:
        """Convert table to plain text format for RAG indexing."""
        lines = []

        if self.caption:
            lines.append(f"Table: {self.caption}")
        else:
            lines.append(f"Table on Page {self.page_number}")

        if self.headers:
            lines.append("Headers: " + ", ".join(str(h) for h in self.headers))

        for i, row in enumerate(self.rows):
            row_text = ", ".join(f"{self.headers[j] if self.headers and j < len(self.headers) else f'Col{j+1}'}: {cell}"
                                  for j, cell in enumerate(row))
            lines.append(f"Row {i+1}: {row_text}")

        return "\n".join(lines)


@dataclass
class TableExtractionResult:
    """Result of extracting tables from a PDF."""
    tables: list[ExtractedTable]
    source_file: str
    total_pages: int
    pages_with_tables: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "total_pages": self.total_pages,
            "table_count": len(self.tables),
            "pages_with_tables": self.pages_with_tables,
            "tables": [t.to_dict() for t in self.tables],
        }

    def get_tables_for_page(self, page_number: int) -> list[ExtractedTable]:
        """Get all tables on a specific page."""
        return [t for t in self.tables if t.page_number == page_number]

    def to_markdown_all(self) -> str:
        """Convert all tables to a single Markdown document."""
        sections = []
        for table in self.tables:
            sections.append(f"### Table on Page {table.page_number}\n")
            sections.append(table.to_markdown())
            sections.append("")
        return "\n".join(sections)


def generate_table_id(page_number: int, table_index: int, source_file: str) -> str:
    """Generate a unique table ID."""
    import hashlib
    hash_input = f"{source_file}:p{page_number}:t{table_index}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:12]


def find_table_caption(page: pymupdf.Page, table_bbox: tuple, direction: str = "above") -> str:
    """
    Try to find a caption for the table by looking above or below it.

    Captions typically start with "Table X" or "TABLE X".
    """
    import re

    x0, y0, x1, y1 = table_bbox
    page_height = page.rect.height

    # Define search area
    if direction == "above":
        # Look 50 points above the table
        search_rect = pymupdf.Rect(x0 - 20, max(0, y0 - 60), x1 + 20, y0)
    else:
        # Look 50 points below the table
        search_rect = pymupdf.Rect(x0 - 20, y1, x1 + 20, min(page_height, y1 + 60))

    # Extract text from the search area
    text = page.get_text("text", clip=search_rect).strip()

    # Look for table caption patterns
    caption_patterns = [
        r"^Table\s+\d+[.:]\s*(.+)$",
        r"^TABLE\s+\d+[.:]\s*(.+)$",
        r"^Tab\.\s*\d+[.:]\s*(.+)$",
    ]

    for line in text.split("\n"):
        line = line.strip()
        for pattern in caption_patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return line  # Return the full caption line

    # If no pattern match, check if any line starts with "Table"
    for line in text.split("\n"):
        line = line.strip()
        if line.lower().startswith("table"):
            return line

    return ""


# Table detection strategies in order of preference
TABLE_STRATEGIES = ["lines_strict", "lines", "text"]


def clean_cell_text(text: str) -> str:
    """Clean cell text by removing special unicode characters and normalizing whitespace."""
    if not text:
        return ""
    # Replace narrow no-break space and other special whitespace
    text = text.replace('\u202f', ' ').replace('\u00a0', ' ')
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.strip()


def merge_fragmented_headers(headers: list[str]) -> list[str]:
    """
    Merge fragmented headers that were split due to column detection issues.

    Example: ['Table 1 Groups of', 'pesticides', 'based on...']
    -> ['Groups of pesticides based on...']
    """
    if not headers:
        return headers

    # Check if headers look fragmented (contain "Table X" pattern spread across cells)
    combined = ' '.join(h for h in headers if h)

    # If the combined text starts with "Table X", it's likely a caption that got mixed in
    import re
    table_match = re.match(r'^Table\s*\d+[\s.:]+(.+)$', combined, re.IGNORECASE)
    if table_match:
        # Return the actual header content without "Table X" prefix
        actual_content = table_match.group(1).strip()
        # This is a single merged header row
        return [actual_content] if actual_content else headers

    return headers


def remove_empty_rows_and_cols(rows: list[list[str]], headers: list[str]) -> tuple[list[list[str]], list[str]]:
    """Remove rows and columns that are completely empty."""
    if not rows:
        return rows, headers

    # Determine column count
    col_count = len(headers) if headers else (max(len(r) for r in rows) if rows else 0)
    if col_count == 0:
        return rows, headers

    # Find columns that have at least some content
    non_empty_cols = []
    for col_idx in range(col_count):
        has_content = False
        # Check header
        if headers and col_idx < len(headers) and headers[col_idx].strip():
            has_content = True
        # Check rows
        for row in rows:
            if col_idx < len(row) and row[col_idx].strip():
                has_content = True
                break
        if has_content:
            non_empty_cols.append(col_idx)

    # Filter headers
    if headers:
        headers = [headers[i] for i in non_empty_cols if i < len(headers)]

    # Filter rows
    new_rows = []
    for row in rows:
        new_row = [row[i] if i < len(row) else "" for i in non_empty_cols]
        # Only add row if it has some content
        if any(cell.strip() for cell in new_row):
            new_rows.append(new_row)

    return new_rows, headers


def is_table_too_sparse(rows: list[list[str]], headers: list[str], threshold: float = 0.7) -> bool:
    """Check if table has too many empty cells (likely a detection error)."""
    if not rows:
        return True

    total_cells = 0
    empty_cells = 0

    for row in rows:
        for cell in row:
            total_cells += 1
            if not cell.strip():
                empty_cells += 1

    if total_cells == 0:
        return True

    return (empty_cells / total_cells) > threshold


def post_process_table(table: ExtractedTable) -> ExtractedTable | None:
    """
    Post-process a table to clean up common extraction issues.
    Returns None if the table should be discarded.
    """
    # Skip tables that are too sparse
    if is_table_too_sparse(table.rows, table.headers, threshold=0.8):
        # Only skip if table is very large (likely a detection error)
        if table.row_count > 10 or table.col_count > 10:
            return None

    # Clean up headers
    headers = merge_fragmented_headers(table.headers)

    # Remove empty rows and columns
    rows, headers = remove_empty_rows_and_cols(table.rows, headers)

    # Skip if table is now empty
    if not rows and not headers:
        return None

    # Create updated table
    return ExtractedTable(
        table_id=table.table_id,
        page_number=table.page_number,
        row_count=len(rows),
        col_count=len(headers) if headers else (max(len(r) for r in rows) if rows else 0),
        headers=headers,
        rows=rows,
        bbox=table.bbox,
        caption=table.caption,
        source_file=table.source_file,
    )


def parse_markdown_table(markdown_lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """
    Parse a Markdown table into headers and rows.

    Args:
        markdown_lines: Lines of markdown containing a table

    Returns:
        Tuple of (headers, rows)
    """
    headers = []
    rows = []
    in_table = False

    for line in markdown_lines:
        line = line.strip()
        if not line.startswith('|'):
            if in_table:
                # End of table
                break
            continue

        in_table = True

        # Split by | and clean
        cells = [clean_cell_text(c) for c in line.split('|')[1:-1]]

        # Skip separator row (|---|---|)
        if all(set(c.strip()) <= set('-:') for c in cells):
            continue

        if not headers:
            headers = cells
        else:
            rows.append(cells)

    return headers, rows


def extract_tables_from_markdown(
    doc: pymupdf.Document,
    page_number: int,
    source_file: str = "",
) -> list[ExtractedTable]:
    """
    Extract tables from a page using pymupdf4llm's markdown output.

    This method is better for text-aligned tables without borders.
    """
    if not HAS_PYMUPDF4LLM:
        return []

    tables = []

    try:
        # Extract markdown with table detection
        result = pymupdf4llm.to_markdown(
            doc,
            pages=[page_number - 1],  # 0-indexed
            page_chunks=True,
            table_strategy="lines_strict",  # Try strict first
        )

        if not result:
            return []

        text = result[0].get('text', '')
        lines = text.split('\n')

        # Find table blocks (consecutive lines with |)
        table_blocks = []
        current_block = []

        for line in lines:
            if '|' in line and line.strip().startswith('|'):
                current_block.append(line)
            elif current_block:
                if len(current_block) >= 2:  # At least header + separator
                    table_blocks.append(current_block)
                current_block = []

        if current_block and len(current_block) >= 2:
            table_blocks.append(current_block)

        # Parse each table block
        for i, block in enumerate(table_blocks):
            headers, rows = parse_markdown_table(block)

            if not headers and not rows:
                continue

            # Try to find caption (look for "Table X" pattern before the table)
            caption = ""
            block_start_idx = lines.index(block[0]) if block[0] in lines else -1
            if block_start_idx > 0:
                for j in range(block_start_idx - 1, max(0, block_start_idx - 5), -1):
                    if re.match(r'.*Table\s*\d+', lines[j], re.IGNORECASE):
                        caption = clean_cell_text(lines[j])
                        break

            table_id = generate_table_id(page_number, i, source_file)

            table = ExtractedTable(
                table_id=table_id,
                page_number=page_number,
                row_count=len(rows),
                col_count=len(headers) if headers else (max(len(r) for r in rows) if rows else 0),
                headers=headers,
                rows=rows,
                bbox=(0, 0, 0, 0),  # Unknown bbox from markdown
                caption=caption,
                source_file=source_file,
            )

            tables.append(table)

    except Exception as e:
        print(f"Warning: pymupdf4llm table extraction failed: {e}")

    return tables


def detect_rotated_headers(page: pymupdf.Page, table_bbox: tuple) -> bool:
    """
    Check if the table header area contains rotated text (vertical text).

    Args:
        page: PyMuPDF Page object
        table_bbox: Bounding box of the table (x0, y0, x1, y1)

    Returns:
        True if rotated text is detected in the header area
    """
    x0, y0, x1, y1 = table_bbox
    # Define header area (approx top 20% or top 50pt of table)
    header_height = min((y1 - y0) * 0.2, 80)
    header_rect = pymupdf.Rect(x0, y0, x1, y0 + header_height)

    # Get text dict in header area
    try:
        text_dict = page.get_text("dict", clip=header_rect)
    except Exception:
        return False

    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            # Check for non-horizontal text
            # dir=(1, 0) is horizontal. (0, -1) or (0, 1) is vertical
            if abs(line["dir"][1]) > 0.1:  # Significant vertical component
                return True
            # Also check char-level rotation for some PDFs
            for span in line["spans"]:
                # If individual chars are rotated
                if span.get("rotation", 0) != 0:
                    return True

    return False


def extract_tables_from_page_with_strategy(
    page: pymupdf.Page,
    page_number: int,
    source_file: str = "",
    find_captions: bool = True,
    strategy: str = "lines_strict",
) -> list[ExtractedTable]:
    """
    Extract tables from a page using a specific strategy.

    Args:
        page: PyMuPDF Page object
        page_number: 1-indexed page number
        source_file: Name of the source PDF file
        find_captions: Whether to search for table captions
        strategy: Table detection strategy ("lines_strict", "lines", "text")

    Returns:
        List of ExtractedTable objects
    """
    tables = []

    try:
        # Use PyMuPDF's table finder with specified strategy
        table_finder = page.find_tables(strategy=strategy)
    except Exception:
        return []

    for i, table in enumerate(table_finder.tables):
        try:
            # Check for rotated headers (feature B in improvement plan)
            has_rotated_headers = detect_rotated_headers(page, tuple(table.bbox))
            
            # Get raw table data
            table_data = table.extract()

            if not table_data or len(table_data) == 0:
                continue

            # Clean and structure the data
            headers = []
            rows = []

            if table.header and table.header.names:
                headers = [clean_cell_text(str(h)) if h else "" for h in table.header.names]
                rows = [[clean_cell_text(str(cell)) if cell else "" for cell in row] for row in table_data[1:]]
            else:
                first_row = table_data[0]
                if first_row and all(isinstance(cell, str) or cell is None for cell in first_row):
                    headers = [clean_cell_text(str(cell)) if cell else "" for cell in first_row]
                    rows = [[clean_cell_text(str(cell)) if cell else "" for cell in row] for row in table_data[1:]]
                else:
                    rows = [[clean_cell_text(str(cell)) if cell else "" for cell in row] for row in table_data]

            # Skip if table is too small or empty
            if len(rows) == 0 and len(headers) == 0:
                continue

            # Get bounding box
            bbox = tuple(table.bbox)

            # Find caption
            caption = ""
            if find_captions:
                caption = find_table_caption(page, bbox, "above")
                if not caption:
                    caption = find_table_caption(page, bbox, "below")
                caption = clean_cell_text(caption)
                
            # If rotated headers detected, mark in caption or metadata
            if has_rotated_headers:
                if caption:
                    caption += " (Contains Rotated Headers)"
                else:
                    caption = "Table with Rotated Headers"

            # Generate table ID
            table_id = generate_table_id(page_number, i, source_file)

            extracted = ExtractedTable(
                table_id=table_id,
                page_number=page_number,
                row_count=len(rows),
                col_count=table.col_count,
                headers=headers,
                rows=rows,
                bbox=bbox,
                caption=caption,
                source_file=source_file,
            )

            tables.append(extracted)

        except Exception as e:
            print(f"Warning: Failed to extract table {i+1} on page {page_number}: {e}")
            continue

    return tables


def should_scan_for_tables(page: pymupdf.Page) -> bool:
    """
    Heuristic check to decide if we should run the expensive table finder on this page.
    Returns True if the page likely contains a table.
    """
    try:
        # 1. Text Search (Fastest)
        text = page.get_text("text")  
        
        # Check for explicit keywords (capture Table 1, TABLE I, etc.)
        if re.search(r"Table\s+\d+|TABLE\s+\d+|Tab\.\s*\d+|Table\s+[IVX]+", text, re.IGNORECASE):
            return True
            
        # 2. Structure Density Check
        # Tables have high numeric density
        digits = sum(c.isdigit() for c in text)
        non_space = sum(1 for c in text if not c.isspace())
        
        if non_space > 100:  # Avoid empty pages
            digit_ratio = digits / non_space
            # If > 10% of chars are digits, it might be a data-heavy table without a standard caption
            if digit_ratio > 0.10:  
                return True
            
    except Exception:
        # If in doubt, scan it
        return True
        
    return False


def extract_tables_from_page(
    page: pymupdf.Page,
    page_number: int,
    source_file: str = "",
    find_captions: bool = True,
) -> list[ExtractedTable]:
    """
    Extract all tables from a single PDF page using the Smart Strategy Selector.
    
    Implements 'Feature A' from improvement plan: Voting system for best strategy.

    Args:
        page: PyMuPDF Page object
        page_number: 1-indexed page number
        source_file: Name of the source PDF file
        find_captions: Whether to search for table captions

    Returns:
        List of ExtractedTable objects
    """
    best_tables = []
    best_score = -1
    
    # OPTIMIZATION: Smart Table Guard
    # Skip expensive ONNX model if page doesn't look like a table
    if not should_scan_for_tables(page):
        return []

    # Try all strategies
    results = {}
    
    for strategy in TABLE_STRATEGIES:
        try:
            tables = extract_tables_from_page_with_strategy(
                page, page_number, source_file, find_captions, strategy
            )
            
            # Post-process tables
            processed_tables = []
            for table in tables:
                processed = post_process_table(table)
                if processed:
                    processed_tables.append(processed)
            
            # Score this strategy result
            if not processed_tables:
                score = 0
            else:
                # Score formula: (rows * cols) * data_density
                score = 0
                for t in processed_tables:
                    cells = (t.row_count + (1 if t.headers else 0)) * t.col_count
                    
                    # Calculate density (non-empty cells / total cells)
                    non_empty = 0
                    if t.headers:
                        non_empty += sum(1 for h in t.headers if h.strip())
                    for row in t.rows:
                        non_empty += sum(1 for c in row if c.strip())
                    
                    density = non_empty / cells if cells > 0 else 0
                    
                    # Reward larger tables, but heavily penalize sparse ones (likely garbage)
                    table_score = cells * (density ** 2) # Square density to punish sparsity more
                    score += table_score
            
            results[strategy] = (score, processed_tables)
            
            if score > best_score:
                best_score = score
                best_tables = processed_tables
                
        except Exception:
            continue
            
    # Optional: Debug print to see which strategy won
    # winning_strategy = [s for s, (scr, _) in results.items() if scr == best_score]
    # if winning_strategy:
    #     print(f"Page {page_number}: Strategy '{winning_strategy[0]}' won with score {best_score:.1f}")
        
    return best_tables


def extract_tables_from_page_legacy(
    page: pymupdf.Page,
    page_number: int,
    source_file: str = "",
    find_captions: bool = True,
) -> list[ExtractedTable]:
    """
    Legacy single-strategy table extraction (kept for compatibility).

    Args:
        page: PyMuPDF Page object
        page_number: 1-indexed page number
        source_file: Name of the source PDF file
        find_captions: Whether to search for table captions

    Returns:
        List of ExtractedTable objects
    """
    tables = []

    # Use PyMuPDF's table finder
    table_finder = page.find_tables()

    for i, table in enumerate(table_finder.tables):
        # Extract table data
        try:
            # Get raw table data
            table_data = table.extract()

            if not table_data or len(table_data) == 0:
                continue

            # Determine headers
            headers = []
            rows = []

            if table.header and table.header.names:
                headers = [str(h) if h else "" for h in table.header.names]
                # Data rows start after header
                rows = [[str(cell) if cell else "" for cell in row] for row in table_data[1:]]
            else:
                # First row might be headers - heuristic check
                first_row = table_data[0]
                # If first row looks like headers (all strings, no numbers)
                if first_row and all(isinstance(cell, str) or cell is None for cell in first_row):
                    headers = [str(cell) if cell else "" for cell in first_row]
                    rows = [[str(cell) if cell else "" for cell in row] for row in table_data[1:]]
                else:
                    rows = [[str(cell) if cell else "" for cell in row] for row in table_data]

            # Get bounding box
            bbox = tuple(table.bbox)

            # Find caption
            caption = ""
            if find_captions:
                caption = find_table_caption(page, bbox, "above")
                if not caption:
                    caption = find_table_caption(page, bbox, "below")

            # Generate table ID
            table_id = generate_table_id(page_number, i, source_file)

            extracted = ExtractedTable(
                table_id=table_id,
                page_number=page_number,
                row_count=len(rows),
                col_count=table.col_count,
                headers=headers,
                rows=rows,
                bbox=bbox,
                caption=caption,
                source_file=source_file,
            )

            tables.append(extracted)

        except Exception as e:
            print(f"Warning: Failed to extract table {i+1} on page {page_number}: {e}")
            continue

    return tables


def extract_tables_from_pdf(
    pdf_path: str | Path,
    pages: list[int] | None = None,
    find_captions: bool = True,
    use_markdown_fallback: bool = True,
) -> TableExtractionResult:
    """
    Extract all tables from a PDF document.

    Uses a multi-strategy approach:
    1. PyMuPDF find_tables() with different strategies
    2. pymupdf4llm markdown extraction as fallback

    Args:
        pdf_path: Path to the PDF file
        pages: Specific pages to extract from (1-indexed), or None for all
        find_captions: Whether to search for table captions
        use_markdown_fallback: Whether to use pymupdf4llm as fallback

    Returns:
        TableExtractionResult with all extracted tables
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = pymupdf.open(str(pdf_path))

    try:
        all_tables = []
        pages_with_tables = []

        # Determine which pages to process
        if pages:
            page_indices = [p - 1 for p in pages if 0 <= p - 1 < len(doc)]
        else:
            page_indices = range(len(doc))

        for page_idx in page_indices:
            page = doc[page_idx]
            page_number = page_idx + 1
            print(f"    Scanning tables on page {page_number}/{len(doc)}...", end="\r")
            
            # Try PyMuPDF find_tables first
            page_tables = extract_tables_from_page(
                page,
                page_number,
                source_file=pdf_path.name,
                find_captions=find_captions,
            )

            # If no good tables found and markdown fallback enabled, try that
            if use_markdown_fallback and HAS_PYMUPDF4LLM:
                pymupdf_score = sum(t.row_count * t.col_count for t in page_tables)

                # Try markdown extraction
                md_tables = extract_tables_from_markdown(doc, page_number, pdf_path.name)
                md_score = sum(t.row_count * t.col_count for t in md_tables)

                # Use markdown tables if they're better
                if md_score > pymupdf_score:
                    page_tables = md_tables

            if page_tables:
                pages_with_tables.append(page_number)
                all_tables.extend(page_tables)

        return TableExtractionResult(
            tables=all_tables,
            source_file=pdf_path.name,
            total_pages=len(doc),
            pages_with_tables=pages_with_tables,
        )

    finally:
        doc.close()


def save_tables(
    result: TableExtractionResult,
    output_dir: str | Path,
    formats: list[str] = ["json", "markdown"],
) -> dict[str, Path]:
    """
    Save extracted tables to files.

    Args:
        result: TableExtractionResult to save
        output_dir: Directory to save files to
        formats: List of formats to save ("json", "markdown", "csv")

    Returns:
        Dict mapping format to saved file path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = Path(result.source_file).stem
    saved_files = {}

    if "json" in formats:
        json_path = output_dir / f"{base_name}_tables.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        saved_files["json"] = json_path

    if "markdown" in formats:
        md_path = output_dir / f"{base_name}_tables.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Tables from {result.source_file}\n\n")
            f.write(f"Total tables: {len(result.tables)}\n\n")
            f.write(result.to_markdown_all())
        saved_files["markdown"] = md_path

    if "csv" in formats:
        # Save each table as a separate CSV
        csv_dir = output_dir / f"{base_name}_tables_csv"
        csv_dir.mkdir(parents=True, exist_ok=True)

        for table in result.tables:
            csv_path = csv_dir / f"table_p{table.page_number}_{table.table_id[:8]}.csv"
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                f.write(table.to_csv())

        saved_files["csv"] = csv_dir

    return saved_files


def tables_to_chunks(
    result: TableExtractionResult,
    include_markdown: bool = True,
    include_text: bool = True,
) -> list[dict]:
    """
    Convert extracted tables to chunk format for RAG indexing.

    Args:
        result: TableExtractionResult
        include_markdown: Include Markdown representation
        include_text: Include plain text representation

    Returns:
        List of chunk dictionaries ready for vector store
    """
    chunks = []

    for table in result.tables:
        # Build chunk text
        text_parts = []

        if table.caption:
            text_parts.append(f"Table: {table.caption}")
        else:
            text_parts.append(f"Table on Page {table.page_number}")

        if include_text:
            text_parts.append(table.to_text())

        if include_markdown:
            text_parts.append("\nMarkdown representation:")
            text_parts.append(table.to_markdown())

        chunk = {
            "id": f"table_{table.table_id}",
            "text": "\n".join(text_parts),
            "metadata": {
                "type": "table",
                "table_id": table.table_id,
                "page_number": table.page_number,
                "source_file": table.source_file,
                "row_count": table.row_count,
                "col_count": table.col_count,
                "caption": table.caption,
                "headers": table.headers,
                "bbox": list(table.bbox),
            }
        }

        chunks.append(chunk)

    return chunks
