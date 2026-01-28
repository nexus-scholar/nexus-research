"""
Phase 1: The Sanitizer (Core Extraction)
Phase 3: The Visionary (Image Extraction & Filtering)

Converts a noisy PDF into structured page-based Markdown chunks.
- Uses page_chunks=True for structured extraction with metadata
- Removes headers/footers using PyMuPDF Layout
- Preserves page numbers for citation tracking
- Detects and truncates references section
- [Phase 3] Extracts and filters images (removing icons/logos/junk)
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import pymupdf.layout  # Must be imported first to activate layout feature
import pymupdf4llm
import pymupdf


# Image filtering constants (Phase 3)
MIN_IMAGE_WIDTH = 200
MIN_IMAGE_HEIGHT = 200
MIN_IMAGE_SIZE_KB = 5
MAX_ASPECT_RATIO = 5.0  # Avoid long thin separator lines


@dataclass
class PageChunk:
    """A single page's extracted content with metadata."""
    page_number: int
    text: str
    metadata: dict = field(default_factory=dict)
    images: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)

    @property
    def is_references_page(self) -> bool:
        """Check if this page contains the references section start."""
        return self.metadata.get("is_references", False)


@dataclass
class SanitizedDocument:
    """Result of sanitizing a PDF document."""
    pages: list[PageChunk]
    source_path: Path
    total_pages: int
    image_dir: Path | None = None  # Phase 3: Directory where images are stored

    @property
    def body_pages(self) -> list[PageChunk]:
        """Get only body content pages (before references)."""
        return [p for p in self.pages if not p.metadata.get("is_references", False)]

    @property
    def reference_pages(self) -> list[PageChunk]:
        """Get only reference section pages."""
        return [p for p in self.pages if p.metadata.get("is_references", False)]

    @property
    def body_text(self) -> str:
        """Get combined body text (for backward compatibility)."""
        return "\n\n".join(p.text for p in self.body_pages)

    @property
    def references(self) -> str:
        """Get combined references text (for backward compatibility)."""
        return "\n\n".join(p.text for p in self.reference_pages)


# Patterns to detect the start of the references section
# These patterns handle various markdown formats:
# - ## References (header only)
# - **References** (bold only)
# - ## **References** (header + bold combined)
# - # **References** (any header level + bold)
REFERENCE_PATTERNS = [
    # Header + Bold combined (e.g., "## **References**")
    r"^#{1,6}\s*\*\*References?\*\*\s*$",
    r"^#{1,6}\s*\*\*Bibliography\*\*\s*$",
    r"^#{1,6}\s*\*\*Works?\s+Cited\*\*\s*$",
    r"^#{1,6}\s*\*\*Literature\s+Cited\*\*\s*$",
    # Header only (e.g., "## References")
    r"^#{1,6}\s+References?\s*$",
    r"^#{1,6}\s+Bibliography\s*$",
    r"^#{1,6}\s+Works?\s+Cited\s*$",
    r"^#{1,6}\s+Literature\s+Cited\s*$",
    # Bold only (e.g., "**References**")
    r"^\*\*References?\*\*\s*$",
    r"^\*\*Bibliography\*\*\s*$",
    # Plain text (e.g., "References")
    r"^References?\s*$",
    r"^Bibliography\s*$",
]


def detect_references_start(text: str) -> bool:
    """Check if the text contains the start of a references section."""
    combined_pattern = "|".join(f"({p})" for p in REFERENCE_PATTERNS)
    for line in text.split("\n"):
        if re.match(combined_pattern, line.strip(), re.IGNORECASE):
            return True
    return False


# =============================================================================
# Phase 3: Image Filtering Functions
# =============================================================================

def filter_images(image_dir: Path) -> set[str]:
    """
    Scan extracted images and delete 'junk' (icons, lines, spacers).

    Returns a set of valid filenames to keep in the markdown.
    """
    valid_images = set()
    if not image_dir.exists():
        return valid_images

    for img_path in image_dir.glob("*"):
        if not img_path.is_file():
            continue

        # Filter 1: File size (too small = icon/logo)
        if img_path.stat().st_size < MIN_IMAGE_SIZE_KB * 1024:
            img_path.unlink()
            continue

        # Filter 2: Dimensions & Aspect Ratio
        try:
            # Use pymupdf to read image dimensions
            with pymupdf.open(img_path) as img_doc:
                if len(img_doc) == 0:
                    img_path.unlink()
                    continue
                pix = img_doc[0].get_pixmap()
                w, h = pix.width, pix.height

                # Too small
                if w < MIN_IMAGE_WIDTH or h < MIN_IMAGE_HEIGHT:
                    img_path.unlink()
                    continue

                # Bad aspect ratio (separator lines, thin decorations)
                aspect = w / h if h > 0 else 0
                if aspect > MAX_ASPECT_RATIO or aspect < (1 / MAX_ASPECT_RATIO):
                    img_path.unlink()
                    continue

                valid_images.add(img_path.name)

        except Exception:
            # If we can't read it, delete it
            try:
                img_path.unlink()
            except Exception:
                pass

    return valid_images


