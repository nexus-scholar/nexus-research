"""
Phase 4: The Translator (Math & Layout Recovery)

Detects and extracts visual elements that standard text parsing misses:
- Mathematical formulas (rendered as vector paths)
- Complex tables (rendered as drawing commands)
- Diagrams constructed from lines/curves

Strategy:
1. Scan page for vector drawings (paths).
2. Group nearby paths into 'Equation Candidates'.
3. Filter out candidates that overlap with known images.
4. Apply Margin Guard (exclude header/footer zones).
5. Apply Stamp Detector (exclude repetitive elements across pages).
6. Extract these regions as screenshots.
"""

import io
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz


# =============================================================================
# Configuration Constants
# =============================================================================

# Margin Guard: Exclude top/bottom X% of page (headers, footers, logos)
MARGIN_TOP_PERCENT = 0.08      # Top 8% of page
MARGIN_BOTTOM_PERCENT = 0.05   # Bottom 5% of page

# Stamp Detector: If a region appears at same coords on N+ pages, it's a logo
STAMP_REPETITION_THRESHOLD = 3  # Must appear on 3+ pages to be a "stamp"
STAMP_POSITION_TOLERANCE = 10   # Pixels tolerance for position matching


@dataclass
class VisualCandidate:
    """A detected visual region (Math/Table) on a page."""
    page_number: int
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    type: str = "equation_candidate"
    text_content: str = ""  # Text captured inside or near the graphic

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def y_center(self) -> float:
        """Vertical center for matching to text."""
        return (self.bbox[1] + self.bbox[3]) / 2

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "bbox": list(self.bbox),
            "type": self.type,
            "width": self.width,
            "height": self.height,
            "text": self.text_content,
        }


def boxes_intersect(box1: tuple, box2: tuple, tolerance: float = 2) -> bool:
    """Check if two rectangles intersect (with tolerance)."""
    x0_1, y0_1, x1_1, y1_1 = box1
    x0_2, y0_2, x1_2, y1_2 = box2

    return not (x1_1 < x0_2 - tolerance or
                x0_1 > x1_2 + tolerance or
                y1_1 < y0_2 - tolerance or
                y0_1 > y1_2 + tolerance)


def merge_boxes(boxes: list[tuple], x_tol: float = 20, y_tol: float = 10) -> list[tuple]:
    """
    Cluster nearby bounding boxes into larger regions.
    Used to group individual math symbols into a full equation.

    Math equations are often rendered as many small vector paths
    (each symbol, fraction line, etc.). This merges them.
    """
    if not boxes:
        return []

    # Make a copy to avoid mutating input
    boxes = list(boxes)

    # Sort by Y then X
    boxes.sort(key=lambda b: (b[1], b[0]))

    merged = []
    while boxes:
        current = boxes.pop(0)
        curr_x0, curr_y0, curr_x1, curr_y1 = current

        changed = True
        while changed:
            changed = False
            rest = []
            for other in boxes:
                o_x0, o_y0, o_x1, o_y1 = other

                # Check for proximity/overlap
                # Vertical overlap or close proximity
                vertical_close = (o_y0 <= curr_y1 + y_tol) and (o_y1 >= curr_y0 - y_tol)
                horizontal_close = (o_x0 <= curr_x1 + x_tol) and (o_x1 >= curr_x0 - x_tol)

                if vertical_close and horizontal_close:
                    # Merge the boxes
                    curr_x0 = min(curr_x0, o_x0)
                    curr_y0 = min(curr_y0, o_y0)
                    curr_x1 = max(curr_x1, o_x1)
                    curr_y1 = max(curr_y1, o_y1)
                    changed = True
                else:
                    rest.append(other)
            boxes = rest

        merged.append((curr_x0, curr_y0, curr_x1, curr_y1))

    return merged


