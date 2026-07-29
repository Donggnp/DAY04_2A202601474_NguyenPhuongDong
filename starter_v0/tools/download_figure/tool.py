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

MIN_EMBEDDED_IMAGE_SIDE = 200
MAX_IMAGES_CAP = 4
CAPTION_MAX_GAP = 120  # points; how far below the image a caption line may sit
CAPTION_SNIPPET_CHARS = 160

FIGURE_CAPTION_RE = re.compile(r"^(?:figure|fig\.?)\s*\d+\s*[:.\-]?\s*", re.IGNORECASE)
TABLE_CAPTION_RE = re.compile(r"\btable\s+\d+\s*[:.\-]?\s*(.{0,%d})" % CAPTION_SNIPPET_CHARS, re.IGNORECASE)

# Priority 0 = kept first when trimming down to MAX_IMAGES_CAP.
RESULT_KEYWORDS = (
    "performance", "comparison", "results", "accuracy", "benchmark",
    "sota", "state-of-the-art", "ablation", "evaluation", "score",
)
METHOD_KEYWORDS = (
    "overview", "architecture", "framework", "proposed method",
    "pipeline", "model structure", "proposed approach", "system design",
)
LABEL_PRIORITY = {"results": 0, "method": 1, "other": 2}


def _classify_caption(caption: str) -> str:
    folded = caption.lower()
    if any(keyword in folded for keyword in RESULT_KEYWORDS):
        return "results"
    if any(keyword in folded for keyword in METHOD_KEYWORDS):
        return "method"
    return "other"


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


def _caption_below(page: Any, rect: Any) -> str | None:
    best_text: str | None = None
    best_gap = CAPTION_MAX_GAP
    for block in page.get_text("blocks"):
        x0, y0, x1, text = block[0], block[1], block[2], block[4]
        text = (text or "").strip()
        if not text or not FIGURE_CAPTION_RE.match(text):
            continue
        gap = y0 - rect.y1
        overlap = min(x1, rect.x1) - max(x0, rect.x0)
        if 0 <= gap <= best_gap and overlap > 0:
            best_text = text.replace("\n", " ")
            best_gap = gap
    return best_text


def _embedded_figure_candidates(doc: Any, page_index: int) -> list[dict[str, Any]]:
    page = doc[page_index]
    candidates: list[dict[str, Any]] = []
    seen_xrefs: set[int] = set()
    for image_info in page.get_images(full=True):
        xref = image_info[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        rect = rects[0]
        if rect.width < MIN_EMBEDDED_IMAGE_SIDE or rect.height < MIN_EMBEDDED_IMAGE_SIDE:
            continue
        caption = _caption_below(page, rect)
        if not caption:
            # No "Figure N: ..." caption nearby -> likely a decorative/logo
            # image or a sub-tile of a composite figure, not a standalone result.
            continue
        candidates.append({
            "kind": "embedded_figure",
            "page": page_index + 1,
            "xref": xref,
            "caption": caption[:CAPTION_SNIPPET_CHARS],
            "label": _classify_caption(caption),
            "area": rect.width * rect.height,
        })
    return candidates


def _table_page_candidates(doc: Any, page_index: int) -> list[dict[str, Any]]:
    page = doc[page_index]
    caption: str | None = None
    for block in page.get_text("blocks"):
        text = (block[4] or "").strip()
        # Anchor to the start of a text block, like _caption_below does for
        # figures — a bare substring search would also match inline
        # references such as "(see table 3)" inside running prose.
        if text and TABLE_CAPTION_RE.match(text):
            caption = text.replace("\n", " ")
            break
    if not caption:
        return []
    # A rendered table page is quantitative data by construction — classify by
    # caption keywords only for embedded figures, where it actually
    # distinguishes an architecture diagram from a results plot. Doing the
    # same here would mislabel e.g. "Table 3: Variations on the Transformer
    # architecture" as `method` just because "architecture" appears in prose,
    # even though the table itself is an ablation/results table.
    label = "results"
    return [{
        "kind": "table_page",
        "page": page_index + 1,
        "caption": caption[:CAPTION_SNIPPET_CHARS],
        "label": label,
        "area": 0,
    }]


def _dedupe_by_caption(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_caption: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate["caption"].lower()
        current_best = best_by_caption.get(key)
        if current_best is None or candidate["area"] > current_best["area"]:
            best_by_caption[key] = candidate
    return list(best_by_caption.values())


def download_figure(arxiv_url: str = "", max_images: int = MAX_IMAGES_CAP, dpi: int = 150) -> dict[str, Any]:
    try:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise RuntimeError("Install pymupdf first: pip install pymupdf") from exc

        arxiv_id, pdf_path = _get_or_download_pdf(arxiv_url)
        max_images = max(1, min(int(max_images or MAX_IMAGES_CAP), MAX_IMAGES_CAP))
        dpi = max(72, min(int(dpi or 150), 300))
        out_dir = ARXIV_DIR / arxiv_id / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(pdf_path))
        page_count = len(doc)

        candidates: list[dict[str, Any]] = []
        for page_index in range(page_count):
            candidates.extend(_embedded_figure_candidates(doc, page_index))
            candidates.extend(_table_page_candidates(doc, page_index))
        candidates = _dedupe_by_caption(candidates)

        # Results captions first, then method-overview captions, then anything
        # else; stable sort keeps original page order within each bucket.
        candidates.sort(key=lambda item: (LABEL_PRIORITY[item["label"]], item["page"]))
        selected = candidates[:max_images]

        items: list[dict[str, Any]] = []
        for candidate in selected:
            page = doc[candidate["page"] - 1]
            if candidate["kind"] == "embedded_figure":
                pixmap = fitz.Pixmap(doc, candidate["xref"])
                if pixmap.n - pixmap.alpha >= 4:
                    pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                out_path = out_dir / f"p{candidate['page']}_fig_xref{candidate['xref']}.png"
            else:
                matrix = fitz.Matrix(dpi / 72, dpi / 72)
                pixmap = page.get_pixmap(matrix=matrix)
                out_path = out_dir / f"p{candidate['page']}_table_page.png"
            pixmap.save(str(out_path))
            items.append({
                "type": candidate["kind"],
                "label": candidate["label"],
                "page": candidate["page"],
                "caption": candidate["caption"],
                "image_path": str(out_path),
                "width": pixmap.width,
                "height": pixmap.height,
            })

        doc.close()

        return {
            "tool": "download_figure",
            "arxiv_id": arxiv_id,
            "pdf_path": str(pdf_path),
            "output_dir": str(out_dir),
            "page_count": page_count,
            "candidates_found": len(candidates),
            "item_count": len(items),
            "items": items,
            "note": (
                "Selected up to "
                f"{MAX_IMAGES_CAP} highest-value images (results captions prioritized over "
                "method/overview captions) out of "
                f"{len(candidates)} captioned candidates, to keep multimodal token cost low."
            ),
        }
    except Exception as exc:
        return err("download_figure", exc)
