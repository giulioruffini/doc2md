"""Discover source documents under a root folder."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

# Word autosave files (~$Foo.docx) and dotfiles are never real sources.
_HIDDEN_PREFIXES: tuple[str, ...] = ("~$", ".")


def scan(root: Path, extensions: Iterable[str], *, recursive: bool = True) -> list[Path]:
    """Return a sorted list of source files under *root* whose suffix is in *extensions*.

    Extensions are matched case-insensitively and must include the leading dot
    (e.g. ``".pdf"``). Hidden and Word-lockfile entries are skipped.
    """
    exts = {e.lower() for e in extensions}
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        p for p in iterator
        if p.is_file()
        and p.suffix.lower() in exts
        and not any(p.name.startswith(pre) for pre in _HIDDEN_PREFIXES)
    )
