# Changelog

All notable changes to `doc2md` are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/).

## [0.5.0] — 2026-04-17

### Added
- **`.tex` support** via a new `LatexConverter`. LaTeX is the best
  math notation for LLMs, so it is kept as-is rather than converted
  to Markdown. Key features:
  - Sub-files (without `\documentclass`) are auto-detected and
    skipped, so `\input{}`-ed chapters don't appear twice.
  - Multi-file projects are flattened via `latexpand --expand-bbl`
    when the binary is on `PATH` (ships with TeX Live), inlining all
    `\input{}`, `\include{}`, and compiled bibliography into one
    self-contained `.tex` stream.
  - Graceful fallback: if `latexpand` is not installed, the raw
    `main.tex` is used.
  - Output is wrapped in a ` ```latex ` fenced code block.
- `README.md` gains a dedicated *LaTeX projects* section.

## [0.4.0] — 2026-04-15

### Added
- **`.epub` support** via `PandocConverter`. Ebooks are routed
  through pandoc alongside `.docx` / `.odt` / `.rtf`.
- **`.md` / `.markdown` source support** via a new
  `MarkdownPassthroughConverter`. Hand-written Markdown files are
  included in the corpus verbatim.
- **`.json` / `.xml` support** via a new `StructuredTextConverter`.
  Content is wrapped in a fenced code block with the appropriate
  language hint; JSON is pretty-printed when parseable. This replaces
  markitdown's single-line flattening of these formats.

### Changed
- **Scanner now accepts an `exclude` parameter.** The pipeline passes
  the merged-corpus and manifest output paths so doc2md never picks
  up its own outputs as sources on re-runs.
- **Scanner applies a derived-markdown heuristic.** A `.md` file with
  a sibling of the same stem and a different registered extension
  (e.g. `report.md` next to `report.docx`) is treated as a doc2md
  output from a previous run and dropped from the source list.
- **Pipeline short-circuits `source == output` writes.** Hand-written
  markdown files in sibling mode are never overwritten, even under
  `--force`.
- `README.md` gains a dedicated *Markdown as a source format*
  section explaining the above.

## [0.3.0] — 2026-04-15

### Added
- **`.rtf` support** via `PandocConverter`. RTF files are routed
  through pandoc (same code path as `.docx` / `.odt`) and thus also
  benefit from LaTeX math preservation.
- **`.txt` support** via a new `PlainTextConverter` — a no-op
  passthrough that returns the file contents verbatim. No backend,
  no dependency.

### Changed
- `README.md` supported-formats table now lists `.rtf` and `.txt`.
- Package description advertises the broader format set.

## [0.2.0] — 2026-04-15

### Added
- **`PandocConverter`** — new converter that shells out to the
  `pandoc` binary for `.docx` and `.odt`. When pandoc is present on
  `PATH`, it is auto-registered as the default for these extensions,
  taking precedence over `MarkItDownConverter`.
- **Equation preservation** — pandoc converts Word equations (OMML)
  to LaTeX (`$…$`, `$$…$$`), so math survives the round-trip for
  DOCX / ODT corpora. No flag required — auto-detected at runtime.
- **`.odt` support** — added via pandoc. Only available when the
  pandoc binary is installed.

### Changed
- `README.md` documents the pandoc integration, updates the supported
  formats table, and includes a new FAQ entry on equations / math.

### Notes
- `.pptx` equations are still lost: pandoc cannot currently read
  `.pptx` as an input format.
- PDFs still go through opendataloader-pdf and do not recover
  equations. Math-OCR backends (marker, Nougat) are a future
  possibility — PRs welcome.

## [0.1.0] — 2026-04-15

### Added
- Initial release.
- `Converter` ABC with `PdfConverter` (opendataloader-pdf) and
  `MarkItDownConverter` (markitdown) covering PDF, DOCX, PPTX, XLSX,
  XLS, HTML, HTM, CSV.
- `build_corpus()` pipeline: scan → convert → optionally merge and/or
  write a manifest. Idempotent (mtime-based skip), per-file error
  isolation, mirrored or sibling output layouts.
- Merged corpus files ship with a rich header: metadata block, usage
  note, table of contents with one-line teasers, and stable `[NN]`
  document IDs.
- Standalone `--manifest` mode for a browsable corpus directory.
- `doc2md` CLI installed via `pyproject.toml` entry point.
