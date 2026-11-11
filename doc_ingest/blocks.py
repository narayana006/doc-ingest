"""The intermediate form every loader produces: a flat list of typed blocks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    kind: str  # "heading", "paragraph", "list", "table" or "code"
    text: str
    level: int = 0  # heading level 1-6; 0 for everything else
    page: int | None = None  # 1-based page number, PDF only


@dataclass
class Document:
    source: str
    format: str
    title: str | None = None
    blocks: list[Block] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)  # PDF pages whose text came from OCR
    empty_pages: list[int] = field(default_factory=list)  # PDF pages that gave no text at all


def markdown_table(rows: list[list[str]]) -> str:
    """Render rows as a Markdown pipe table; the first row is the header."""
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return ""
    width = max(len(row) for row in rows)

    def line(cells: list[str]) -> str:
        cells = [" ".join(c.split()).replace("|", "\\|") for c in cells] + [""] * (width - len(cells))
        return "| " + " | ".join(cells) + " |"

    out = [line(rows[0]), "| " + " | ".join(["---"] * width) + " |"]
    out += [line(row) for row in rows[1:]]
    return "\n".join(out)