def clean_markdown_images(text: str, valid_images: set[str]) -> str:
    """
    Remove markdown image tags for images that were deleted by the filter.

    Input: "Here is text.\n![](images/deleted.png)\nMore text."
    Output: "Here is text.\nMore text."
    """
    lines = text.split('\n')
    cleaned_lines = []

    # Regex to find standard markdown images: ![alt](path)
    img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')

    for line in lines:
        match = img_pattern.search(line)
        if match:
            path_str = match.group(2)
            filename = Path(path_str).name
            if filename not in valid_images:
                # Skip this line (it refers to a deleted image)
                continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


# =============================================================================
# Main Extraction Functions
# =============================================================================

def sanitize_pdf(
    pdf_path: str | Path,
    image_output_dir: str | Path | None = None,
) -> SanitizedDocument:
    """
    Convert a PDF file to structured page-based Markdown.

    This is the main entry point for Phase 1 (The Sanitizer).
    If image_output_dir is provided, also extracts and filters images (Phase 3).

    Args:
        pdf_path: Path to the PDF file
        image_output_dir: Optional directory to extract images to

    Returns:
        SanitizedDocument with structured page chunks
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Prepare image directory if requested
    write_images = False
    if image_output_dir:
        image_output_dir = Path(image_output_dir)
        image_output_dir.mkdir(parents=True, exist_ok=True)
        write_images = True

    doc = pymupdf.open(str(pdf_path))

    try:
        # Extract with optional image writing
        raw_chunks = pymupdf4llm.to_markdown(
            doc,
            page_chunks=True,
            header=False,
            footer=False,
            write_images=write_images,
            image_path=str(image_output_dir) if write_images else None,
            image_format="png",
        )
    finally:
        doc.close()

    # Phase 3: Filter junk images
    valid_images = set()
    if write_images and image_output_dir:
        valid_images = filter_images(image_output_dir)

    pages = []
    references_started = False

    for i, chunk in enumerate(raw_chunks):
        text = chunk.get("text", "")

        # Phase 3: Clean markdown text (remove broken image links)
        if write_images:
            text = clean_markdown_images(text, valid_images)

        metadata = chunk.get("metadata", {})
        page_num = metadata.get("page", i) + 1
        images = chunk.get("images", [])
        tables = chunk.get("tables", [])

        if not references_started and detect_references_start(text):
            references_started = True

        page_chunk = PageChunk(
            page_number=page_num,
            text=text.strip(),
            metadata={
                **metadata,
                "is_references": references_started,
                "has_images": len(images) > 0,
                "has_tables": len(tables) > 0,
                "image_count": len(images),
                "table_count": len(tables),
            },
            images=images,
            tables=tables,
        )
        pages.append(page_chunk)

    return SanitizedDocument(
        pages=pages,
        source_path=pdf_path,
        total_pages=len(pages),
        image_dir=image_output_dir if write_images else None,
    )


def save_sanitized_document(
    doc: SanitizedDocument,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Save markdown files to disk."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = doc.source_path.stem
    body_path = output_dir / f"{base_name}_body.md"
    references_path = output_dir / f"{base_name}_references.md"

    body_path.write_text(doc.body_text, encoding="utf-8")
    references_path.write_text(doc.references, encoding="utf-8")

    return body_path, references_path


def process_pdf(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    extract_images: bool = False,
) -> tuple[SanitizedDocument, tuple[Path, Path] | None]:
    """
    Full pipeline: sanitize a PDF and optionally save to disk.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Optional directory to save output files
        extract_images: Whether to extract images (Phase 3)

    Returns:
        Tuple of (SanitizedDocument, (body_path, references_path) or None)
    """
    pdf_path = Path(pdf_path)

    # Setup image directory if extracting
    image_dir = None
    if extract_images and output_dir:
        image_dir = Path(output_dir) / "images" / pdf_path.stem

    doc = sanitize_pdf(pdf_path, image_output_dir=image_dir)

    saved_paths = None
    if output_dir:
        saved_paths = save_sanitized_document(doc, output_dir)

    return doc, saved_paths


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python sanitizer.py <pdf_path> [output_dir]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./output"

    print(f"Processing: {pdf_path}")
    doc, paths = process_pdf(pdf_path, output_dir, extract_images=True)

    if paths:
        print(f"Body text saved to: {paths[0]}")
        print(f"References saved to: {paths[1]}")

    print(f"\nTotal pages: {doc.total_pages}")
    print(f"Body pages: {len(doc.body_pages)}")
    print(f"Reference pages: {len(doc.reference_pages)}")

    if doc.image_dir:
        image_count = len(list(doc.image_dir.glob("*"))) if doc.image_dir.exists() else 0
        print(f"Images extracted: {image_count} (in {doc.image_dir})")
