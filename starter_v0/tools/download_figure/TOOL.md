---
name: download_figure
track: core
kind: live_api_plus_local_extract
provider: arXiv + PyMuPDF
requires_env: [ARXIV_USER_AGENT]
inputs: [arxiv_url, max_images, dpi]
outputs: [items, output_dir, page_count, candidates_found]
side_effect: local_file_write
---
# download_figure

`paper_text` extracts the PDF as plain text via `pypdf`, which loses figures
and mangles tables (numbers/columns turn into a flat character stream). This
tool extracts the *visual* evidence instead, so a multimodal model (e.g.
GPT-4o) can read Table 1 / a results chart directly.

To keep multimodal token cost low, this is a **rank-and-cap** pipeline, not a
"dump everything" extractor — it returns at most 4 images per call.

1. **Candidate discovery**, over every page:
   - Embedded raster images (min 200x200px) that have a `Figure N: ...`
     caption text block directly below them (matched via bbox distance, not
     just page proximity). Images with no matching caption are dropped —
     this filters out logos, icons, and the individual sub-tiles of a
     composite figure that don't carry their own caption.
   - Pages whose text contains a `Table N` caption are kept as a
     **cropped table region**, not a full-page render (tables are vector/text
     drawings, not embedded images, so pass 1 alone would miss them). The
     crop is computed from real text-block geometry: sort the page's text
     blocks top-to-bottom, start at the caption block, and keep absorbing
     the next blocks as table rows as long as the vertical gap between them
     stays under 28pt and the accumulated height stays under 320pt — the
     first block that breaks either condition is body prose resuming, so the
     region stops there. This keeps the rendered image to just the caption +
     table instead of an entire A4 page with unrelated paragraphs, which was
     wasting multimodal tokens and diluting what the model actually needed
     to read.
2. **Dedupe** candidates that resolve to the same caption text, keeping the
   largest one (handles composite figures made of several embedded xrefs).
3. **Label + rank**: each caption is keyword-classified as `results`
   (performance/comparison/accuracy/benchmark/sota/ablation/evaluation/score)
   or `method` (overview/architecture/framework/pipeline/proposed
   method/system design); anything else is `other`. Table candidates default
   to `results` even without a keyword hit, since tables are inherently
   quantitative. Candidates are sorted `results` > `method` > `other`, and
   only the top `max_images` (hard cap 4) are actually rendered to disk.

Reuses the PDF already cached by `paper_text` under `starter_v0/arxiv_papers/`
when present, instead of re-downloading. Output PNGs go to
`starter_v0/arxiv_papers/<arxiv_id>/figures/`. Each returned item includes its
`caption` and `label` so the caller/model knows what it's looking at without
having to re-derive it.

`items[*].image_path` is a local file path, not a URL — the caller (UI/agent)
is responsible for attaching it to a multimodal call or displaying it.
