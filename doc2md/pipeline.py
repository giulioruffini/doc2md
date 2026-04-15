"""High-level orchestration: discover → convert → (optionally) merge / manifest."""
from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from doc2md.converters import DEFAULT_CONVERTERS, Converter
from doc2md.merger import MergeEntry, merge, write_manifest
from doc2md.scanner import scan

log = logging.getLogger(__name__)


@dataclass
class BuildResult:
    """Summary of a :func:`build_corpus` run."""

    converted: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    merged_path: Path | None = None
    manifest_path: Path | None = None


def _is_up_to_date(source: Path, output: Path) -> bool:
    try:
        return output.stat().st_mtime >= source.stat().st_mtime
    except FileNotFoundError:
        return False


def build_corpus(
    root: Path,
    *,
    merged_output: Path | None = None,
    manifest_output: Path | None = None,
    write_individual: bool = True,
    output_dir: Path | None = None,
    recursive: bool = True,
    force: bool = False,
    converters: dict[str, Converter] | None = None,
) -> BuildResult:
    """Convert every supported document under *root* to Markdown.

    Parameters
    ----------
    root:
        Folder to scan.
    merged_output:
        If set, also write a single merged Markdown file at this path. The
        merged file carries a header, table of contents, and per-document
        sections with stable ``[NN]`` IDs.
    manifest_output:
        If set, also write a standalone directory/manifest file (header +
        TOC linking to the individual ``.md`` files). Requires
        *write_individual* to be ``True`` — otherwise the links would be
        dead.
    write_individual:
        If ``True`` (default), keep per-document ``.md`` files. If
        ``False``, only the merged file is kept (requires *merged_output*).
    output_dir:
        If set, individual ``.md`` files are written into this directory,
        mirroring the source tree. If ``None``, each ``.md`` is placed next
        to its source file.
    recursive:
        Recurse into subfolders (default True).
    force:
        Re-convert files even when an up-to-date ``.md`` already exists.
    converters:
        Custom ``{extension: Converter instance}`` mapping. Defaults to
        lazy instances of :data:`doc2md.converters.DEFAULT_CONVERTERS`.
    """
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    if not write_individual and merged_output is None:
        raise ValueError(
            "nothing to do: write_individual=False requires merged_output"
        )
    if manifest_output is not None and not write_individual:
        raise ValueError(
            "--manifest requires individual .md files (drop --no-individual)"
        )

    # Lazy converter instantiation — a missing backend only matters if its
    # extension actually appears in *root*. Cache by class so one converter
    # instance is shared across every extension it handles.
    if converters is None:
        extensions: list[str] = list(DEFAULT_CONVERTERS.keys())
        class_cache: dict[type[Converter], Converter] = {}

        def get_converter(ext: str) -> Converter:
            cls = DEFAULT_CONVERTERS[ext]
            if cls not in class_cache:
                class_cache[cls] = cls()
            return class_cache[cls]
    else:
        extensions = list(converters.keys())

        def get_converter(ext: str) -> Converter:
            return converters[ext]

    sources = scan(root, extensions, recursive=recursive)
    log.info("found %d source document(s) under %s", len(sources), root)

    result = BuildResult()
    if not sources:
        return result

    # Where do per-document .md files live? Three modes:
    #   write_individual & no output_dir  → sibling of the source file
    #   write_individual & output_dir     → mirrored under output_dir
    #   !write_individual                 → ephemeral temp dir, cleaned up
    cleanup_dir: Path | None = None
    if write_individual:
        individual_root = output_dir.resolve() if output_dir else root
    else:
        cleanup_dir = Path(tempfile.mkdtemp(prefix="doc2md_"))
        individual_root = cleanup_dir

    try:
        entries: list[MergeEntry] = []
        for src in sources:
            rel = src.relative_to(root)
            if write_individual and output_dir is None:
                out_path = src.with_suffix(".md")
            else:
                out_path = (individual_root / rel).with_suffix(".md")

            if not force and _is_up_to_date(src, out_path):
                log.info("up-to-date: %s", rel)
                result.skipped.append(src)
                entries.append(MergeEntry(source=src, markdown=out_path))
                continue

            try:
                converter = get_converter(src.suffix.lower())
            except ImportError as exc:
                log.warning("backend missing for %s: %s", src.suffix, exc)
                result.failed.append((src, f"backend missing: {exc}"))
                continue

            log.info("converting: %s", rel)
            try:
                content = converter.convert(src)
            except Exception as exc:  # noqa: BLE001 — log and continue
                log.warning("failed: %s (%s)", rel, exc)
                result.failed.append((src, str(exc)))
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            result.converted.append(out_path)
            entries.append(MergeEntry(source=src, markdown=out_path))

        title = root.name

        if merged_output is not None and entries:
            merged_path = merged_output.resolve()
            merge(entries, root, merged_path, title=title)
            result.merged_path = merged_path
            log.info("merged %d file(s) into %s", len(entries), merged_path)

        if manifest_output is not None and entries:
            manifest_path = manifest_output.resolve()
            write_manifest(entries, root, manifest_path, title=title)
            result.manifest_path = manifest_path
            log.info("wrote manifest for %d file(s) to %s", len(entries), manifest_path)
    finally:
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)

    return result
