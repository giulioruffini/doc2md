"""Corpus-level writers: merged file and standalone manifest.

Both writers share the same header/TOC vocabulary so an LLM sees a
consistent structure whether it's reading a single merged corpus or a
manifest that points at individual ``.md`` files:

* every document has a stable numeric ID ``[NN]`` (zero-padded);
* the header tells the agent what the corpus is and how to cite it;
* a table of contents lists every document with size, format, and a
  one-line teaser pulled from the body.

In the merged file, TOC entries link to in-file anchors (``#doc-NN``).
In the manifest, they link to the actual ``.md`` files on disk,
relative to the manifest's own location.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class MergeEntry:
    """One document in the corpus, tying its source to its Markdown rendering."""

    source: Path      # original .pdf / .docx
    markdown: Path    # converted .md file


# --------------------------------------------------------------------------- #
# formatting helpers                                                          #
# --------------------------------------------------------------------------- #


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _teaser(content: str, max_len: int = 140) -> str:
    """First non-trivial line of a document, stripped of markdown noise."""
    for raw in content.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        s = s.lstrip("*_>-•·– ").strip()
        if len(s) < 3:
            continue
        return s[: max_len - 1].rstrip() + "…" if len(s) > max_len else s
    return ""


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _fmt(path: Path) -> str:
    return path.suffix.lstrip(".").lower() or "?"


def _size(path: Path) -> str:
    try:
        return _human_size(path.stat().st_size)
    except FileNotFoundError:
        return "?"


# --------------------------------------------------------------------------- #
# header + TOC builders                                                       #
# --------------------------------------------------------------------------- #


def _header(
    title: str,
    source_root: Path,
    entries: list[MergeEntry],
    total_bytes: int,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"# Corpus: {title}\n\n"
        f"- **Generated:** {ts}\n"
        f"- **Source root:** `{source_root.name}`\n"
        f"- **Documents:** {len(entries)}\n"
        f"- **Total source size:** {_human_size(total_bytes)}\n\n"
        "## How to use this corpus\n\n"
        "This file is a concatenation of documents converted from PDF/DOCX "
        "to Markdown for LLM ingest. Each document has a stable numeric ID "
        "of the form `[NN]`. When citing a document in an answer, reference "
        "it as `[NN] <filename>`. The table of contents below maps every ID "
        "to a `## [NN] ...` heading further down in the file.\n\n"
    )


def _toc_sections(
    entries: list[MergeEntry],
    source_root: Path,
    teasers: list[str],
) -> str:
    lines = ["## Table of contents\n"]
    for i, (e, teaser) in enumerate(zip(entries, teasers), start=1):
        tag = f"[{i:02d}]"
        rel = _rel(e.source, source_root)
        suffix = f" — _{teaser}_" if teaser else ""
        lines.append(
            f"{i}. **`{tag}`** [`{rel}`](#doc-{i:02d}) — "
            f"{_size(e.source)} · {_fmt(e.source)}{suffix}"
        )
    lines.append("")
    return "\n".join(lines)


def _toc_files(
    entries: list[MergeEntry],
    source_root: Path,
    manifest_dir: Path,
    teasers: list[str],
) -> str:
    lines = ["## Table of contents\n"]
    for i, (e, teaser) in enumerate(zip(entries, teasers), start=1):
        tag = f"[{i:02d}]"
        src_rel = _rel(e.source, source_root)
        try:
            link = e.markdown.relative_to(manifest_dir).as_posix()
        except ValueError:
            link = os.path.relpath(e.markdown, manifest_dir)
        suffix = f" — _{teaser}_" if teaser else ""
        lines.append(
            f"{i}. **`{tag}`** [`{src_rel}`]({link}) — "
            f"{_size(e.source)} · {_fmt(e.source)}{suffix}"
        )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# public writers                                                              #
# --------------------------------------------------------------------------- #


def merge(
    entries: list[MergeEntry],
    source_root: Path,
    output: Path,
    *,
    title: str = "Merged Corpus",
) -> None:
    """Write a merged Markdown file: rich header, TOC, per-document sections."""
    bodies: list[str] = []
    teasers: list[str] = []
    total_bytes = 0

    for entry in entries:
        body = entry.markdown.read_text(encoding="utf-8", errors="replace").strip()
        bodies.append(body)
        teasers.append(_teaser(body))
        try:
            total_bytes += entry.source.stat().st_size
        except FileNotFoundError:
            pass

    parts: list[str] = [
        _header(title, source_root, entries, total_bytes),
        _toc_sections(entries, source_root, teasers),
    ]

    for i, (entry, body) in enumerate(zip(entries, bodies), start=1):
        if not body:
            continue
        tag = f"[{i:02d}]"
        rel = _rel(entry.source, source_root)
        parts.append("\n\n---\n\n")
        parts.append(f'## <a id="doc-{i:02d}"></a>{tag} {rel}\n\n')
        parts.append(
            f"**Source:** `{rel}`  \n"
            f"**Format:** {_fmt(entry.source)} · "
            f"**Size:** {_size(entry.source)}\n\n"
        )
        parts.append(body)
        parts.append("\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(parts), encoding="utf-8")


def write_manifest(
    entries: list[MergeEntry],
    source_root: Path,
    output: Path,
    *,
    title: str = "Corpus manifest",
) -> None:
    """Write a standalone manifest: header + TOC linking to individual ``.md`` files.

    Links in the TOC are computed relative to *output*'s parent directory,
    so the manifest can live next to the ``.md`` files and be opened in any
    Markdown viewer.
    """
    teasers: list[str] = []
    total_bytes = 0
    for entry in entries:
        try:
            body = entry.markdown.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            body = ""
        teasers.append(_teaser(body))
        try:
            total_bytes += entry.source.stat().st_size
        except FileNotFoundError:
            pass

    manifest_dir = output.resolve().parent
    parts = [
        _header(title, source_root, entries, total_bytes),
        _toc_files(entries, source_root, manifest_dir, teasers),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(parts), encoding="utf-8")
