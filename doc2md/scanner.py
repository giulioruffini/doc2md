"""Discover source documents under a root folder."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

# Word autosave files (~$Foo.docx) and dotfiles are never real sources.
_HIDDEN_PREFIXES: tuple[str, ...] = ("~$", ".")

#: Extensions that are treated as "already Markdown" for the purposes of
#: the derived-markdown heuristic (see :func:`scan`).
_MARKDOWN_EXTS: frozenset[str] = frozenset({".md", ".markdown"})


def scan(
    root: Path,
    extensions: Iterable[str],
    *,
    recursive: bool = True,
    exclude: Iterable[Path] | None = None,
) -> list[Path]:
    """Return a sorted list of source files under *root*.

    A file is included when:

    * its suffix (case-insensitive) is in *extensions*;
    * its name does not start with a Word lockfile prefix (``~$``) or a
      dot;
    * its resolved path is not in *exclude* (typically the merged/
      manifest output paths of the current run, so doc2md never picks up
      its own outputs as sources);
    * **derived-markdown heuristic:** if a ``.md`` / ``.markdown`` file
      has a sibling with the same stem and a *non-markdown* registered
      extension (e.g. ``report.md`` next to ``report.docx``), it is
      assumed to be a doc2md output from a previous run and dropped from
      the source list. Authentic hand-written markdown files (without
      such a sibling) are still included. This heuristic is
      intentionally simple; if it gets in your way, use ``--output-dir``
      to keep inputs and outputs physically separate.
    """
    exts = {e.lower() for e in extensions}
    excluded = {p.resolve() for p in (exclude or ())}

    iterator = root.rglob("*") if recursive else root.glob("*")

    candidates = [
        p for p in iterator
        if p.is_file()
        and p.suffix.lower() in exts
        and not any(p.name.startswith(pre) for pre in _HIDDEN_PREFIXES)
        and p.resolve() not in excluded
    ]

    md_exts_in_registry = _MARKDOWN_EXTS & exts
    if md_exts_in_registry:
        # (parent_dir, stem) for every non-markdown source → any .md at
        # the same location is treated as a derived output.
        primary_keys: set[tuple[Path, str]] = {
            (p.parent, p.stem)
            for p in candidates
            if p.suffix.lower() not in md_exts_in_registry
        }
        candidates = [
            p for p in candidates
            if p.suffix.lower() not in md_exts_in_registry
            or (p.parent, p.stem) not in primary_keys
        ]

    return sorted(candidates)
