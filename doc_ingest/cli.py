"""doc-ingest: documents in, JSONL chunks out."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .chunker import chunk_document
from .loaders import SUPPORTED_SUFFIXES, MissingDependency, load_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc-ingest",
        description="Extract text from .txt, .md, .html, .docx and .pdf files and write section-aware chunks as JSONL.",
    )
    parser.add_argument("paths", nargs="+", help="files or directories (searched recursively)")
    parser.add_argument("--out", default="-", help="output JSONL file (default: stdout)")
    parser.add_argument("--chunk-size", type=int, default=800, help="maximum characters per chunk (default 800)")
    parser.add_argument("--prepend-section", action="store_true", help="start each chunk's text with its heading path")
    parser.add_argument("--quiet", action="store_true", help="do not print the summary")
    parser.add_argument("--version", action="version", version=f"doc-ingest {__version__}")
    return parser


def collect_files(paths: list[str]) -> tuple[list[tuple[Path, str]], int]:
    """Return (file, source name) pairs for supported files, plus a count of skipped ones.

    Source names are relative to the directory argument they were found
    under, so output does not depend on where the corpus lives on disk.
    """
    found: list[tuple[Path, str]] = []
    skipped = 0
    for raw in paths:
        root = Path(raw)
        if root.is_dir():
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                if any(part.startswith(".") for part in path.relative_to(root).parts):
                    continue
                if path.suffix.lower() in SUPPORTED_SUFFIXES:
                    found.append((path, path.relative_to(root).as_posix()))
                else:
                    skipped += 1
        elif root.is_file():
            found.append((root, root.name))
        else:
            raise FileNotFoundError(f"no such file or directory: {raw}")
    return found, skipped


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.chunk_size < 1:
        print("error: --chunk-size must be at least 1", file=sys.stderr)
        return 2
    try:
        files, skipped = collect_files(args.paths)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    records: list[dict] = []
    per_format: Counter[str] = Counter()
    failures: list[str] = []
    for path, source in files:
        try:
            doc = load_document(path)
        except MissingDependency as exc:
            failures.append(f"{source}: {exc}")
            continue
        except Exception as exc:  # one unreadable file should not stop the run
            failures.append(f"{source}: {type(exc).__name__}: {exc}")
            continue
        doc.source = source
        chunks = chunk_document(doc, chunk_size=args.chunk_size, prepend_section=args.prepend_section)
        per_format[doc.format] += 1
        records.extend(chunk.to_dict() for chunk in chunks)

    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")

    if not args.quiet:
        formats = ", ".join(f"{count} {name}" for name, count in sorted(per_format.items())) or "none"
        sizes = [record["n_chars"] for record in records]
        lines = [f"files read:    {sum(per_format.values())} ({formats})"]
        if skipped:
            lines.append(f"files skipped: {skipped} (unsupported type)")
        lines.append(f"chunks:        {len(records)}")
        if sizes:
            lines.append(f"chunk chars:   min {min(sizes)}, mean {sum(sizes) // len(sizes)}, max {max(sizes)}")
        if args.out != "-":
            lines.append(f"written to:    {args.out}")
        print("\n".join(lines), file=sys.stderr if args.out == "-" else sys.stdout)
    for failure in failures:
        print(f"failed: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
