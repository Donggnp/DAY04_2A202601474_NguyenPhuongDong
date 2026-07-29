from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from tools._shared import ROOT, TIMEOUT, err


ARXIV_DIR = ROOT / "arxiv_papers"
ARXIV_MIN_INTERVAL_SECONDS = 3.0
_last_arxiv_request_at = 0.0

MIN_EMBEDDED_IMAGE_SIDE = 100
TABLE_CAPTION_RE = re.compile(r"\bTable\s+\d+", re.IGNORECASE)


def _arxiv_user_agent() -> str:
    return os.getenv("ARXIV_USER_AGENT", "AI20k-Day04-Research-Agent/1.0 (educational lab; contact: local)")


def _rate_limit_arxiv() -> None:
    global _last_arxiv_request_at
    elapsed = time.monotonic() - _last_arxiv_request_at
    if elapsed < ARXIV_MIN_INTERVAL_SECONDS:
        time.sleep(ARXIV_MIN_INTERVAL_SECONDS - elapsed)
    _last_arxiv_request_at = time.monotonic()


def _arxiv_id(value: str) -> str:
    match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", value or "")
    if not match:
        raise ValueError("Invalid arXiv ID or URL")
    return match.group(1)


def _get_or_download_pdf(arxiv_url: str) -> tuple[str, Path]:
    arxiv_id = _arxiv_id(arxiv_url)
    ARXIV_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ARXIV_DIR / f"{arxiv_id}.pdf"
    if output_path.exists():
        # Reuse the PDF already cached by `paper_text` (or a previous call here)
        # instead of hitting arXiv again for the same paper.
        return arxiv_id, output_path
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    _rate_limit_arxiv()
    response = requests.get(pdf_url, headers={"User-Agent": _arxiv_user_agent()}, timeout=TIMEOUT, stream=True)
    response.raise_for_status()
    with output_path.open("wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)
    return arxiv_id, output_path


def download_figure(arxiv_url: str = "", max_images: int = 6, dpi: int = 150) -> dict[str, Any]:
    try:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise RuntimeError("Install pymupdf first: pip install pymupdf") from exc

        arxiv_id, pdf_path = _get_or_download_pdf(arxiv_url)
        max_images = max(1, min(int(max_images or 6), 20))
        dpi = max(72, min(int(dpi or 150), 300))
        out_dir = ARXIV_DIR / arxiv_id / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(pdf_path))
        items: list[dict[str, Any]] = []

        # Pass 1: embedded raster images (charts/plots/diagrams as figures).
        seen_xrefs: set[int] = set()
        for page_index in range(len(doc)):
            if len(items) >= max_images:
                break
            page = doc[page_index]
            for image_info in page.get_images(full=True):
                if len(items) >= max_images:
                    break
                xref = image_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                pixmap = fitz.Pixmap(doc, xref)
                if pixmap.width < MIN_EMBEDDED_IMAGE_SIDE or pixmap.height < MIN_EMBEDDED_IMAGE_SIDE:
                    continue
                if pixmap.n - pixmap.alpha >= 4:
                    pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                out_path = out_dir / f"p{page_index + 1}_fig_xref{xref}.png"
                pixmap.save(str(out_path))
                items.append({
                    "type": "embedded_figure",
                    "page": page_index + 1,
                    "image_path": str(out_path),
                    "width": pixmap.width,
                    "height": pixmap.height,
                })

        # Pass 2: full-page render for pages whose text mentions "Table N",
        # since tables are usually vector/text drawings, not embedded images.
        for page_index in range(len(doc)):
            if len(items) >= max_images:
                break
            page = doc[page_index]
            if not TABLE_CAPTION_RE.search(page.get_text()):
                continue
            matrix = fitz.Matrix(dpi / 72, dpi / 72)
            pixmap = page.get_pixmap(matrix=matrix)
            out_path = out_dir / f"p{page_index + 1}_table_page.png"
            pixmap.save(str(out_path))
            items.append({
                "type": "table_page",
                "page": page_index + 1,
                "image_path": str(out_path),
                "width": pixmap.width,
                "height": pixmap.height,
            })

        page_count = len(doc)
        doc.close()

        return {
            "tool": "download_figure",
            "arxiv_id": arxiv_id,
            "pdf_path": str(pdf_path),
            "output_dir": str(out_dir),
            "page_count": page_count,
            "item_count": len(items),
            "items": items,
            "note": "embedded_figure = extracted raster image; table_page = full page rendered as PNG because its text mentions 'Table N'.",
        }
    except Exception as exc:
        return err("download_figure", exc)
