"""
Complete PDF Processing Pipeline

Combines all phases:
- Phase 1 (Sanitizer): PDF to page-based Markdown
- Phase 2 (Architect): Semantic chunking with page numbers
- Phase 3 (Visionary): Image extraction and filtering
- Phase 4 (Translator): Math/equation extraction from vector paths
- Phase 5 (Librarian): Citation resolution
- Phase 9 (Cartographer): Table extraction and parsing
"""

from pathlib import Path
from dataclasses import dataclass, field
import json

from .sanitizer import sanitize_pdf, save_sanitized_document, PageChunk
from .chunker import chunk_pages, chunk_markdown, save_chunks, Chunk
from .librarian import (
    build_reference_library,
    inject_citations_into_chunks,
    save_reference_library,
    ReferenceLibrary,
    extract_citation_numbers,
)
from .translator import (
    extract_math_from_pdf,
    group_math_by_page,
)
from .table_extractor import (
    extract_tables_from_pdf,
    save_tables,
    tables_to_chunks,
    TableExtractionResult,
)


@dataclass
class ProcessedDocument:
    """Complete result of processing a PDF document."""
    source_path: Path
    body_text: str
    references: str
    chunks: list[Chunk]
    pages: list[PageChunk] = field(default_factory=list)
    total_pages: int = 0
    output_dir: Path | None = None
    image_dir: Path | None = None  # Phase 3: Directory containing extracted images
    math_dir: Path | None = None   # Phase 4: Directory containing math images
    reference_library: ReferenceLibrary | None = None  # Phase 5: Parsed references
    math_metadata: list[dict] = field(default_factory=list)  # Phase 4: Math extraction info
    table_results: TableExtractionResult | None = None  # Phase 9: Extracted tables

    @property
    def body_page_count(self) -> int:
        """Number of body content pages."""
        return sum(1 for p in self.pages if not p.metadata.get("is_references", False))

    @property
    def reference_page_count(self) -> int:
        """Number of reference pages."""
        return sum(1 for p in self.pages if p.metadata.get("is_references", False))

    @property
    def image_count(self) -> int:
        """Number of extracted images (after filtering)."""
        if self.image_dir and self.image_dir.exists():
            return len(list(self.image_dir.glob("*")))
        return 0

    @property
    def math_count(self) -> int:
        """Number of extracted math/equation images."""
        return len(self.math_metadata)

    @property
    def table_count(self) -> int:
        """Number of extracted tables."""
        if self.table_results:
            return len(self.table_results.tables)
        return 0

    @property
    def chunks_with_images(self) -> list[Chunk]:
        """Get chunks that contain image references."""
        return [c for c in self.chunks if c.images]

    @property
    def chunks_with_math(self) -> list[Chunk]:
        """Get chunks that have potential math regions."""
        return [c for c in self.chunks if c.metadata.get("potential_math")]

    @property
    def chunks_with_tables(self) -> list[Chunk]:
        """Get chunks that have table content."""
        return [c for c in self.chunks if c.metadata.get("type") == "table"]

    @property
    def citation_count(self) -> int:
        """Number of unique citations found in chunks."""
        all_citations = set()
        for chunk in self.chunks:
            all_citations.update(extract_citation_numbers(chunk.text))
        return len(all_citations)

    @property
    def resolved_citation_count(self) -> int:
        """Number of citations that were resolved to references."""
        if not self.reference_library:
            return 0
        return len(self.reference_library)


