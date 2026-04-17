# doc2md

> **Point it at a folder. Get clean Markdown.**  
> A small, well-behaved tool for turning a directory of mixed documents
> (PDF, DOCX, ODT, RTF, EPUB, PPTX, XLSX, HTML, CSV, TXT, LaTeX,
> Markdown, JSON, XML) into Markdown that's ready to feed to an LLM — a Gemini
> Gem, a Claude Project, a RAG pipeline, or just your own reading
> list.

## Why

Modern LLMs are good at reading, but only if you hand them clean text.
A typical knowledge base is the opposite: a folder tree full of PDFs,
Word docs, spreadsheets, slide decks, and the occasional HTML export —
each with its own extraction quirks, each opaque to anything that
expects plain text. Feeding that directly into a chatbot gets you
garbled tables, stripped equations, lost structure, and an agent that
confidently cites things that aren't there.

The fix is boring but effective: convert everything to Markdown first,
once, and feed the model that. Markdown is the lingua franca of
modern LLMs — short, structured, token-efficient, citation-friendly,
and lossless enough for the vast majority of document content.
`doc2md` does that conversion for a whole folder in one command,
preserves equations as LaTeX when pandoc is available, and emits a
single merged corpus file with a built-in table of contents and
stable `[NN]` document IDs so the model can cite sources back to you
unambiguously. You upload one file to your Gem, Project, or RAG
index, and the model gets the whole corpus with provenance intact.

## What it produces

`doc2md` scans a folder, converts every supported document to Markdown,
and can additionally produce:

- a **merged corpus file** — one big `.md` with a header, table of
  contents, and per-document sections carrying stable `[NN]` IDs so an
  LLM can cite sources precisely;
- a **manifest** — a standalone directory file that lists every
  converted document with links to its individual `.md`.

You pick: individual files, merged corpus, manifest, or any combination.

---

## Features

- **One command, one folder** — `doc2md ./papers` and you're done.
- **Multi-format** — PDF, DOCX, ODT, RTF, EPUB, PPTX, XLSX, XLS, HTML,
  HTM, CSV, TXT, LaTeX, Markdown, JSON, XML out of the box; easily
  extensible.
