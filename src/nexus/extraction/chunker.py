"""
Phase 2: The Architect (Semantic Chunking)
Phase 3: The Visionary (Image Linking)

Turns the Markdown stream into retrievable chunks for RAG.
- Splits by headers with context injection
- Handles size limits with recursive splitting
- Generates deterministic chunk IDs
- Preserves page numbers from structured extraction
- [Phase 3] Extracts image references into metadata
- [Phase 3] "Sticky Caption" logic to keep figures with their descriptions
"""

import re
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
import json

# Import for type hints (avoid circular import at runtime)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .sanitizer import PageChunk, SanitizedDocument


@dataclass
class Chunk:
    """A semantic chunk of document content."""
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    images: list[str] = field(default_factory=list)  # Phase 3: Image filenames in this chunk

    def to_dict(self) -> dict:
        """Convert chunk to dictionary for JSON serialization."""
        return asdict(self)

    @property
    def page_number(self) -> int | None:
        """Get the page number if available."""
        return self.metadata.get("page_number")

    @property
    def page_range(self) -> tuple[int, int] | None:
        """Get page range if chunk spans multiple pages."""
        start = self.metadata.get("page_start")
        end = self.metadata.get("page_end")
        if start and end:
            return (start, end)
        elif self.page_number:
            return (self.page_number, self.page_number)
        return None


# Header pattern for splitting markdown
HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Phase 3: Pattern to find images in text: ![alt](path)
IMAGE_PATTERN = re.compile(r'!\[.*?\]\((.*?)\)')

# Phase 3: Caption heuristic - "Figure X", "Fig. X", "Table X"
CAPTION_PATTERN = re.compile(r'^\s*(?:Figure|Fig\.|Table)\s*\d+', re.IGNORECASE)

# Default maximum tokens (approximate - using character count as proxy)
# ~4 chars per token is a reasonable approximation for English text
DEFAULT_MAX_CHARS = 4000  # ~1000 tokens


def generate_chunk_id(content: str, context: str) -> str:
    """
    Generate a deterministic chunk ID based on content and context.

    This ensures idempotency - same content always gets same ID.
    """
    hash_input = f"{context}::{content}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def extract_headers(text: str) -> list[tuple[int, int, int, str]]:
    """
    Extract all headers from markdown text.

    Returns:
        List of (start_pos, end_pos, level, title) tuples
    """
    headers = []
    for match in HEADER_PATTERN.finditer(text):
        level = len(match.group(1))  # Number of # symbols
        title = match.group(2).strip()
        headers.append((match.start(), match.end(), level, title))
    return headers


def build_header_hierarchy(headers: list[tuple[int, int, int, str]], current_idx: int) -> str:
    """
    Build the header hierarchy path for a given header.

    Example: "Methodology > Hyperparameters"
    """
    if current_idx < 0 or current_idx >= len(headers):
        return ""

    current_level = headers[current_idx][2]
    current_title = headers[current_idx][3]

    # Walk backwards to find parent headers
    hierarchy = [current_title]
    target_level = current_level - 1

    for i in range(current_idx - 1, -1, -1):
        level = headers[i][2]
        title = headers[i][3]

        if level == target_level:
            hierarchy.insert(0, title)
            target_level -= 1

        if target_level < 1:
            break

    return " > ".join(hierarchy)


# =============================================================================
# Phase 3: Sticky Caption Functions
# =============================================================================

def extract_images_from_text(text: str) -> list[str]:
    """Return list of image filenames referenced in the text."""
    matches = IMAGE_PATTERN.findall(text)
    # Extract just the filename from the path
    return [Path(p).name for p in matches]


def split_with_sticky_captions(text: str) -> list[str]:
    """
    Split text into 'blocks' but keep Images glued to their Captions.

    This prevents figures from being separated from their descriptions.
    Returns a list of blocks (paragraphs or merged image+caption).
    """
    # First, split by double newlines to get raw paragraphs
    raw_paragraphs = re.split(r"\n\n+", text)
    merged_blocks = []

    i = 0
    while i < len(raw_paragraphs):
        current = raw_paragraphs[i].strip()
        if not current:
            i += 1
            continue

        # Check if current block is primarily an image
        is_image = bool(IMAGE_PATTERN.match(current))

        if is_image and i + 1 < len(raw_paragraphs):
            next_para = raw_paragraphs[i + 1].strip()
            # Check if next block looks like a caption
            is_caption = bool(CAPTION_PATTERN.match(next_para))

            if is_caption:
                # MERGE THEM - keep image with its caption
                merged_blocks.append(f"{current}\n\n{next_para}")
                i += 2  # Skip next paragraph
                continue

        merged_blocks.append(current)
        i += 1

    return merged_blocks


