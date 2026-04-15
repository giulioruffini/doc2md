"""Per-format conversion strategies.

Each :class:`Converter` turns one source document into a Markdown string.
Backends are imported lazily so a missing optional dependency only fails
when its format is actually encountered.

Two built-in converters cover most document formats:

* :class:`MarkItDownConverter` — wraps `Microsoft MarkItDown
  <https://github.com/microsoft/markitdown>`_ and handles ``.docx``,
  ``.pptx``, ``.xlsx``, ``.xls``, ``.html``, ``.htm`` and ``.csv``.
* :class:`PdfConverter` — wraps `opendataloader-pdf
  <https://pypi.org/project/opendataloader-pdf/>`_ for higher-quality
  PDF extraction than markitdown's built-in PDF path.

Adding a new format:
    1. Subclass :class:`Converter`, set ``extensions``, implement ``convert``.
    2. Register the extension(s) in :data:`DEFAULT_CONVERTERS`.
"""
from __future__ import annotations

import shutil
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


def _register(mapping: dict[str, type[Converter]], cls: type[Converter]) -> None:
    for ext in cls.extensions:
        mapping[ext] = cls


#: Extension → converter class. Override via ``build_corpus(converters=...)``.
DEFAULT_CONVERTERS: dict[str, type[Converter]] = {}
_register(DEFAULT_CONVERTERS, PdfConverter)
_register(DEFAULT_CONVERTERS, MarkItDownConverter)
