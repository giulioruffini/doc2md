"""Per-format conversion strategies.

Each :class:`Converter` turns one source document into a Markdown string.
Backends are imported lazily so a missing optional dependency only fails
when its format is actually encountered.

Six built-in converters cover most document formats:

* :class:`PdfConverter` — wraps `opendataloader-pdf
  <https://pypi.org/project/opendataloader-pdf/>`_ for higher-quality PDF
  extraction than markitdown's built-in PDF path.
* :class:`PandocConverter` — shells out to the `pandoc
  <https://pandoc.org>`_ binary for ``.docx``, ``.odt``, ``.rtf`` and
  ``.epub``. Pandoc preserves Word equations as LaTeX (``$…$`` /
  ``$$…$$``) and produces cleaner tables and headings than markitdown.
  Auto-enabled when the ``pandoc`` binary is present on ``PATH``.
* :class:`MarkItDownConverter` — wraps `Microsoft MarkItDown
  <https://github.com/microsoft/markitdown>`_ and handles ``.docx``,
  ``.pptx``, ``.xlsx``, ``.xls``, ``.html``, ``.htm`` and ``.csv``.
  Used as a fallback for ``.docx`` when pandoc is not available.
* :class:`PlainTextConverter` — passthrough for ``.txt``. No backend,
  no parsing — the file is returned verbatim.
* :class:`StructuredTextConverter` — wraps ``.json`` and ``.xml`` in a
  fenced code block with a language hint; JSON is pretty-printed when
  parseable. No backend dependency.
* :class:`MarkdownPassthroughConverter` — returns ``.md`` / ``.markdown``
  files verbatim. Works with the scanner's derived-markdown heuristic,
  which drops ``.md`` files that look like doc2md's own outputs from
  previous runs.
* :class:`LatexConverter` — handles ``.tex`` files. LaTeX is the best
  math notation for LLMs, so it is kept as-is rather than converted.
  Sub-files (without ``\\documentclass``) are skipped; multi-file
  projects are flattened via ``latexpand`` when available. Output is
  wrapped in a ```` ```latex ```` code fence.

Adding a new format:
    1. Subclass :class:`Converter`, set ``extensions``, implement ``convert``.
    2. Register the extension(s) in :data:`DEFAULT_CONVERTERS`.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path


class Converter(ABC):
    """Strategy for turning a single source document into Markdown text."""

    #: File suffixes (lowercase, leading dot) this converter handles.
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def convert(self, source: Path) -> str:
        """Return Markdown content for *source*. Raise on failure."""


class MarkItDownConverter(Converter):
    """All formats handled by Microsoft's MarkItDown.

    One ``MarkItDown`` instance is shared across every extension the class
    registers, so you only pay the import/setup cost once per run
    regardless of how many of these formats appear in the corpus.
    """

    extensions = (
        ".docx",
        ".pptx",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
        ".csv",
    )

    def __init__(self) -> None:
        from markitdown import MarkItDown  # lazy — only required when used

        self._md = MarkItDown()

    def convert(self, source: Path) -> str:
        result = self._md.convert(str(source))
        return result.text_content or ""


class PdfConverter(Converter):
    """PDF → Markdown via opendataloader-pdf.

    opendataloader is batch-oriented and writes files to an output directory
    rather than returning text. We run it against a per-file scratch dir,
    read the result, and clean up.
    """

    extensions = (".pdf",)

    def __init__(self, *, use_struct_tree: bool = True, hybrid: str | None = None) -> None:
        import opendataloader_pdf  # lazy

        self._backend = opendataloader_pdf
        self._use_struct_tree = use_struct_tree
        self._hybrid = hybrid

    def convert(self, source: Path) -> str:
        scratch = Path(tempfile.mkdtemp(prefix="doc2md_pdf_"))
        try:
            kwargs: dict[str, object] = {
                "input_path": [str(source)],
                "output_dir": str(scratch),
                "format": "markdown",
            }
            if self._use_struct_tree:
                kwargs["use_struct_tree"] = True
            if self._hybrid:
                kwargs["hybrid"] = self._hybrid

            self._backend.convert(**kwargs)

            produced = sorted(scratch.rglob("*.md"))
            if not produced:
                raise RuntimeError("opendataloader-pdf produced no markdown output")
            if len(produced) == 1:
                return produced[0].read_text(encoding="utf-8", errors="replace")
            # Rare: multi-file output (e.g. per-page). Concatenate in order.
            return "\n\n".join(
                p.read_text(encoding="utf-8", errors="replace") for p in produced
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class PandocConverter(Converter):
    """DOCX / ODT / RTF / EPUB → Markdown via the ``pandoc`` binary.

    Pandoc is preferred over :class:`MarkItDownConverter` for these
    formats because it:

    * converts Word equations (OMML) to LaTeX (``$…$`` / ``$$…$$``),
    * produces cleaner headings, tables, blockquotes, and lists,
    * handles ODT, RTF and EPUB, which markitdown does not (at least
      not in the default doc2md install).

    This converter is auto-registered as the default for ``.docx``,
    ``.odt``, ``.rtf`` and ``.epub`` when the ``pandoc`` binary is
    found on ``PATH``. If pandoc is not installed, ``.docx`` falls
    back to markitdown and the other three formats have no handler.
    Install from https://pandoc.org — e.g. ``brew install pandoc`` on
    macOS or ``apt install pandoc`` on Debian.

    Pandoc invocation can be customized by passing *extra_args*. By
    default doc2md runs::

        pandoc --from={fmt} --to=markdown --wrap=none
               --markdown-headings=atx
               --extract-media={scratch}
               <source>

    which yields one-paragraph-per-line Markdown with LaTeX math and
    images extracted into a scratch directory that is cleaned up after
    the call (image references in the output point at the now-deleted
    scratch dir — downstream LLM ingest does not use them).
    """

    extensions = (".docx", ".odt", ".rtf", ".epub")

    def __init__(self, *, extra_args: list[str] | None = None) -> None:
        if shutil.which("pandoc") is None:
            raise ImportError(
                "pandoc binary not found on PATH. "
                "Install from https://pandoc.org "
                "(e.g. `brew install pandoc` or `apt install pandoc`)."
            )
        self._extra_args = list(extra_args or [])

    def convert(self, source: Path) -> str:
        fmt = {
            ".docx": "docx",
            ".odt": "odt",
            ".rtf": "rtf",
            ".epub": "epub",
        }[source.suffix.lower()]
        media_dir = Path(tempfile.mkdtemp(prefix="doc2md_pandoc_media_"))
        try:
            cmd = [
                "pandoc",
                "--from", fmt,
                "--to", "markdown",
                "--wrap=none",
                "--markdown-headings=atx",
                f"--extract-media={media_dir}",
                *self._extra_args,
                str(source),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return proc.stdout
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"pandoc failed on {source.name}: {exc.stderr.strip()}"
            ) from exc
        finally:
            shutil.rmtree(media_dir, ignore_errors=True)


class PlainTextConverter(Converter):
    """Plain ``.txt`` → Markdown.

    This is a no-op converter: plain text is already valid Markdown (any
    stray markdown metacharacters are ignored by LLMs anyway), so the
    file contents are returned as-is. No backend dependencies, no
    parsing — just a UTF-8 read with replacement-character fallback for
    broken encodings.
    """

    extensions = (".txt",)

    def convert(self, source: Path) -> str:
        return source.read_text(encoding="utf-8", errors="replace")


class MarkdownPassthroughConverter(Converter):
    """Hand-written ``.md`` / ``.markdown`` → Markdown.

    Returns the file verbatim. The scanner's derived-markdown heuristic
    (see :func:`doc2md.scanner.scan`) takes care of distinguishing
    authentic markdown sources from doc2md's own outputs in the same
    directory, and the pipeline short-circuits the write when the
    resolved output path equals the source path (so ``--force`` won't
    clobber the source's timestamp).
    """

    extensions = (".md", ".markdown")

    def convert(self, source: Path) -> str:
        return source.read_text(encoding="utf-8", errors="replace")


class StructuredTextConverter(Converter):
    """``.json`` / ``.xml`` → fenced code block with a language hint.

    Markitdown's built-in JSON / XML handling flattens the content to a
    single line, which is unreadable for both humans and LLMs. This
    converter instead wraps the raw text in a triple-backtick fence
    with the appropriate language tag — preserving structure exactly
    while rendering cleanly in every Markdown viewer.

    As a bonus, ``.json`` files are pretty-printed (2-space indent)
    when they parse as valid JSON; if parsing fails, the original text
    is kept verbatim.
    """

    extensions = (".json", ".xml")

    def convert(self, source: Path) -> str:
        content = source.read_text(encoding="utf-8", errors="replace")
        ext = source.suffix.lower()
        if ext == ".json":
            import json

            try:
                parsed = json.loads(content)
                content = json.dumps(parsed, indent=2, ensure_ascii=False)
            except (ValueError, json.JSONDecodeError):
                pass  # not valid JSON — keep raw text
        lang = ext.lstrip(".")
        return f"```{lang}\n{content}\n```\n"


class LatexConverter(Converter):
    """``.tex`` → fenced LaTeX, with optional project flattening.

    LaTeX *is* the gold-standard math notation for LLMs — converting
    it to Markdown would lose information. So this converter passes
    the source through with minimal processing:

    1. **Sub-file detection.** If the file does not contain
       ``\\documentclass``, it is a chapter or section meant to be
       ``\\input{}``-ed by a parent document. Converting it separately
       would double-count content, so an empty string is returned
       (the merger already skips empty documents).
    2. **Project flattening** via ``latexpand`` (ships with TeX Live).
       When the binary is present on ``PATH``, it inlines all
       ``\\input{}``, ``\\include{}``, and (if a ``.bbl`` exists) the
       compiled bibliography into one self-contained ``.tex`` stream.
       ``latexpand`` runs from the source's parent directory so
       relative paths resolve correctly. If ``latexpand`` is not
       installed, the raw file content is used instead — the LLM
       still sees the document structure but ``\\input{}`` references
       remain unresolved.
    3. The result is wrapped in a ```` ```latex ```` fenced code block,
       consistent with how ``StructuredTextConverter`` handles JSON
       and XML.
    """

    extensions = (".tex",)

    def convert(self, source: Path) -> str:
        content = source.read_text(encoding="utf-8", errors="replace")

        if "\\documentclass" not in content:
            return ""

        if shutil.which("latexpand"):
            try:
                cmd = ["latexpand"]
                # --expand-bbl takes a FILE argument (the .bbl path),
                # not a bare flag. Only use it when the .bbl exists.
                bbl = source.with_suffix(".bbl")
                if bbl.exists():
                    cmd.extend(["--expand-bbl", bbl.name])
                cmd.append(source.name)
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=source.parent,
                    check=True,
                )
                if proc.stdout.strip():
                    content = proc.stdout
            except subprocess.CalledProcessError:
                pass  # fall back to raw content

        return f"```latex\n{content}\n```\n"


def _register(mapping: dict[str, type[Converter]], cls: type[Converter]) -> None:
    for ext in cls.extensions:
        mapping[ext] = cls


#: Extension → converter class. Override via ``build_corpus(converters=...)``.
DEFAULT_CONVERTERS: dict[str, type[Converter]] = {}
_register(DEFAULT_CONVERTERS, PdfConverter)
_register(DEFAULT_CONVERTERS, MarkItDownConverter)
_register(DEFAULT_CONVERTERS, PlainTextConverter)
_register(DEFAULT_CONVERTERS, StructuredTextConverter)
_register(DEFAULT_CONVERTERS, MarkdownPassthroughConverter)
_register(DEFAULT_CONVERTERS, LatexConverter)
# Pandoc takes precedence for .docx (and adds .odt / .rtf / .epub)
# when the binary is available — registration order matters: pandoc
# overrides markitdown.
if shutil.which("pandoc") is not None:
    _register(DEFAULT_CONVERTERS, PandocConverter)
