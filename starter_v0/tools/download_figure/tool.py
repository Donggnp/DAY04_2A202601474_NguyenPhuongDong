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

# How far a table's row blocks may extend from its caption before we treat
# the page as having moved on to unrelated body text (points, PDF space).
TABLE_ROW_GAP_LIMIT = 28.0
TABLE_MAX_HEIGHT = 360.0
TABLE_TOP_PAD = 6.0
TABLE_BOTTOM_PAD = 12.0
# Minimum horizontal overlap (as a fraction of the narrower block's width)
# for a block to be considered "the same column" as the caption. Two-column
# layouts put unrelated body text at the same y-range as a table in the
# other column, so a pure y-sort walk would otherwise wander across columns.
MIN_COLUMN_OVERLAP = 0.35
# Below this gap (points), trust block adjacency over content when deciding
# whether a block is still part of the table — see _is_table_boundary.
PROSE_SKIP_GAP = 10.0
# A block counting >= this many hits from _PROSE_STOPWORDS is treated as a
# resumed body paragraph, not another table row, regardless of how small its
# vertical gap to the previous block is — LaTeX's paragraph spacing can be as
# tight as inter-row spacing, so gap distance alone can't tell them apart.
PROSE_STOPWORD_HITS = 3
PROSE_STOPWORDS = {
    "the", "and", "of", "in", "is", "are", "with", "for", "this", "that",
    "we", "our", "to", "as", "on", "by", "from", "which", "these", "was",
    "were", "have", "has", "at", "it", "its", "an", "be", "such",
}
FIRST_PERSON_MARKERS = {"we", "our", "us"}

# Punctuation right after the number is required, not optional: a real
# caption is always "Table 1: ..." / "Table 1. ...", while a sentence like
# "Table 1 shows results for..." also starts with "Table 1" but is regular
# prose referencing the table, not the caption itself.
FIGURE_CAPTION_RE = re.compile(r"^(?:figure|fig\.?)\s*\d+(?:\.\d+)?\s*[:.\-]\s*", re.IGNORECASE)
TABLE_CAPTION_RE = re.compile(r"\btable\s+\d+(?:\.\d+)?\s*[:.\-]\s*(.{0,%d})" % CAPTION_SNIPPET_CHARS, re.IGNORECASE)

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


def _is_caption_text(text: str) -> bool:
    return bool(TABLE_CAPTION_RE.match(text) or FIGURE_CAPTION_RE.match(text))


def _is_prose(text: str) -> bool:
    stripped = text.strip()
    words = re.findall(r"[a-z]+", stripped.lower())
    hits = sum(1 for word in words if word in PROSE_STOPWORDS)
    if hits >= PROSE_STOPWORD_HITS:
        return True
    # A short sentence ("Ablation studies can be found in Appendix C.") may
    # not clear the stopword bar on its own, but real sentence-final
    # punctuation is itself a strong prose signal that table cells almost
    # never produce, so accept a lower bar when it's present.
    return stripped.endswith((".", ".\"", ".'")) and hits >= 2


def _has_first_person(text: str) -> bool:
    # Papers describe their own work as "we"/"our" in body prose; table and
    # figure content (numbers, model names, metadata labels, even
    # full-sentence qualitative examples describing a *model's* output)
    # essentially never does. Unlike the stopword/period checks in
    # _is_prose, this holds regardless of how tight the block spacing is, so
    # it's checked unconditionally instead of being gated by PROSE_SKIP_GAP.
    words = re.findall(r"[a-z]+", text.lower())
    return any(word in FIRST_PERSON_MARKERS for word in words)


def _is_table_boundary(text: str, gap: float) -> bool:
    if _is_caption_text(text) or _has_first_person(text):
        return True
    # A qualitative "examples"/metadata table can have full-sentence cell
    # content (e.g. RAG's "Examples from generation tasks"), which the prose
    # check above would otherwise flag as body text and stop on immediately.
    # When the gap to the previous block is tight, trust position over
    # content — real body paragraphs practically never sit this close to
    # the previous element, so only run the content check in the ambiguous
    # gap range where spacing alone can't decide.
    if gap <= PROSE_SKIP_GAP:
        return False
    return _is_prose(text)


def _h_overlap_frac(a: tuple[float, float], b: tuple[float, float]) -> float:
    overlap = min(a[1], b[1]) - max(a[0], b[0])
    if overlap <= 0:
        return 0.0
    narrower = min(a[1] - a[0], b[1] - b[0])
    return overlap / narrower if narrower > 0 else 0.0


