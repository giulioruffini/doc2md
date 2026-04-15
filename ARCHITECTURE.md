# Architecture

This document describes how `doc2md` is put together — its modules,
their responsibilities, the data that flows between them, the design
decisions behind the shape of the code, and the invariants those
decisions rely on. It is aimed at contributors and at users who want
to understand what's happening when they type `doc2md ./folder`.

For usage documentation, see [README.md](README.md).  
For version history, see [CHANGELOG.md](CHANGELOG.md).

---

## Overview

`doc2md` exists to solve one problem cleanly: **point it at a folder
of mixed documents, get Markdown back**. The output can be a set of
per-document `.md` files, a single merged corpus file with a rich
header and table of contents, a standalone manifest that indexes the
individual files, or any combination. The main consumer is an LLM
— a Gemini Gem, a Claude Project, a RAG pipeline — and every design
choice is made with that consumer in mind.

The codebase is deliberately small (~750 LOC across six Python
modules). Every piece is replaceable. If you want to swap out the PDF
backend, you change one class. If you want to add a new format, you
write one class and register it. If you want to change how the merged
file is laid out, you edit one function in one module.

---

## Design principles

1. **One job per module.** `scanner` discovers, `converters` convert,
   `merger` assembles corpus-level artifacts, `pipeline` orchestrates,
   `cli` parses arguments. No module reaches across its neighbours.
2. **Lazy, tolerant backends.** Heavy third-party imports (markitdown,
   opendataloader-pdf) live inside converter `__init__` methods, not
   at module top level. A missing optional dependency only fails when
   its format actually appears in the folder, and the rest of the
   batch carries on.
3. **Idempotent by default.** Re-running over the same folder is
   cheap: mtime comparison skips sources whose `.md` is already
   up-to-date. `--force` rebuilds everything; nothing else does.
4. **Per-file error isolation.** One bad document must never kill a
   batch. Exceptions from a converter are caught, logged, recorded in
   `BuildResult.failed`, and the pipeline moves on.
5. **LLM-friendly outputs.** The merged corpus file is *self-describing*:
   it starts with a usage note telling the model how to cite
   documents, followed by a table of contents with stable `[NN]` IDs
   and per-document metadata blocks.
6. **Predictable filesystem behaviour.** Three output modes (sibling,
   mirrored, ephemeral), clear precedence rules, and an explicit
   guard against writing over a source file with a copy of itself.

---

## Module map

```
                           ┌──────────────┐
           CLI arguments ──▶    cli.py    │
                           └──────┬───────┘
                                  │ argparse → keyword args
                                  ▼
                           ┌──────────────┐
                           │  pipeline.py │
                           │ build_corpus │
                           └──┬───────┬───┘
                              │       │
                 scan(root)   │       │   merge / write_manifest
                              ▼       ▼
                    ┌──────────────┐  ┌──────────────┐
                    │  scanner.py  │  │   merger.py  │
                    └──────────────┘  └──────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  converters.py   │
                    │  PdfConverter    │
                    │  PandocConverter │
                    │  MarkItDown...   │
                    │  PlainText...    │
                    │  Markdown...     │
                    │  StructuredText  │
                    └────────┬─────────┘
                             │
                             ▼
                ┌──────────────────────────┐
                │  external backends       │
                │  • opendataloader-pdf    │
                │  • pandoc (subprocess)   │
                │  • markitdown            │
                └──────────────────────────┘
```

The only dependencies between internal modules are the arrows in this
diagram. Notably, `converters` and `merger` don't know about each
other; they're glued together by `pipeline`.

---

## Module walkthrough

### `scanner.py`

**Responsibility:** given a root folder and a set of registered
extensions, return a sorted list of source files.

The scanner is stateless and has no dependencies beyond `pathlib`.
It applies three filters:

1. **Extension match** (case-insensitive).
2. **Hidden / lockfile exclusion** — Word autosave files (`~$Foo.docx`)
   and dotfiles are never sources.
3. **Explicit path exclusion** — callers can pass an `exclude` set.
   The pipeline uses this to exclude the current run's merged-corpus
   and manifest output paths, so doc2md never picks up its own
   outputs as sources on re-runs.

It also applies a **derived-markdown heuristic**. When `.md` /
`.markdown` is among the registered extensions, any markdown file
with the same `(parent, stem)` as a non-markdown candidate is dropped
from the source list. Rationale: doc2md writes `foo.md` next to
`foo.docx`, so re-running would otherwise pick up its own outputs as
sources, creating a feedback loop and double-converting files. The
heuristic is intentionally simple — if two *authentic* sources happen
to share a stem across extensions (e.g. a hand-written `notes.md` and
an unrelated `notes.pdf`), `--output-dir` is the escape hatch: it
physically separates inputs from outputs, which eliminates the
ambiguity.

