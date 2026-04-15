"""Command-line entry point for doc2md."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from doc2md.pipeline import build_corpus


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc2md",
        description=(
            "Scan a folder for documents (PDF, DOCX, PPTX, XLSX, HTML, "
            "CSV, ...) and emit Markdown suitable for LLM ingest — "
            "individual files, a merged corpus, or both."
        ),
    )
    parser.add_argument("root", type=Path, help="Folder to scan.")
    parser.add_argument(
        "--merged",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Also write a single merged Markdown file at PATH. "
            "The file includes a header, table of contents, and "
            "per-document sections with stable [NN] IDs."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Also write a standalone manifest (header + TOC linking to "
            "individual .md files) at PATH. Requires per-document files."
        ),
    )
    parser.add_argument(
        "--no-individual",
        action="store_true",
        help="Do not keep per-document .md files (requires --merged).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Mirror per-document .md files into DIR instead of writing "
            "them next to their sources."
        ),
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only scan the top-level folder.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-convert files even if an up-to-date .md already exists.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose (DEBUG-level) logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    try:
        result = build_corpus(
            root=args.root,
            merged_output=args.merged,
            manifest_output=args.manifest,
            write_individual=not args.no_individual,
            output_dir=args.output_dir,
            recursive=not args.no_recursive,
            force=args.force,
        )
    except (ValueError, NotADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"converted:           {len(result.converted)}")
    print(f"skipped (current):   {len(result.skipped)}")
    print(f"failed:              {len(result.failed)}")
    for src, err in result.failed:
        print(f"  - {src}: {err}")
    if result.merged_path:
        print(f"merged:              {result.merged_path}")
    if result.manifest_path:
        print(f"manifest:            {result.manifest_path}")

    return 0 if not result.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