- **Equation-aware** — install [pandoc](https://pandoc.org) and DOCX/ODT
  equations are preserved as LaTeX (`$…$`, `$$…$$`) instead of being
  silently dropped. Auto-detected at runtime; no flags required.
- **LLM-aware output** — the merged file comes with a generated header
  that tells the model how to cite documents (`[NN] filename`), a table
  of contents with one-line teasers, and per-document metadata blocks.
- **Idempotent** — re-running skips sources whose `.md` is already
  up-to-date. `--force` rebuilds everything.
- **Resilient** — one bad document doesn't kill the batch; failures are
  logged and reported at the end.
- **Lazy backends** — a missing optional dependency only fails if its
  format actually appears in your folder.
- **Small and readable** — a single package, ~600 lines, easy to audit
  or extend.

---

## Install

`doc2md` is not on PyPI yet. Install it directly from GitHub:

```bash
pip install git+https://github.com/giulioruffini/doc2md.git
```

Or clone and install in editable mode if you want to hack on it:

```bash
git clone https://github.com/giulioruffini/doc2md.git
cd doc2md
pip install -e .
```

Either way you end up with a `doc2md` command on your `PATH`. Run
`doc2md --help` to confirm.

> 💡 Install into a virtualenv, not your system Python:
> ```bash
> python3 -m venv ~/venvs/doc2md
> source ~/venvs/doc2md/bin/activate
> pip install git+https://github.com/giulioruffini/doc2md.git
> ```

Requires Python 3.10+. Installs two backends:

- [`markitdown`](https://github.com/microsoft/markitdown) — for DOCX,
  PPTX, XLSX, XLS, HTML, CSV.
- [`opendataloader-pdf`](https://pypi.org/project/opendataloader-pdf/) —
  for PDFs (higher-quality extraction than markitdown's built-in PDF
  path).

### Optional: pandoc (strongly recommended for DOCX / ODT)

If the [`pandoc`](https://pandoc.org) binary is present on your
``PATH``, doc2md automatically uses it for ``.docx`` and ``.odt``
instead of markitdown. Pandoc:

- **preserves Word equations as LaTeX** (``$…$`` and ``$$…$$``),
- produces cleaner headings, tables, lists, and blockquotes,
- adds support for ``.odt`` (LibreOffice / OpenOffice).

Install it once and forget about it:

```bash
# macOS
brew install pandoc
# Debian / Ubuntu
sudo apt install pandoc
# Windows
winget install --id JohnMacFarlane.Pandoc
```

No Python dependency is added — doc2md just shells out to the binary.
If pandoc isn't installed, ``.docx`` silently falls back to markitdown
and ``.odt`` is skipped.

> 💡 If you keep your documents inside a cloud-sync folder (Google Drive,
> Dropbox, iCloud…), create your virtualenv **outside** of it. Cloud
> sync tends to strip executable bits and mangle interpreter symlinks,
> which silently breaks virtualenvs.

---

## Quick start

```bash
# Per-document .md next to every source, plus a merged corpus and a manifest:
doc2md ./papers \
    --merged ./papers/papers_corpus.md \
    --manifest ./papers/INDEX.md

# Only the merged file, no per-document clutter:
doc2md ./papers \
    --merged ./papers/papers_corpus.md \
    --no-individual

# Mirror all outputs into a separate build directory:
doc2md ./papers \
    --output-dir build/papers-md \
    --merged build/papers_corpus.md \
    --manifest build/papers-md/INDEX.md

# Run doc2md over every subfolder that looks like a source directory:
for dir in *-sources; do
    doc2md "$dir" \
        --merged "$dir/${dir}_corpus.md" \
        --manifest "$dir/INDEX.md"
done
```

---

## CLI reference

```
doc2md [-h] [--merged PATH] [--manifest PATH] [--no-individual]
       [--output-dir DIR] [--no-recursive] [--force] [-v]
       root
```

| Flag | Meaning |
| --- | --- |
| `root` | Folder to scan (positional). |
| `--merged PATH` | Also write a single merged Markdown file at `PATH` (header + TOC + `[NN]` per-document sections). |
| `--manifest PATH` | Also write a standalone directory file (header + TOC linking to the individual `.md` files). Requires per-document files. |
| `--no-individual` | Don't keep per-document `.md` files. Requires `--merged`. |
| `--output-dir DIR` | Mirror per-document `.md` files under `DIR` instead of writing them next to sources. |
| `--no-recursive` | Only scan the top-level of `root`. |
| `--force` | Re-convert files even if an up-to-date `.md` already exists. |
| `-v, --verbose` | DEBUG-level logging. |

---

## Python API

```python
from pathlib import Path
from doc2md import build_corpus

result = build_corpus(
    root=Path("papers"),
    merged_output=Path("papers/papers_corpus.md"),
    manifest_output=Path("papers/INDEX.md"),
)

print(result.converted)     # [Path, ...]  per-document .md files written
print(result.skipped)       # sources already up-to-date
print(result.failed)        # [(Path, error_message), ...]
print(result.merged_path)   # Path | None
print(result.manifest_path) # Path | None
```

---

## What the merged file looks like

Every merged corpus file starts with a small preamble designed for LLM
consumption:

```markdown
# Corpus: papers

- **Generated:** 2026-04-15 13:24 UTC
- **Source root:** `papers`
- **Documents:** 42
- **Total source size:** 58.3 MB

## How to use this corpus

This file is a concatenation of documents converted from PDF/DOCX to
Markdown for LLM ingest. Each document has a stable numeric ID of the
form `[NN]`. When citing a document in an answer, reference it as
`[NN] <filename>`. The table of contents below maps every ID to a
`## [NN] ...` heading further down in the file.

## Table of contents

1. **`[01]`** [`chapter_01.pdf`](#doc-01) — 1.9 MB · pdf — _Introduction to..._
2. **`[02]`** [`chapter_02.docx`](#doc-02) — 320 KB · docx — _Background and related work_
...

---

## <a id="doc-01"></a>[01] chapter_01.pdf

**Source:** `chapter_01.pdf`  
**Format:** pdf · **Size:** 1.9 MB

<document body here>
```

The per-document `[NN]` IDs are stable across a run, so an LLM can cite
them and a human can grep for them. Anchors (`#doc-NN`) make the TOC
clickable in any Markdown viewer.

The manifest file uses the same header + TOC vocabulary, but its TOC
links point at the actual `.md` files on disk (paths relative to the
manifest's own location), so you can drop `INDEX.md` next to your
output directory and browse the corpus like a folder.

---

## LaTeX projects

LaTeX is the gold-standard notation for mathematics, and modern LLMs
read it natively. Converting LaTeX to Markdown would *lose*
information (custom environments, theorem numbering, cross-references,
fine-grained math markup), so doc2md deliberately keeps `.tex` content
as-is, wrapped in a ` ```latex ` fenced code block for clean embedding
inside the merged corpus.

**Multi-file projects.** A typical LaTeX project is split across a
`main.tex`, several `\input{}`-ed chapter files, and a
`\bibliography{refs}`. doc2md handles this automatically:

- **Sub-file detection:** any `.tex` file that does *not* contain
  `\documentclass` is assumed to be a chapter or section included by
  a parent. It is returned empty (the merger skips empty documents),
  so it never appears twice in the corpus.
- **Project flattening:** when [`latexpand`](https://ctan.org/pkg/latexpand)
  is on your `PATH` (it ships with TeX Live), doc2md uses it to
  inline all `\input{}`, `\include{}`, and the compiled bibliography
  (`.bbl`) into one self-contained `.tex` stream. The LLM gets the
  entire paper in a single section — equations, proofs, references
  and all.
- **Graceful fallback:** if `latexpand` is not installed, the raw
  `main.tex` is used. The LLM still sees the document structure but
  `\input{}` references remain unresolved.

```bash
# Install latexpand (included in TeX Live):
# macOS
brew install --cask mactex   # or: brew install texlive
# Debian / Ubuntu
sudo apt install texlive-extra-utils
```

**Bibliography tip:** `latexpand --expand-bbl` inlines the `.bbl`
file, which only exists after a BibTeX / Biber run. If you haven't
compiled your `.tex` project, the bibliography won't be inlined. For
best results, compile once (`pdflatex` + `bibtex` / `biber`) before
running doc2md, so the `.bbl` is fresh.

## Markdown as a source format

Treating `.md` / `.markdown` as a source format needs one subtlety:
doc2md writes its own output as `.md` files alongside the sources, so a
naive scan would pick up those outputs and feed them back into the next
run as sources. To avoid that, the scanner applies two guards:

1. **Explicit output exclusion.** The merged corpus file and the
   manifest file are excluded from the scan by path, so the merge of a
   folder never contains itself (even when `--merged` points inside
   `root`).
2. **Derived-markdown heuristic.** If a `.md` file has a sibling with
   the same stem and a different, registered extension (e.g.
   `report.md` next to `report.docx`), the `.md` is assumed to be a
   doc2md output from a previous run and is dropped from the source
   list. A hand-written `.md` without such a sibling — e.g. a
   `notes.md` on its own, or a `README.md` — is included normally.

When `.md` *is* a source and its resolved output path equals the
source path (sibling mode, no `.md` backend conversion needed), the
pipeline short-circuits the read/write round-trip entirely. Even under
`--force`, doc2md will not overwrite an authentic markdown source with
a copy of itself.

If this heuristic gets in your way — say, you really do keep a
hand-written `notes.md` next to `notes.pdf` — use `--output-dir` to
mirror outputs into a separate directory. That eliminates the
ambiguity: inputs and outputs no longer share a parent folder, so
every `.md` in `root` is unambiguously a source.

## Architecture

> For a full design walkthrough — module responsibilities, data flow,
> extension points, invariants, and known trade-offs — see
> **[ARCHITECTURE.md](ARCHITECTURE.md)**.

```
doc2md/
├── scanner.py      # discover source files under a root
├── converters.py   # Converter ABC + MarkItDown/Pandoc/Pdf/PlainText/Markdown/StructuredText + registry
├── merger.py       # header, TOC, per-document sections, manifest writer
├── pipeline.py     # build_corpus() orchestration + BuildResult
└── cli.py          # argparse entry (installed as the `doc2md` script)
```

The pipeline is deliberately split so each piece is independently
testable and replaceable:

- **`scanner.scan()`** — returns source paths, filters Word lockfiles
  (`~$...`) and dotfiles.
- **`converters.Converter`** — ABC. Each subclass declares its
  `extensions` and implements `convert(source) -> str`. Backends are
  imported lazily inside `__init__`, so a missing optional dependency
  only fails if that format actually appears in the folder. A single
  converter can handle multiple extensions (one shared backend
  instance).
- **`merger.merge()` / `write_manifest()`** — corpus-level writers.
  Both share the same header and TOC vocabulary so downstream LLMs see
  a consistent structure.
- **`pipeline.build_corpus()`** — glues the three together, handles
  idempotency (mtime check), output layout (sibling vs. mirrored vs.
  ephemeral), and per-file error isolation (one bad file doesn't kill
  the batch).

---

## Extending: add a new format

Say you want to support `.epub`:

```python
# doc2md/converters.py
class EpubConverter(Converter):
    extensions = (".epub",)

    def __init__(self) -> None:
        from ebooklib import epub
        # ... set up your backend here
        self._backend = epub

    def convert(self, source: Path) -> str:
        # ... return markdown text
        ...

_register(DEFAULT_CONVERTERS, EpubConverter)
```

Or reuse `MarkItDownConverter` — it already handles several formats
through a single backend, and adding an extension to its `extensions`
tuple is enough if markitdown supports the format natively.

`scanner.scan()` and `pipeline.build_corpus()` pick up the new
extension automatically from the registry.

---

## Supported formats

| Extension | Backend (default) | Notes |
| --- | --- | --- |
| `.pdf` | opendataloader-pdf | Uses PDF structural tree when available; high-quality layout extraction. |
| `.docx` | pandoc (fallback: markitdown) | Pandoc preserves equations as LaTeX and produces cleaner output. |
| `.odt`  | pandoc | Only available when pandoc is installed. |
| `.rtf`  | pandoc | Only available when pandoc is installed. |
| `.epub` | pandoc | Only available when pandoc is installed. |
| `.pptx` | markitdown | Pandoc cannot currently read `.pptx`; equations in slides are lost. |
| `.xlsx`, `.xls` | markitdown | |
| `.html`, `.htm` | markitdown | |
| `.csv`  | markitdown | |
| `.tex`  | latexpand + passthrough | LaTeX is already the best math notation for LLMs — it's kept as-is, not converted. Multi-file projects are flattened via `latexpand` when available; sub-files (without `\documentclass`) are auto-skipped. See [LaTeX projects](#latex-projects). |
| `.txt`  | passthrough | Returned verbatim; no parsing. |
| `.md`, `.markdown` | passthrough | Hand-written markdown is copied verbatim. See the [Markdown sources](#markdown-as-a-source-format) section for how doc2md avoids picking up its own outputs. |
| `.json` | structured-text | Pretty-printed when valid JSON, then wrapped in a ` ```json ` fenced code block. |
| `.xml`  | structured-text | Wrapped verbatim in a ` ```xml ` fenced code block. |

Need another format? See [Extending](#extending-add-a-new-format).

---

## FAQ

**Can I use it from Python without the CLI?**  
Yes — `from doc2md import build_corpus`. See the Python API section.

**What happens to files doc2md can't convert?**  
They're listed in `BuildResult.failed` with the error message. The rest
of the batch continues. Exit code is non-zero if anything failed.

**Does it re-convert files every time?**  
No. Re-runs are idempotent: a source is skipped if a `.md` already
exists and is newer than the source. Use `--force` to rebuild.

**Can I run it over many folders at once?**  
Yes — wrap it in a shell loop (see Quick start).

**What about equations and math?**  
For **DOCX / ODT**, install [pandoc](https://pandoc.org) and doc2md will
auto-use it — equations are preserved as LaTeX (`$…$`, `$$…$$`). For
**PDFs**, the current pipeline does not recover equations (PDF math is
rendered as glyphs or bitmaps, which plain-text extractors can't
recover reliably). If you need LaTeX math out of academic PDFs,
consider running a dedicated math-OCR tool like
[marker](https://github.com/datalab-to/marker) or
[Nougat](https://github.com/facebookresearch/nougat) on the raw PDF
first; PR welcome to add an alternative `PdfConverter` backed by one
of these.

**Does the merged file include the individual `.md` files, or read them
from disk?**  
It reads the individual `.md` files that were just written. So the
merged file is always consistent with the per-document outputs.

---

## Contributing

Issues and PRs welcome. Keep the scope tight: `doc2md` aims to be a
small, legible tool, not a kitchen-sink document processor. If you want
to add a format, a single clean converter + a note in this README is
the ideal PR.

```bash
git clone https://github.com/giulioruffini/doc2md.git
cd doc2md
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

---

## License

MIT — see [LICENSE](LICENSE).