def extract_equation_candidates(
    doc: fitz.Document,
    page_index: int,
    known_image_bboxes: list[tuple] | None = None,
    min_paths_threshold: int = 5,
    apply_margin_guard: bool = True,
) -> list[VisualCandidate]:
    """
    Find regions on the page that contain vector graphics but aren't standard images.

    These are typically mathematical equations rendered as paths/curves.

    Args:
        doc: PyMuPDF document
        page_index: 0-indexed page number
        known_image_bboxes: Bounding boxes of known images to exclude
        min_paths_threshold: Minimum number of paths in a region to consider it
        apply_margin_guard: Whether to exclude header/footer zones

    Returns:
        List of VisualCandidate objects
    """
    page = doc[page_index]

    try:
        paths = page.get_drawings()
    except Exception:
        return []

    if not paths:
        return []

    # Calculate margin zones (Margin Guard)
    page_w, page_h = page.rect.width, page.rect.height
    margin_top = page_h * MARGIN_TOP_PERCENT
    margin_bottom = page_h * (1 - MARGIN_BOTTOM_PERCENT)

    # 1. Get bbox of every drawing path
    path_boxes = []
    for item in paths:
        rect = item.get("rect")
        if rect:
            path_boxes.append(tuple(rect))

    if not path_boxes:
        return []

    # 2. Filter out page-sized borders or tiny dots
    clean_boxes = []
    for box in path_boxes:
        w = box[2] - box[0]
        h = box[3] - box[1]

        # Ignore full page borders
        if w > page_w * 0.9 or h > page_h * 0.9:
            continue
        # Ignore tiny noise (single pixels, dots)
        if w < 3 and h < 3:
            continue

        clean_boxes.append(box)

    if len(clean_boxes) < min_paths_threshold:
        # Not enough paths to form meaningful equations
        return []

    # 3. Merge individual paths into coherent regions
    merged_regions = merge_boxes(clean_boxes)

    # 4. Filter against known images (Phase 3 outputs) to avoid duplicates
    final_candidates = []
    if known_image_bboxes is None:
        known_image_bboxes = []

    for box in merged_regions:
        # Check intersection with known images
        is_known_image = False
        for img_box in known_image_bboxes:
            if boxes_intersect(box, img_box):
                is_known_image = True
                break

        if is_known_image:
            continue

        # Calculate dimensions
        w = box[2] - box[0]
        h = box[3] - box[1]
        y_center = (box[1] + box[3]) / 2

        # Filter 5: Margin Guard - exclude header/footer zones
        if apply_margin_guard:
            # Check if center of region is in margin zones
            if y_center < margin_top or y_center > margin_bottom:
                continue

        # Filter 6: Sanity checks for equation-like regions
        # Must be at least somewhat visible
        if w < 15 or h < 8:
            continue

        # Drop very small regions (likely icons)
        if (w * h) < 1200:
            continue

        # Equations are usually wider than tall (fractions can be taller)
        # Very tall narrow regions are likely decorative lines
        aspect = w / h if h > 0 else 0
        if aspect < 0.3 and h > 100:
            # Likely a vertical line/border
            continue

        # Very wide thin regions are likely horizontal rules
        if aspect > 20 and h < 5:
            continue
            
        # Feature B: Text-Graphic Fusion
        # Check for text inside or overlapping with the box
        # Expand box slightly to catch subscripts/superscripts
        search_rect = fitz.Rect(box[0]-2, box[1]-2, box[2]+2, box[3]+2)
        text_content = page.get_text("text", clip=search_rect).strip()
        
        # Clean up text (remove excessive whitespace)
        text_content = " ".join(text_content.split())

        if text_content and not _looks_like_math_text(text_content):
            # Skip decorative or header-like text regions
            continue

        final_candidates.append(VisualCandidate(
            page_number=page_index + 1,  # 1-indexed for consistency
            bbox=box,
            type="equation_or_diagram",
            text_content=text_content
        ))

    return final_candidates