def process_pdf_to_chunks(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    max_chunk_chars: int = 4000,
    save_intermediate: bool = True,
    extract_images: bool = True,   # Phase 3
    use_page_chunks: bool = True,
    resolve_citations: bool = True, # Phase 5
    extract_math: bool = True,      # Phase 4
    extract_tables: bool = True,    # Phase 9
) -> ProcessedDocument:
    """
    Process a PDF through the complete pipeline.

    Phase 1: Sanitize PDF to structured page-based Markdown
    Phase 2: Chunk pages into semantic pieces with page numbers
    Phase 3: Extract and filter images, link to chunks
    Phase 4: Extract math/equations from vector paths
    Phase 5: Parse references and inject citation metadata
    Phase 9: Extract and parse tables

    Args:
        pdf_path: Path to the PDF file
        output_dir: Optional directory to save all output files
        max_chunk_chars: Maximum characters per chunk
        save_intermediate: Whether to save intermediate .md files
        extract_images: Whether to extract images (Phase 3)
        use_page_chunks: Use page-based chunking (recommended, preserves page numbers)
        resolve_citations: Whether to parse references and link citations (Phase 5)
        extract_math: Whether to extract math/equations from vector paths (Phase 4)
        extract_tables: Whether to extract and parse tables (Phase 9)

    Returns:
        ProcessedDocument with all results
    """
    pdf_path = Path(pdf_path)

    # Setup directories
    image_dir = None
    math_dir = None
    if output_dir:
        output_dir = Path(output_dir)
        if extract_images:
            image_dir = output_dir / "images" / pdf_path.stem
        if extract_math:
            math_dir = output_dir / "math" / pdf_path.stem

    # Phase 1: Sanitize (extracts images if requested)
    sanitized = sanitize_pdf(pdf_path, image_output_dir=image_dir)

    # Phase 4: Translator (Math/Equation Extraction)
    # Uses Margin Guard + Stamp Detector to filter logos/watermarks
    math_metadata = []
    if extract_math and math_dir:
        math_metadata = extract_math_from_pdf(pdf_path, math_dir)

    # Phase 2 & 3: Chunk using appropriate method (with sticky captions)
    if use_page_chunks:
        chunks = chunk_pages(
            sanitized.body_pages,
            max_chars=max_chunk_chars,
            source_file=pdf_path.name,
        )
    else:
        chunks = chunk_markdown(
            sanitized.body_text,
            max_chars=max_chunk_chars,
            source_file=pdf_path.name,
        )

    # Phase 4 Continued: Link math to chunks by page number
    if math_metadata:
        math_by_page = group_math_by_page(math_metadata)

        # Attach math metadata to chunks on the same page
        for chunk in chunks:
            page = chunk.metadata.get("page_number")
            if page and page in math_by_page:
                chunk.metadata["potential_math"] = math_by_page[page]
                
                # OPTIONAL: Append math text to chunk text for better retrieval?
                # For now, we just keep it in metadata to avoid messing up the flow.
                # But we could do: chunk.text += " " + " ".join(m.get("text", "") for m in math_by_page[page])

    # Phase 5: Build reference library and inject citations
    reference_library = None
    if resolve_citations and sanitized.references:
        reference_library = build_reference_library(
            sanitized.references,
            source_file=pdf_path.name
        )

        # Inject citation metadata into chunks
        if len(reference_library) > 0:
            chunks_as_dicts = [c.to_dict() for c in chunks]
            chunks_with_citations = inject_citations_into_chunks(chunks_as_dicts, reference_library)

            # Reconstruct Chunk objects with citations
            chunks = [
                Chunk(
                    id=c["id"],
                    text=c["text"],
                    metadata={**c["metadata"], "citations": c.get("citations", {})},
                    images=c.get("images", []),
                )
                for c in chunks_with_citations
            ]

    # Phase 9: Table Extraction (The Cartographer)
    table_results = None
    if extract_tables:
        try:
            # Smart Strategy + Rotation Detection is now default in extract_tables_from_pdf
            # because we updated it to call extract_tables_from_page (Smart)
            table_results = extract_tables_from_pdf(pdf_path, find_captions=True)

            if table_results.tables:
                # Create table chunks and add to main chunks list
                table_chunks_data = tables_to_chunks(table_results)

                for tc in table_chunks_data:
                    table_chunk = Chunk(
                        id=tc["id"],
                        text=tc["text"],
                        metadata=tc["metadata"],
                        images=[],
                    )
                    chunks.append(table_chunk)

                # Also link tables to text chunks on the same page
                tables_by_page = {}
                for table in table_results.tables:
                    if table.page_number not in tables_by_page:
                        tables_by_page[table.page_number] = []
                    
                    # Include improved metadata
                    caption_text = table.caption
                    # Check for rotation flag in caption or metadata if we added it
                    
                    tables_by_page[table.page_number].append({
                        "table_id": table.table_id,
                        "caption": caption_text,
                        "row_count": table.row_count,
                        "col_count": table.col_count,
                        "headers": table.headers  # Add headers for context
                    })

                # Attach table metadata to text chunks on the same page
                for chunk in chunks:
                    if chunk.metadata.get("type") != "table":
                        page = chunk.metadata.get("page_number")
                        if page and page in tables_by_page:
                            chunk.metadata["tables_on_page"] = tables_by_page[page]

        except Exception as e:
            print(f"Warning: Table extraction failed: {e}")
            table_results = None

    # Save outputs if requested
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if save_intermediate:
            save_sanitized_document(sanitized, output_dir)

            # Save reference library if we have one
            if reference_library and len(reference_library) > 0:
                refs_json_path = output_dir / f"{pdf_path.stem}_references.json"
                save_reference_library(reference_library, refs_json_path)

            # Save math metadata if we have any
            if math_metadata:
                math_json_path = output_dir / f"{pdf_path.stem}_math.json"
                math_json_path.write_text(
                    json.dumps(math_metadata, indent=2),
                    encoding="utf-8"
                )

            # Save table data if we have any (Phase 9)
            if table_results and table_results.tables:
                save_tables(
                    table_results,
                    output_dir,
                    formats=["json", "markdown"]
                )

        # Always save chunks
        chunks_path = output_dir / f"{pdf_path.stem}_chunks.json"
        save_chunks(chunks, chunks_path)

    return ProcessedDocument(
        source_path=pdf_path,
        body_text=sanitized.body_text,
        references=sanitized.references,
        chunks=chunks,
        pages=sanitized.pages,
        total_pages=sanitized.total_pages,
        output_dir=output_dir,
        image_dir=sanitized.image_dir,
        math_dir=math_dir,
        reference_library=reference_library,
        math_metadata=math_metadata,
        table_results=table_results,
    )