### `converters.py`

**Responsibility:** turn one source document into a Markdown string.

Every concrete converter implements the `Converter` ABC:

```python
class Converter(ABC):
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def convert(self, source: Path) -> str: ...
```

The contract is minimal on purpose: one method, one path in, a
Markdown string out. The converter owns any scratch directories,
subprocess calls, and backend-specific setup.

Six concrete converters ship in the box:

| Class | Extensions | Backend | Notes |
| --- | --- | --- | --- |
| `PdfConverter` | `.pdf` | opendataloader-pdf | Wraps a batch-oriented tool with a per-file scratch directory. |
| `PandocConverter` | `.docx` `.odt` `.rtf` `.epub` | pandoc binary (subprocess) | Preserves Word equations (OMML) as LaTeX. Auto-enabled when pandoc is on `PATH`. |
| `MarkItDownConverter` | `.docx` `.pptx` `.xlsx` `.xls` `.html` `.htm` `.csv` | markitdown | Fallback for `.docx` when pandoc is absent. |
| `PlainTextConverter` | `.txt` | — | Zero-dependency passthrough. |
| `MarkdownPassthroughConverter` | `.md` `.markdown` | — | Verbatim. Works in concert with the scanner's derived-markdown heuristic. |
| `StructuredTextConverter` | `.json` `.xml` | — | Wraps content in a fenced code block. JSON is pretty-printed when parseable. |

**Registration** lives in a module-level dict:

```python
DEFAULT_CONVERTERS: dict[str, type[Converter]] = {}
_register(DEFAULT_CONVERTERS, PdfConverter)
_register(DEFAULT_CONVERTERS, MarkItDownConverter)
_register(DEFAULT_CONVERTERS, PlainTextConverter)
_register(DEFAULT_CONVERTERS, StructuredTextConverter)
_register(DEFAULT_CONVERTERS, MarkdownPassthroughConverter)
if shutil.which("pandoc") is not None:
    _register(DEFAULT_CONVERTERS, PandocConverter)
```

**Precedence is controlled by insertion order.** `_register` simply
sets `mapping[ext] = cls`, so a later registration overrides an
earlier one. Pandoc is registered last, and only when the binary is
available, so it wins for `.docx` whenever possible and silently
steps aside otherwise.

Backends are imported **lazily inside `__init__`**. That means:

- `import doc2md` never triggers import of markitdown or
  opendataloader-pdf.
- If your folder has only PDFs, markitdown is never imported at all.
- If your folder has only DOCX files and pandoc is installed,
  opendataloader-pdf is never imported either.

The pipeline caches converter instances **by class, not by
extension**, so `MarkItDownConverter` pays its setup cost exactly
once per run regardless of whether the folder contains one format or
seven.

### `merger.py`

**Responsibility:** assemble corpus-level artifacts from a list of
per-document conversion results.

The core data type is a small frozen dataclass:

```python
@dataclass(frozen=True)
class MergeEntry:
    source: Path      # original .pdf / .docx / ...
    markdown: Path    # converted .md file on disk
```

The pipeline builds a `list[MergeEntry]` as it goes and hands it to
two writers:

- **`merge(entries, source_root, output, *, title)`** — writes a
  single merged Markdown file with:
  1. A metadata block (generation time, source root, document count,
     total source size).
  2. A "How to use this corpus" paragraph that tells the LLM every
     document has a stable `[NN]` ID and should be cited as
     `[NN] <filename>`.
  3. A table of contents linking to in-file anchors (`#doc-NN`),
     with one-line teasers extracted from each document body.
  4. Per-document sections headed `## <a id="doc-NN"></a>[NN] <path>`
     with their own source/format/size metadata, then the content.
