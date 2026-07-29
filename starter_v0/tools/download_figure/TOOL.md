---
name: download_figure
track: core
kind: live_api_plus_local_extract
provider: arXiv + PyMuPDF
requires_env: [ARXIV_USER_AGENT]
inputs: [arxiv_url, max_images, dpi]
outputs: [items, output_dir, page_count]
side_effect: local_file_write
---
# download_figure

`paper_text` extracts the PDF as plain text via `pypdf`, which loses figures
and mangles tables (numbers/columns turn into a flat character stream). This
tool extracts the *visual* evidence instead, so a multimodal model (e.g.
GPT-4o) can read Table 1 / a results chart directly instead of guessing from
broken text.

Two extraction passes, both capped by `max_images`:

1. **Embedded figures** — pulls raster images actually embedded in the PDF
   (plots, diagrams). Skips anything smaller than 100x100px to filter out
   logos/icons.
2. **Table pages** — pages whose text contains a `Table N` caption are
   rendered as a full-page PNG at `dpi` (default 150), since tables in
   academic PDFs are almost always vector/text drawings, not embedded images,
   so pass 1 alone would miss them.

Reuses the PDF already cached by `paper_text` under `starter_v0/arxiv_papers/`
when present, instead of re-downloading and re-hitting the arXiv rate limit.
Output PNGs are saved to `starter_v0/arxiv_papers/<arxiv_id>/figures/`.

`items[*].image_path` is a local file path, not a URL — the caller (UI/agent)
is responsible for attaching it to a multimodal call or displaying it, this
tool only prepares the files.