def split_blocks_into_chunks(blocks: list[str], max_chars: int) -> list[str]:
    """Recombine blocks into chunks that fit size limits."""
    chunks = []
    current_chunk = []
    current_size = 0

    for block in blocks:
        block_size = len(block)

        # If single block is huge, accept it (better than breaking a table/figure)
        if block_size > max_chars:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_size = 0
            chunks.append(block)
            continue

        if current_size + block_size + 2 > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [block]
            current_size = block_size
        else:
            current_chunk.append(block)
            current_size += block_size + 2  # +2 for \n\n

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


# =============================================================================
# Legacy: Flat Text Chunking (for backward compatibility)
# =============================================================================

def split_by_paragraphs(text: str, max_chars: int, context: str) -> list[str]:
    """
    Recursively split text by paragraphs if it exceeds max_chars.
    Each piece retains the header context.
    """
    if len(text) <= max_chars:
        return [text]

    # Use sticky caption splitting
    blocks = split_with_sticky_captions(text)
    return split_blocks_into_chunks(blocks, max_chars)


def chunk_markdown(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    source_file: str | None = None,
) -> list[Chunk]:
    """
    Split markdown text into semantic chunks.

    This is the legacy entry point for Phase 2 (The Architect).
    For page-aware chunking, use chunk_pages() instead.

    Args:
        text: The markdown text to chunk
        max_chars: Maximum characters per chunk (approximate token limit)
        source_file: Optional source filename for metadata

    Returns:
        List of Chunk objects
    """
    chunks = []
    headers = extract_headers(text)

    if not headers:
        # No headers - treat entire text as one section
        text_chunks = split_by_paragraphs(text.strip(), max_chars, "")
        for i, chunk_text in enumerate(text_chunks):
            chunk_id = generate_chunk_id(chunk_text, "")
            chunk_images = extract_images_from_text(chunk_text)
            chunks.append(Chunk(
                id=chunk_id,
                text=chunk_text,
                metadata={
                    "section": "Document",
                    "hierarchy": "",
                    "part": i + 1 if len(text_chunks) > 1 else None,
                    "source_file": source_file,
                },
                images=chunk_images,
            ))
        return chunks

    # Process each section
    for i, (start, end, level, title) in enumerate(headers):
        # Find section content (from header end to next header or end of text)
        if i + 1 < len(headers):
            next_start = headers[i + 1][0]
            section_content = text[end:next_start].strip()
        else:
            section_content = text[end:].strip()

        if not section_content:
            continue

        # Build hierarchy path
        hierarchy = build_header_hierarchy(headers, i)

        # Create context-injected text
        context_prefix = f"Section: {hierarchy}\n\n" if hierarchy else ""

        # Split if too long (with sticky captions)
        content_chunks = split_by_paragraphs(section_content, max_chars - len(context_prefix), hierarchy)

        for j, chunk_content in enumerate(content_chunks):
            full_text = f"{context_prefix}{chunk_content}"
            chunk_id = generate_chunk_id(chunk_content, hierarchy)
            chunk_images = extract_images_from_text(chunk_content)

            metadata = {
                "section": title,
                "hierarchy": hierarchy,
                "header_level": level,
                "source_file": source_file,
            }

            if len(content_chunks) > 1:
                metadata["part"] = j + 1
                metadata["total_parts"] = len(content_chunks)

            chunks.append(Chunk(
                id=chunk_id,
                text=full_text,
                metadata=metadata,
                images=chunk_images,
            ))

    return chunks


# =============================================================================
# Page-Aware Chunking (Recommended)
# =============================================================================