def save_candidates(
    doc: fitz.Document,
    candidates: list[VisualCandidate],
    output_dir: Path,
    dpi: int = 300,
    padding: int = 5,
    ocr_latex: bool = False,
    latex_ocr_engine: str = "pix2tex",
    drop_invalid_latex: bool = True,
) -> list[dict]:
    """
    Save the candidate regions as high-resolution images.

    Args:
        doc: PyMuPDF document
        candidates: List of VisualCandidate objects
        output_dir: Directory to save images
        dpi: Resolution for rendering
        padding: Pixels to add around the region

    Returns:
        List of metadata dicts for each saved image
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_list = []

    for i, cand in enumerate(candidates):
        page = doc[cand.page_number - 1]

        # Add padding around the region
        rect = fitz.Rect(
            cand.bbox[0] - padding,
            cand.bbox[1] - padding,
            cand.bbox[2] + padding,
            cand.bbox[3] + padding
        )

        # Clip to page bounds
        rect = rect & page.rect

        if rect.is_empty:
            continue

        # Render at high resolution
        try:
            pix = page.get_pixmap(clip=rect, dpi=dpi)
        except Exception:
            continue

        # Generate filename
        filename = f"math_p{cand.page_number}_{i:02d}.png"
        save_path = output_dir / filename

        try:
            pix.save(str(save_path))
        except Exception:
            continue

        metadata = {
            "filename": filename,
            "page": cand.page_number,
            "bbox": list(cand.bbox),
            "type": cand.type,
            "width": cand.width,
            "height": cand.height,
        }

        if ocr_latex:
            try:
                latex = latex_ocr_from_pixmap(pix, engine=latex_ocr_engine)
                if latex and _looks_like_latex_math(latex):
                    metadata["latex"] = latex
                else:
                    metadata["latex_invalid"] = True
                    if drop_invalid_latex:
                        continue
            except Exception as e:
                metadata["latex_error"] = str(e)
                if drop_invalid_latex:
                    continue

        metadata_list.append(metadata)

    return metadata_list


def extract_math_from_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    known_image_bboxes_by_page: dict[int, list[tuple]] | None = None,
    ocr_latex: bool = False,
    latex_ocr_engine: str = "pix2tex",
) -> list[dict]:
    """
    Extract all equation candidates from a PDF.

    Applies two-pass filtering:
    1. Per-page extraction with Margin Guard
    2. Cross-page Stamp Detection (removes repetitive logos/watermarks)

    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save math images
        known_image_bboxes_by_page: Dict mapping page numbers to known image bboxes

    Returns:
        List of metadata dicts for all extracted math regions
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    if known_image_bboxes_by_page is None:
        known_image_bboxes_by_page = {}

    if ocr_latex:
        _ensure_latex_ocr_available(latex_ocr_engine)

    doc = fitz.open(str(pdf_path))

    try:
        # Pass 1: Collect all candidates from all pages
        all_candidates: list[VisualCandidate] = []

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            known_bboxes = known_image_bboxes_by_page.get(page_num, [])

            candidates = extract_equation_candidates(
                doc,
                page_idx,
                known_image_bboxes=known_bboxes,
                apply_margin_guard=True,
            )
            all_candidates.extend(candidates)

        # Pass 2: Stamp Detector - remove repetitive elements
        filtered_candidates = filter_stamps(all_candidates)

        # Pass 3: Save filtered candidates
        all_metadata = []
        if filtered_candidates:
            all_metadata = save_candidates(
                doc,
                filtered_candidates,
                output_dir,
                ocr_latex=ocr_latex,
                latex_ocr_engine=latex_ocr_engine,
                drop_invalid_latex=True,
            )

    finally:
        doc.close()

    return all_metadata


_LATEX_OCR = None


def _ensure_latex_ocr_available(engine: str) -> None:
    if engine != "pix2tex":
        raise ValueError(f"Unsupported LaTeX OCR engine: {engine}")
    try:
        from pix2tex.cli import LatexOCR  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "LaTeX OCR engine not available. Install pix2tex and pillow. "
            "Example: pip install pix2tex pillow"
        ) from e


def latex_ocr_from_pixmap(pix: fitz.Pixmap, engine: str = "pix2tex") -> str:
    """Convert a rendered pixmap to LaTeX using a local OCR engine."""
    if engine != "pix2tex":
        raise ValueError(f"Unsupported LaTeX OCR engine: {engine}")

    try:
        from pix2tex.cli import LatexOCR
    except Exception as e:
        raise RuntimeError(
            "LaTeX OCR engine not available. Install pix2tex and pillow. "
            "Example: pip install pix2tex pillow"
        ) from e

    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            "Pillow is required for LaTeX OCR. Install with: pip install pillow"
        ) from e

    global _LATEX_OCR
    if _LATEX_OCR is None:
        _LATEX_OCR = LatexOCR()

    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return str(_LATEX_OCR(image)).strip()


def _looks_like_math_text(text: str) -> bool:
    """Heuristic to reject header/logo text from math candidates."""
    if not text:
        return False

    if re.search(r"[=<>±+\-×*/^_]", text):
        return True
    if re.search(r"[∑∏∫√≈≤≥]", text):
        return True
    if re.search(r"[\u0370-\u03FF]", text):
        return True  # Greek
    if re.search(r"\d", text) and re.search(r"[()\[\]]", text):
        return True
    if re.fullmatch(r"[A-Za-z\s]{6,}", text):
        return False
    return bool(re.search(r"\d", text))


