"""Structure-aware chunking: split at headings first, then by size."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from .blocks import Block, Document

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    format: str
    title: str | None
    section: str
    page: int | None
    page_end: int | None
    chunk_index: int
    n_chars: int

    def to_dict(self) -> dict:
        return asdict(self)


def _pack(pieces: list[str], size: int, joiner: str) -> list[str]:
    """Greedily join pieces into strings no longer than ``size``."""
    out: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{joiner}{piece}" if current else piece
        if current and len(candidate) > size:
            out.append(current)
            current = piece
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def split_block(block: Block, size: int) -> list[str]:
    """Split one oversized block without breaking its structure more than needed.

    Tables are split between rows and every part repeats the header. Code and
    lists are split between lines. Paragraphs are split between sentences, and
    a sentence longer than ``size`` is split between words.
    """
    text = block.text
    if len(text) <= size:
        return [text]
    if block.kind == "table":
        lines = text.split("\n")
        header, rows = "\n".join(lines[:2]), lines[2:]
        if not rows:
            return [text]
        room = max(size - len(header) - 1, 1)
        return [f"{header}\n{part}" for part in _pack(rows, room, "\n")]
    if block.kind in ("code", "list"):
        return _pack(text.split("\n"), size, "\n")
    pieces: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        pieces.extend(_pack(sentence.split(" "), size, " ") if len(sentence) > size else [sentence])
    return _pack(pieces, size, " ")


def chunk_document(doc: Document, chunk_size: int = 800, prepend_section: bool = False) -> list[Chunk]:
    """Turn a document's blocks into chunks of at most ``chunk_size`` characters.

    A heading always starts a new chunk, and each chunk records the heading
    path it sits under ("Guide > Install > Linux"). A single line that is
    longer than ``chunk_size`` on its own (a very wide table row, a long line
    of code) is kept whole rather than cut mid-line.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    chunks: list[Chunk] = []
    path: list[tuple[int, str]] = []
    parts: list[str] = []
    pages: list[int] = []
    section = ""

    def emit() -> None:
        nonlocal parts, pages
        body = "\n\n".join(parts).strip()
        parts_pages, parts, pages = pages, [], []
        if not body:
            return
        text = f"{section}\n\n{body}" if prepend_section and section else body
        index = len(chunks)
        digest = hashlib.sha1(f"{doc.source}\x00{index}\x00{text}".encode("utf-8")).hexdigest()[:12]
        chunks.append(
            Chunk(
                id=digest,
                text=text,
                source=doc.source,
                format=doc.format,
                title=doc.title,
                section=section,
                page=min(parts_pages) if parts_pages else None,
                page_end=max(parts_pages) if parts_pages else None,
                chunk_index=index,
                n_chars=len(text),
            )
        )

    for block in doc.blocks:
        if block.kind == "heading":
            emit()
            path = [(level, text) for level, text in path if level < block.level] + [(block.level, block.text)]
            section = " > ".join(text for _, text in path)
            continue
        for piece in split_block(block, chunk_size):
            if parts and len("\n\n".join(parts)) + 2 + len(piece) > chunk_size:
                emit()
            parts.append(piece)
            if block.page is not None:
                pages.append(block.page)
    emit()
    return chunks
