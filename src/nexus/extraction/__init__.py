"""Nexus Extraction - PDF processing pipeline."""

from .sanitizer import sanitize_pdf, SanitizedDocument, PageChunk
from .chunker import (
    chunk_markdown,
    chunk_pages,
    Chunk,
    save_chunks,
    load_chunks,
    extract_images_from_text,
)
from .librarian import (
    build_reference_library,
    parse_references_markdown,
    inject_citations_into_chunks,
    extract_citation_numbers,
    Reference,
    ReferenceLibrary,
    save_reference_library,
    load_reference_library,
)
from .translator import (
    extract_equation_candidates,
    save_candidates,
    extract_math_from_pdf,
    group_math_by_page,
    filter_stamps,
    VisualCandidate,
    latex_ocr_from_pixmap,
)
from .ocr import (
    ocr_page_text,
    detect_ocr_pages,
    apply_ocr_to_chunks,
    tesseract_available,
)
from .table_extractor import (
    extract_tables_from_pdf,
    extract_tables_from_page,
    save_tables,
    tables_to_chunks,
    ExtractedTable,
    TableExtractionResult,
)
from .pipeline import process_pdf_to_chunks, process_directory, ProcessedDocument

__version__ = "0.1.0"

__all__ = [
    # Phase 1: Sanitizer
    "sanitize_pdf",
    "SanitizedDocument",
    "PageChunk",
    # Phase 2: Chunker
    "chunk_markdown",
    "chunk_pages",
    "Chunk",
    "save_chunks",
    "load_chunks",
    # Phase 3: Visionary
    "extract_images_from_text",
    # Phase 4: Translator
    "extract_equation_candidates",
    "save_candidates",
    "extract_math_from_pdf",
    "group_math_by_page",
    "filter_stamps",
    "VisualCandidate",
    "latex_ocr_from_pixmap",
    # OCR helpers
    "ocr_page_text",
    "detect_ocr_pages",
    "apply_ocr_to_chunks",
    "tesseract_available",
    # Phase 5: Librarian
    "build_reference_library",
    "parse_references_markdown",
    "inject_citations_into_chunks",
    "extract_citation_numbers",
    "Reference",
    "ReferenceLibrary",
    "save_reference_library",
    "load_reference_library",
    # Phase 9: Cartographer (Tables)
    "extract_tables_from_pdf",
    "extract_tables_from_page",
    "save_tables",
    "tables_to_chunks",
    "ExtractedTable",
    "TableExtractionResult",
    # Pipeline
    "process_pdf_to_chunks",
    "process_directory",
    "ProcessedDocument",
]
