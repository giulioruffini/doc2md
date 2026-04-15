"""Per-format conversion strategies.

Each :class:`Converter` turns one source document into a Markdown string.
Backends are imported lazily so a missing optional dependency only fails
when its format is actually encountered.

Three built-in converters cover most document formats:

* :class:`PdfConverter` — wraps `opendataloader-pdf
  <https://pypi.org/project/opendataloader-pdf/>`_ for higher-quality PDF
  extraction than markitdown's built-in PDF path.
* :class:`PandocConverter` — shells out to the `pandoc
  <https://pandoc.org>`_ binary for ``.docx`` and ``.odt``. Pandoc
  preserves Word equations as LaTeX (``$…$`` / ``$$…$$``) and produces
  cleaner tables and headings than markitdown. Auto-enabled when the
  ``pandoc`` binary is present on ``PATH``.
* :class:`MarkItDownConverter` — wraps `Microsoft MarkItDown
  <https://github.com/microsoft/markitdown>`_ and handles ``.docx``,
  ``.pptx``, ``.xlsx``, ``.xls``, ``.html``, ``.htm`` and ``.csv``.
  Used as a fallback for ``.docx`` when pandoc is not available.

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
    """DOCX / ODT → Markdown via the ``pandoc`` binary.

    Pandoc is preferred over :class:`MarkItDownConverter` for these
    formats because it:

    * converts Word equations (OMML) to LaTeX (``$…$`` / ``$$…$$``),
    * produces cleaner headings, tables, blockquotes, and lists,
    * handles ODT, which markitdown does not.

    This converter is auto-registered as the default for ``.docx`` and
    ``.odt`` when the ``pandoc`` binary is found on ``PATH``. If pandoc
    is not installed, ``.docx`` falls back to markitdown and ``.odt``
    has no handler. Install from https://pandoc.org — e.g.
    ``brew install pandoc`` on macOS or ``apt install pandoc`` on Debian.

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

    extensions = (".docx", ".odt")

    def __init__(self, *, extra_args: list[str] | None = None) -> None:
        if shutil.which("pandoc") is None:
            raise ImportError(
                "pandoc binary not found on PATH. "
                "Install from https://pandoc.org "
                "(e.g. `brew install pandoc` or `apt install pandoc`)."
            )
        self._extra_args = list(extra_args or [])

    def convert(self, source: Path) -> str:
        fmt = {".docx": "docx", ".odt": "odt"}[source.suffix.lower()]
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


def _register(mapping: dict[str, type[Converter]], cls: type[Converter]) -> None:
    for ext in cls.extensions:
        mapping[ext] = cls


#: Extension → converter class. Override via ``build_corpus(converters=...)``.
DEFAULT_CONVERTERS: dict[str, type[Converter]] = {}
_register(DEFAULT_CONVERTERS, PdfConverter)
_register(DEFAULT_CONVERTERS, MarkItDownConverter)
# Pandoc takes precedence for .docx (and adds .odt) when the binary is
# available — registration order matters: pandoc overrides markitdown.
if shutil.which("pandoc") is not None:
    _register(DEFAULT_CONVERTERS, PandocConverter)