def _table_region(page: Any) -> tuple[str, tuple[float, float, float, float]] | None:
    all_blocks = [block for block in page.get_text("blocks") if (block[4] or "").strip()]

    caption_block = None
    caption_text: str | None = None
    for block in all_blocks:
        text = block[4].strip()
        # Anchor to the start of a text block, like _caption_below does for
        # figures — a bare substring search would also match inline
        # references such as "(see table 3)" inside running prose.
        if TABLE_CAPTION_RE.match(text):
            caption_block = block
            caption_text = text.replace("\n", " ")
            break
    if caption_block is None or caption_text is None:
        return None

    cap_x = (caption_block[0], caption_block[2])
    # Restrict to blocks that plausibly sit in the same column as the
    # caption, then sort by top-y so the walk below proceeds in visual
    # reading order (raw block order follows the PDF content stream, not
    # layout, and mixes columns at the same y-range otherwise).
    column = [b for b in all_blocks if _h_overlap_frac(cap_x, (b[0], b[2])) >= MIN_COLUMN_OVERLAP]
    column.sort(key=lambda b: b[1])
    idx = column.index(caption_block)

    included = [caption_block]
    below_boundary = page.rect.y1
    above_boundary = page.rect.y0

    # Some papers caption a table like a figure (caption below the table)
    # instead of the usual caption-above-table convention. Decide the
    # direction *before* walking, from whichever side sits closer to the
    # caption — walking "below" first and only falling back to "above" when
    # it finds nothing is not good enough: axis labels/legend text from an
    # unrelated chart sitting right after the caption are non-prose too, so
    # a naive "did below find anything" check would happily walk into a
    # figure instead of the real table sitting on the other side.
    below_gap = (column[idx + 1][1] - caption_block[3]) if idx + 1 < len(column) else float("inf")
    above_gap = (caption_block[1] - column[idx - 1][3]) if idx > 0 else float("inf")

    if below_gap <= above_gap:
        below_bottom = caption_block[3]
        for block in column[idx + 1:]:
            gap = block[1] - below_bottom
            if _is_table_boundary(block[4].strip(), gap):
                below_boundary = block[1]
                break
            if gap > TABLE_ROW_GAP_LIMIT or (block[3] - caption_block[1]) > TABLE_MAX_HEIGHT:
                below_boundary = block[1]
                break
            included.append(block)
            below_bottom = block[3]
    else:
        above_top = caption_block[1]
        for block in reversed(column[:idx]):
            gap = above_top - block[3]
            if _is_table_boundary(block[4].strip(), gap):
                above_boundary = block[3]
                break
            if gap > TABLE_ROW_GAP_LIMIT or (caption_block[3] - block[1]) > TABLE_MAX_HEIGHT:
                above_boundary = block[3]
                break
            included.append(block)
            above_top = block[1]

    x0 = min(block[0] for block in included)
    y0 = min(block[1] for block in included)
    x1 = max(block[2] for block in included)
    y1 = max(block[3] for block in included)

    page_rect = page.rect
    crop = (
        max(page_rect.x0, x0 - TABLE_TOP_PAD),
        max(page_rect.y0, y0 - TABLE_TOP_PAD, above_boundary),
        min(page_rect.x1, x1 + TABLE_TOP_PAD),
        min(page_rect.y1, y1 + TABLE_BOTTOM_PAD, below_boundary),
    )
    return caption_text, crop


def _table_page_candidates(doc: Any, page_index: int) -> list[dict[str, Any]]:
    page = doc[page_index]
    region = _table_region(page)
    if region is None:
        return []
    caption, crop = region
    # A cropped table region is quantitative data by construction — classify
    # by caption keywords only for embedded figures, where it actually
    # distinguishes an architecture diagram from a results plot. Doing the
    # same here would mislabel e.g. "Table 3: Variations on the Transformer
    # architecture" as `method` just because "architecture" appears in prose,
    # even though the table itself is an ablation/results table.
    return [{
        "kind": "table_crop",
        "page": page_index + 1,
        "caption": caption[:CAPTION_SNIPPET_CHARS],
        "label": "results",
        "area": 0,
        "crop": crop,
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
                clip = fitz.Rect(*candidate["crop"])
                pixmap = page.get_pixmap(matrix=matrix, clip=clip)
                out_path = out_dir / f"p{candidate['page']}_table_crop.png"
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