def chunk_pages(
    pages: list,  # list[PageChunk] - using list to avoid circular import
    max_chars: int = DEFAULT_MAX_CHARS,
    source_file: str | None = None,
) -> list[Chunk]:
    """
    Chunk page-based data with page numbers preserved.

    This is the preferred method when using page_chunks=True extraction.
    Each chunk knows which page(s) it came from.
    Includes Phase 3 features: sticky captions and image metadata.

    Args:
        pages: List of PageChunk objects from sanitizer
        max_chars: Maximum characters per chunk
        source_file: Optional source filename for metadata

    Returns:
        List of Chunk objects with page number metadata
    """
    chunks = []

    # Track current header hierarchy across pages
    current_hierarchy = []

    for page in pages:
        # Skip reference pages (they're handled separately)
        if page.metadata.get("is_references", False):
            continue

        page_num = page.page_number
        text = page.text

        if not text.strip():
            continue

        # Extract headers from this page
        headers = extract_headers(text)

        if not headers:
            # No headers on this page - use accumulated context
            hierarchy_str = " > ".join(current_hierarchy) if current_hierarchy else ""
            context_prefix = f"Section: {hierarchy_str}\n\n" if hierarchy_str else ""

            # Phase 3: Split with sticky captions
            blocks = split_with_sticky_captions(text.strip())
            text_chunks = split_blocks_into_chunks(blocks, max_chars - len(context_prefix))

            for i, chunk_text in enumerate(text_chunks):
                full_text = f"{context_prefix}{chunk_text}"
                chunk_id = generate_chunk_id(chunk_text, f"page_{page_num}")
                chunk_images = extract_images_from_text(chunk_text)

                metadata = {
                    "section": current_hierarchy[-1] if current_hierarchy else "Document",
                    "hierarchy": hierarchy_str,
                    "page_number": page_num,
                    "source_file": source_file,
                }

                if len(text_chunks) > 1:
                    metadata["part"] = i + 1
                    metadata["total_parts"] = len(text_chunks)

                chunks.append(Chunk(
                    id=chunk_id,
                    text=full_text,
                    metadata=metadata,
                    images=chunk_images,
                ))
        else:
            # Process sections within this page
            for i, (start, end, level, title) in enumerate(headers):
                # Update hierarchy
                # Remove headers at same or deeper level
                while current_hierarchy and len(current_hierarchy) >= level:
                    current_hierarchy.pop()
                current_hierarchy.append(title)

                # Find section content
                if i + 1 < len(headers):
                    next_start = headers[i + 1][0]
                    section_content = text[end:next_start].strip()
                else:
                    section_content = text[end:].strip()

                if not section_content:
                    continue

                # Build hierarchy string
                hierarchy_str = " > ".join(current_hierarchy)
                context_prefix = f"Section: {hierarchy_str}\n\n" if hierarchy_str else ""

                # Phase 3: Split with sticky captions
                blocks = split_with_sticky_captions(section_content)
                content_chunks = split_blocks_into_chunks(blocks, max_chars - len(context_prefix))

                for j, chunk_content in enumerate(content_chunks):
                    full_text = f"{context_prefix}{chunk_content}"
                    chunk_id = generate_chunk_id(chunk_content, hierarchy_str)
                    chunk_images = extract_images_from_text(chunk_content)

                    metadata = {
                        "section": title,
                        "hierarchy": hierarchy_str,
                        "header_level": level,
                        "page_number": page_num,
                        "source_file": source_file,
                    }

                    if len(content_chunks) > 1:
                        metadata["part"] = j + 1
                        metadata["total_parts"] = len(content_chunks)

                    chunks.append(Chunk(
                        id=chunk_id,
                        text=full_text,
                        metadata=metadata,
                        images=chunk_images,
                    ))

    return chunks


# =============================================================================
# I/O Functions
# =============================================================================

def save_chunks(
    chunks: list[Chunk],
    output_path: str | Path,
) -> Path:
    """
    Save chunks to a JSON file.

    Args:
        chunks: List of Chunk objects
        output_path: Path to save the JSON file

    Returns:
        The output path
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    chunks_data = [chunk.to_dict() for chunk in chunks]
    output_path.write_text(
        json.dumps(chunks_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return output_path


def load_chunks(input_path: str | Path) -> list[Chunk]:
    """
    Load chunks from a JSON file.

    Args:
        input_path: Path to the JSON file

    Returns:
        List of Chunk objects
    """
    input_path = Path(input_path)
    data = json.loads(input_path.read_text(encoding="utf-8"))

    return [
        Chunk(
            id=item["id"],
            text=item["text"],
            metadata=item.get("metadata", {}),
            images=item.get("images", []),
        )
        for item in data
    ]


def process_markdown_file(
    markdown_path: str | Path,
    output_dir: str | Path | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[list[Chunk], Path | None]:
    """
    Full pipeline: read markdown file and chunk it.

    Args:
        markdown_path: Path to the markdown file
        output_dir: Optional directory to save chunks JSON
        max_chars: Maximum characters per chunk

    Returns:
        Tuple of (chunks, output_path or None)
    """
    markdown_path = Path(markdown_path)
    text = markdown_path.read_text(encoding="utf-8")

    chunks = chunk_markdown(
        text,
        max_chars=max_chars,
        source_file=markdown_path.name,
    )

    output_path = None
    if output_dir:
        output_dir = Path(output_dir)
        output_path = output_dir / f"{markdown_path.stem}_chunks.json"
        save_chunks(chunks, output_path)

    return chunks, output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python chunker.py <markdown_path> [output_dir]")
        sys.exit(1)

    markdown_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./output"

    print(f"Processing: {markdown_path}")
    chunks, output_path = process_markdown_file(markdown_path, output_dir)

    print(f"Generated {len(chunks)} chunks")
    if output_path:
        print(f"Saved to: {output_path}")

    # Print summary
    for i, chunk in enumerate(chunks[:5]):
        section = chunk.metadata.get('section', 'N/A')
        images = chunk.images
        print(f"\n--- Chunk {i+1} ({section}) ---")
        print(f"Images: {images if images else 'None'}")
        print(chunk.text[:150] + "..." if len(chunk.text) > 150 else chunk.text)

    if len(chunks) > 5:
        print(f"\n... and {len(chunks) - 5} more chunks")
