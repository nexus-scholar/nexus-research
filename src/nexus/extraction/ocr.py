"""Lightweight OCR utilities for PDF page text extraction."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

import pymupdf


def _resolve_tesseract_cmd() -> str | None:
    env_path = os.getenv("TESSERACT_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    which_path = shutil.which("tesseract")
    if which_path:
        return which_path

    # Common Windows install locations
    candidates = [
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


def _resolve_tessdata_dir(cmd_path: str | None) -> str | None:
    env_path = os.getenv("TESSDATA_PREFIX")
    if env_path and Path(env_path).exists():
        return env_path

    # Project-local tessdata (repo/data/tessdata)
    try:
        repo_root = Path(__file__).resolve().parents[3]
        candidate = repo_root / "data" / "tessdata"
        if candidate.exists():
            return str(candidate)
    except Exception:
        pass

    if cmd_path:
        tessdata = Path(cmd_path).parent / "tessdata"
        if tessdata.exists():
            return str(tessdata)

    return None


def tesseract_available() -> bool:
    """Return True if tesseract is available."""
    return _resolve_tesseract_cmd() is not None


def _render_page_to_png(page: pymupdf.Page, dpi: int) -> Path:
    """Render a page to a temporary PNG and return the path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    pix = page.get_pixmap(dpi=dpi)
    pix.save(str(tmp_path))
    return tmp_path


def _ocr_with_tesseract(
    image_path: Path,
    *,
    lang: str = "eng",
    psm: int = 3,
    oem: int = 1,
    dpi: int | None = None,
    timeout: int = 60,
) -> str:
    """Run tesseract on a single image and return extracted text."""
    cmd_path = _resolve_tesseract_cmd()
    if not cmd_path:
        raise RuntimeError(
            "Tesseract OCR is not installed or not on PATH. "
            "Install it and ensure `tesseract` is available."
        )

    cmd = [cmd_path, str(image_path), "stdout", "-l", lang, "--oem", str(oem), "--psm", str(psm)]
    if dpi:
        cmd.extend(["--dpi", str(dpi)])

    env = os.environ.copy()
    if "TESSDATA_PREFIX" not in env:
        tessdata_dir = _resolve_tessdata_dir(cmd_path)
        if tessdata_dir:
            env["TESSDATA_PREFIX"] = tessdata_dir

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
        env=env,
    )
    return result.stdout


def ocr_page_text(
    page: pymupdf.Page,
    *,
    engine: str = "tesseract",
    lang: str = "eng",
    dpi: int = 300,
    timeout: int = 60,
) -> str:
    """OCR a page to text using the configured engine."""
    image_path = _render_page_to_png(page, dpi)
    try:
        if engine == "tesseract":
            return _ocr_with_tesseract(image_path, lang=lang, dpi=dpi, timeout=timeout)
        raise ValueError(f"Unsupported OCR engine: {engine}")
    finally:
        try:
            image_path.unlink()
        except Exception:
            pass


def detect_ocr_pages(raw_chunks: Iterable[dict], min_chars: int = 200) -> set[int]:
    """Detect pages that should use OCR based on low extracted text volume."""
    pages = set()
    for i, chunk in enumerate(raw_chunks):
        text = (chunk.get("text") or "").strip()
        if len(text) < min_chars:
            metadata = chunk.get("metadata", {}) or {}
            page_idx = metadata.get("page", i)
            pages.add(page_idx)
    return pages


def apply_ocr_to_chunks(
    doc: pymupdf.Document,
    raw_chunks: list[dict],
    *,
    ocr_pages: set[int],
    engine: str = "tesseract",
    lang: str = "eng",
    dpi: int = 300,
    timeout: int = 60,
) -> list[dict]:
    """Replace text in raw_chunks for pages flagged for OCR."""
    for i, chunk in enumerate(raw_chunks):
        metadata = chunk.get("metadata", {}) or {}
        page_idx = metadata.get("page", i)
        if page_idx in ocr_pages:
            try:
                ocr_text = ocr_page_text(
                    doc[page_idx],
                    engine=engine,
                    lang=lang,
                    dpi=dpi,
                    timeout=timeout,
                )
                chunk["text"] = ocr_text.strip()
                metadata["ocr_used"] = True
            except Exception as e:
                metadata["ocr_used"] = False
                metadata["ocr_error"] = str(e)
        else:
            metadata["ocr_used"] = False
        chunk["metadata"] = metadata
    return raw_chunks
