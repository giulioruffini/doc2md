# Changelog

All notable changes to `doc2md` are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/).

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