def process_directory(
    input_dir: str | Path,
    output_dir: str | Path,
    max_chunk_chars: int = 4000,
    save_intermediate: bool = True,
    extract_images: bool = True,
    resolve_citations: bool = True,
    extract_math: bool = True,
    extract_tables: bool = True,
) -> list[ProcessedDocument]:
    """
    Process all PDFs in a directory.

    Args:
        input_dir: Directory containing PDF files
        output_dir: Directory to save all output files
        max_chunk_chars: Maximum characters per chunk
        save_intermediate: Whether to save intermediate markdown files
        extract_images: Whether to extract images (Phase 3)
        resolve_citations: Whether to parse references and link citations (Phase 5)
        extract_math: Whether to extract math/equations (Phase 4)
        extract_tables: Whether to extract and parse tables (Phase 9)

    Returns:
        List of ProcessedDocument results
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    pdf_files = list(input_dir.glob("*.pdf"))
    results = []

    for pdf_path in pdf_files:
        print(f"Processing: {pdf_path.name}")
        try:
            result = process_pdf_to_chunks(
                pdf_path,
                output_dir=output_dir,
                max_chunk_chars=max_chunk_chars,
                save_intermediate=save_intermediate,
                extract_images=extract_images,
                resolve_citations=resolve_citations,
                extract_math=extract_math,
                extract_tables=extract_tables,
            )
            results.append(result)

            # Enhanced output with all phase info
            extras = []
            if extract_images:
                extras.append(f"{result.image_count} imgs")
            if extract_math:
                extras.append(f"{result.math_count} math")
            if resolve_citations:
                extras.append(f"{result.resolved_citation_count} refs")
            if extract_tables:
                extras.append(f"{result.table_count} tables")

            extras_str = ", ".join(extras)
            print(f"  OK: {len(result.chunks)} chunks, {extras_str}")

        except Exception as e:
            print(f"  ERROR: {e}")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <pdf_path_or_dir> [output_dir]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./output"

    if input_path.is_dir():
        print(f"Processing directory: {input_path}")
        results = process_directory(input_path, output_dir)
        print(f"\nProcessed {len(results)} PDFs")
        total_chunks = sum(len(r.chunks) for r in results)
        total_images = sum(r.image_count for r in results)
        total_math = sum(r.math_count for r in results)
        print(f"Total chunks: {total_chunks}")
        print(f"Total images: {total_images}")
        print(f"Total math regions: {total_math}")
    else:
        print(f"Processing: {input_path}")
        result = process_pdf_to_chunks(input_path, output_dir)
        print(f"Generated {len(result.chunks)} chunks")
        print(f"Extracted {result.image_count} images")
        print(f"Extracted {result.math_count} math regions")

        # Show chunks with math
        chunks_with_math = result.chunks_with_math
        if chunks_with_math:
            print(f"\nChunks with math: {len(chunks_with_math)}")
            for c in chunks_with_math[:3]:
                math_info = c.metadata.get("potential_math", [])
                print(f"  Page {c.page_number}: {len(math_info)} math region(s)")

        print(f"\nOutput saved to: {output_dir}")