- **`write_manifest(entries, source_root, output, *, title)`** —
  writes a standalone directory file using the same header + TOC
  vocabulary, but the TOC links point at the actual `.md` files on
  disk (paths are computed relative to the manifest's own location)
  instead of in-file anchors.

Both writers delegate formatting helpers — `_human_size`, `_teaser`,
`_rel`, `_fmt`, `_size`, `_header`, `_toc_sections`, `_toc_files` —
so the header and TOC look identical across the two outputs. The
teaser extractor skips empty lines, ATX headings, and code-fence
openers so structured formats (JSON/XML) still get a useful preview
pulled from inside the fence.

### `pipeline.py`

**Responsibility:** glue everything together. This is where the work
actually happens.

`build_corpus()` is the single public entry point. It:

1. Resolves *root* and validates flag combinations (`--no-individual`
   requires `--merged`; `--manifest` requires individual files).
2. Builds a lazy per-class converter cache.
3. Calls `scanner.scan(root, extensions, exclude=...)` with the
   merged/manifest output paths in `exclude`, so doc2md's own outputs
   are never treated as sources.
4. Chooses the layout root for per-document `.md` files:
   - `write_individual=True, output_dir=None` → sibling of each source
   - `write_individual=True, output_dir=DIR` → mirrored under `DIR`
   - `write_individual=False`           → ephemeral tempdir, cleaned
     up at the end (individuals are still used internally for the
     merge, then deleted)
5. For each source:
   a. Compute the output path.
   b. **Source-is-its-own-output short-circuit.** If the resolved
      output path equals the resolved source path (hand-written
      `.md` in sibling mode), skip the read/write entirely. This is
      important under `--force`: we must never overwrite an authentic
      markdown source with a copy of itself.
   c. **Idempotency check.** If the output exists and is newer than
      the source and we're not under `--force`, skip the conversion
      but still add an entry (so the merge still includes the file).
   d. **Converter lookup + convert.** `ImportError` (missing backend)
      and any other exception are trapped, logged, recorded in
      `result.failed`, and the pipeline moves on. No single bad file
      can kill the batch.
   e. Write the `.md`, append the `MergeEntry`.
6. Call `merge()` and/or `write_manifest()` with the completed
   `entries` list.
7. Clean up the ephemeral tempdir if one was used.

The return value is a `BuildResult`:

```python
@dataclass
class BuildResult:
    converted: list[Path]
    skipped: list[Path]
    failed: list[tuple[Path, str]]
    merged_path: Path | None
    manifest_path: Path | None
```

The CLI uses it to print a final summary and compute the exit code
(non-zero if anything failed).

### `cli.py`

**Responsibility:** translate CLI arguments into a `build_corpus()`
call and format the result as stdout text.

Thin by design. Every behaviour the CLI exposes has a
corresponding keyword argument on `build_corpus()`, so Python users
get the same power without going through `argparse`. The CLI adds
only three things:

1. `argparse`-based flag parsing.
2. Logging configuration (`-v` turns on DEBUG).
3. A final summary block (`converted:`, `skipped:`, `failed:`,
   `merged:`, `manifest:`) plus a non-zero exit code when any file
   failed.

---

## A typical run, end to end

```bash
doc2md ./papers \
    --merged ./papers/papers_corpus.md \
    --manifest ./papers/INDEX.md
```

1. **`cli.main()`** parses args, sets up logging, calls
   `build_corpus(root='./papers', merged_output='papers/papers_corpus.md',
   manifest_output='papers/INDEX.md', ...)`.
2. **`build_corpus()`** resolves `./papers` to an absolute path,
   validates flags, builds a converter cache, and prepares the scan
   exclude set: `{/abs/path/papers/papers_corpus.md,
   /abs/path/papers/INDEX.md}`.
3. **`scanner.scan()`** walks `./papers`, filters by registered
   extensions (`.pdf`, `.docx`, …), skips hidden/lockfile entries,
   drops the two excluded paths, and applies the derived-markdown
   heuristic. Returns a sorted list of `Path` objects.
4. For each source, the pipeline:
   - computes the per-document output path (sibling mode: `src.with_suffix('.md')`),
   - checks if the source is its own output (no, unless it's an
     authentic `.md`),
   - checks mtime-based up-to-date (skip if yes and not `--force`),
   - looks up the converter by extension,
   - calls `converter.convert(source)` — which for a PDF invokes
     `opendataloader-pdf` in a per-file scratch dir, reads the result
     back, and returns the Markdown string,
   - writes the `.md` next to the source,
   - appends a `MergeEntry(source, markdown_path)` to the running
     list.
5. Once every source has been processed, `pipeline` calls
   **`merger.merge(entries, root, 'papers/papers_corpus.md', title='papers')`**.
   `merge` reads each individual `.md`, extracts a teaser, computes
   a total size, and writes the merged file with its header, TOC, and
   per-document sections.
6. Then **`merger.write_manifest(entries, root, 'papers/INDEX.md',
   title='papers')`** writes the standalone manifest using the same
   header but with file-link TOC entries.
7. `build_corpus()` returns a `BuildResult`; `cli.main()` prints the
   summary; the process exits 0 (or 1 if any file failed).

---

## Extension points

### Add a new format

Write a `Converter` subclass and register it:

```python
# doc2md/converters.py
class MyFormatConverter(Converter):
    extensions = (".myfmt",)

    def __init__(self) -> None:
        # lazy backend import here
        ...

    def convert(self, source: Path) -> str:
        # return markdown
        ...

_register(DEFAULT_CONVERTERS, MyFormatConverter)
```

The scanner, pipeline, merger, and CLI all pick up the new extension
automatically. No wiring needed anywhere else.

### Replace a backend

Subclass the relevant converter or register a completely new class
with the same `extensions` tuple. Later registrations override
earlier ones — that's how `PandocConverter` supersedes
`MarkItDownConverter` for `.docx`.

You can also inject converters from the outside without touching the
source tree:

```python
from doc2md import build_corpus
from doc2md.converters import Converter, PdfConverter

class MyPdfConverter(Converter):
    extensions = (".pdf",)
    def convert(self, source): ...

build_corpus(
    root=...,
    converters={".pdf": MyPdfConverter()},
)
```

The keyword argument bypasses `DEFAULT_CONVERTERS` completely.

### Customize the merged-file layout

`merger.merge()` and `merger.write_manifest()` are the only code that
assembles corpus-level artifacts. Everything they emit comes from a
handful of helper functions — `_header`, `_toc_sections`, `_toc_files`,
`_teaser`, `_human_size`. Changing the look of the merged file means
editing these in one place.

### Add a new CLI flag

`cli.py` owns `argparse` and passes keyword arguments to
`build_corpus()`. Add the flag to `_build_parser()`, then pipe it
through to the `build_corpus()` call. If the behaviour is not
trivially a boolean switch, the feature lives in `pipeline.py`; the
CLI is a thin layer on top.

---

## Invariants

The code guarantees these at runtime:

- **Source files are never written.** The pipeline reads sources, and
  writes `.md` outputs elsewhere or not at all. The one edge case is
  an authentic `.md` source in sibling mode, where the output path
  equals the source path; that is caught by the source-is-its-own-output
  short-circuit and neither read nor rewritten.
- **One bad file never kills a batch.** All converter exceptions are
  caught and recorded; the pipeline continues with the next file.
- **A run is idempotent absent `--force`.** If nothing has changed on
  disk, a re-run does zero conversions and produces byte-identical
  merged/manifest files except for the timestamp in the header.
- **The merged file is self-contained.** Every document it references
  appears in the TOC and the body; every in-file anchor in the TOC
  has a matching section heading.
- **The scanner never returns doc2md's own outputs.** Explicit
  exclusion handles the merged/manifest paths; the derived-markdown
  heuristic handles per-document outputs.
- **Lazy backends fail late, not early.** Importing `doc2md`, or
  running the CLI over a folder whose formats are all handled,
  never touches a missing backend.

---

## Known trade-offs

- **The derived-markdown heuristic is stem-based.** If you have a
  legitimate hand-written `notes.md` in the same directory as an
  unrelated `notes.pdf`, the heuristic will drop `notes.md` from the
  source list. Use `--output-dir` to separate inputs from outputs if
  this happens.
- **`.pptx` equations are lost.** Pandoc does not currently read
  `.pptx` as input, so slideshow equations fall through markitdown's
  text extraction, which flattens OMML.
- **PDF equations are lost.** PDF math is rendered as glyphs or
  bitmaps, and neither opendataloader-pdf nor any other plain-text
  extractor recovers it reliably. A future alternative
  `PdfConverter` backed by marker or Nougat could fix this for
  academic PDFs; see [README.md](README.md) for the FAQ note.
- **Output layout is sibling-by-default.** That's the most ergonomic
  mode for "drop a folder into a Gem", but it intermixes inputs and
  outputs in the same tree. For cleaner separation, pass
  `--output-dir`.
- **No parallelism.** The pipeline converts one file at a time. The
  bottleneck is usually pandoc or opendataloader-pdf startup cost,
  and the code base is small enough that adding a thread-pool
  wrapper around the converter loop would be a dozen lines — but
  it's a future concern, not a v0.x one.

---

## Testing

`doc2md` does not yet ship an automated test suite. Development relies
on repeatable smoke tests against representative fixtures — a folder
with one of each supported format, plus a planted derived-markdown
file and an authentic hand-written `.md`. Every release verifies:

1. A clean first run converts every file.
2. An immediate re-run converts zero files (idempotency).
3. A `--force` run preserves authentic `.md` source mtime.
4. The merged file is not in its own TOC.
5. The manifest file is not in the sources list.
6. JSON/XML TOC teasers show inside-fence content, not the fence
   marker.

A formal `pytest` suite is on the roadmap. Contributions welcome.