def _looks_like_latex_math(latex: str) -> bool:
    latex = latex.strip()
    if len(latex) < 2:
        return False
    if len(latex) > 500:
        return False

    has_digit = bool(re.search(r"\d", latex))
    has_operator = bool(re.search(r"[=<>±+\-*/^_]", latex))

    common_cmds = (
        "\\frac",
        "\\sum",
        "\\int",
        "\\sqrt",
        "\\alpha",
        "\\beta",
        "\\gamma",
        "\\delta",
        "\\theta",
        "\\lambda",
        "\\mu",
        "\\nu",
        "\\pi",
        "\\rho",
        "\\sigma",
        "\\tau",
        "\\phi",
        "\\psi",
        "\\omega",
        "\\cdot",
        "\\times",
        "\\mathbb",
        "\\mathbf",
        "\\mathrm",
    )
    has_common = any(cmd in latex for cmd in common_cmds)

    if has_common and (has_digit or has_operator):
        return True
    if has_common and not (has_digit or has_operator):
        if latex.count("\\mathrm") >= 2:
            return False

    if has_digit and (has_operator or "\\cdot" in latex or "\\times" in latex):
        return True

    letters = re.findall(r"[A-Za-z]", latex)
    nonspace = re.findall(r"[^\s]", latex)
    if nonspace:
        if (len(letters) / len(nonspace)) > 0.8 and not (has_digit or has_operator):
            return False

    return has_operator or has_digit


def filter_stamps(candidates: list[VisualCandidate]) -> list[VisualCandidate]:
    """
    Stamp Detector: Remove vector elements that appear at same position across multiple pages.

    Logic: Equations are unique; logos/watermarks are repetitive.
    If a region appears at the same coordinates on N+ pages, it's a stamp.

    Args:
        candidates: List of all candidates from all pages

    Returns:
        Filtered list with stamps removed
    """
    if len(candidates) < STAMP_REPETITION_THRESHOLD:
        return candidates

    # Group candidates by approximate position (ignoring page number)
    # Key: (x0_rounded, y0_rounded, x1_rounded, y1_rounded)
    position_counts: dict[tuple, list[VisualCandidate]] = defaultdict(list)

    for cand in candidates:
        # Round to nearest tolerance increment for grouping
        key = (
            round(cand.bbox[0] / STAMP_POSITION_TOLERANCE) * STAMP_POSITION_TOLERANCE,
            round(cand.bbox[1] / STAMP_POSITION_TOLERANCE) * STAMP_POSITION_TOLERANCE,
            round(cand.bbox[2] / STAMP_POSITION_TOLERANCE) * STAMP_POSITION_TOLERANCE,
            round(cand.bbox[3] / STAMP_POSITION_TOLERANCE) * STAMP_POSITION_TOLERANCE,
        )
        position_counts[key].append(cand)

    # Find stamp positions (appear on 3+ different pages)
    stamp_positions = set()
    for key, cands in position_counts.items():
        # Count unique pages
        unique_pages = set(c.page_number for c in cands)
        if len(unique_pages) >= STAMP_REPETITION_THRESHOLD:
            stamp_positions.add(key)

    # Filter out stamps
    filtered = []
    for cand in candidates:
        key = (
            round(cand.bbox[0] / STAMP_POSITION_TOLERANCE) * STAMP_POSITION_TOLERANCE,
            round(cand.bbox[1] / STAMP_POSITION_TOLERANCE) * STAMP_POSITION_TOLERANCE,
            round(cand.bbox[2] / STAMP_POSITION_TOLERANCE) * STAMP_POSITION_TOLERANCE,
            round(cand.bbox[3] / STAMP_POSITION_TOLERANCE) * STAMP_POSITION_TOLERANCE,
        )
        if key not in stamp_positions:
            filtered.append(cand)

    return filtered


def group_math_by_page(math_metadata: list[dict]) -> dict[int, list[dict]]:
    """Group math metadata by page number."""
    by_page = {}
    for m in math_metadata:
        p = m.get("page", 0)
        if p not in by_page:
            by_page[p] = []
        by_page[p].append(m)
    return by_page


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python translator.py <pdf_path> [output_dir]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./output/math"

    print(f"Scanning for equations: {pdf_path}")
    metadata = extract_math_from_pdf(pdf_path, output_dir)

    print(f"Found {len(metadata)} equation candidates")
    for m in metadata[:5]:
        print(f"  Page {m['page']}: {m['filename']} ({m['width']:.0f}x{m['height']:.0f})")

    if len(metadata) > 5:
        print(f"  ... and {len(metadata) - 5} more")
