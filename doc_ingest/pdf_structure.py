"""Find headings in PDF text by font size.

PDFs have no heading markup, but headings are almost always set larger than
the body text. We read each text line with its font size and y position,
treat the most common size (by characters) as the body size, and call a
short line a heading when it is clearly larger. Heading levels follow the
size ranking: the largest heading size is level 1, the next level 2, and so on.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .blocks import Block

MIN_RATIO = 1.15  # a heading is at least this much larger than body text
MAX_HEADING_CHARS = 120
MAX_LEVELS = 6


@dataclass
class Line:
    text: str
    size: float
    y: float


def read_lines(page) -> list[Line]:
    """Return the text lines of a pypdf page with effective font size and y."""
    lines: list[Line] = []

    def visit(text, cm, tm, font_dict, font_size):
        clean = " ".join(text.split())
        if not clean:
            return
        scale = math.hypot(tm[2], tm[3]) * math.hypot(cm[2], cm[3])
        lines.append(Line(clean, round((font_size or 0) * scale, 1), tm[5] * cm[3] + cm[5]))

    page.extract_text(visitor_text=visit)
    return lines


def body_size(pages: list[list[Line]]) -> float | None:
    counts: Counter[float] = Counter()
    for lines in pages:
        for line in lines:
            if line.size > 0:
                counts[line.size] += len(line.text)
    return counts.most_common(1)[0][0] if counts else None


def _is_heading(line: Line, body: float) -> bool:
    return (
        line.size >= body * MIN_RATIO
        and len(line.text) <= MAX_HEADING_CHARS
        and not line.text.endswith((".", ",", ";"))
    )


def blocks_from_pages(pages: list[list[Line]]) -> list[list[Block]] | None:
    """Turn lines into heading and paragraph blocks, one list per page.

    Returns None when no line stands out, so the caller can fall back to
    plain text extraction.
    """
    body = body_size(pages)
    if body is None:
        return None
    sizes = sorted({l.size for lines in pages for l in lines if _is_heading(l, body)}, reverse=True)
    if not sizes:
        return None
    level_of = {size: min(rank, MAX_LEVELS) for rank, size in enumerate(sizes, start=1)}
    result: list[list[Block]] = []
    for number, lines in enumerate(pages, start=1):
        blocks: list[Block] = []
        para: list[str] = []
        last: Line | None = None

        def flush():
            if para:
                blocks.append(Block("paragraph", " ".join(para), page=number))
                para.clear()

        for line in lines:
            if line.size in level_of and _is_heading(line, body):
                flush()
                previous = blocks[-1] if blocks else None
                if previous and previous.kind == "heading" and previous.level == level_of[line.size] and last and last.size == line.size:
                    previous.text += " " + line.text  # a heading wrapped onto two lines
                else:
                    blocks.append(Block("heading", line.text, level=level_of[line.size], page=number))
            else:
                if last is not None and para and last.y - line.y > 1.6 * max(line.size, 1):
                    flush()
                para.append(line.text)
            last = line
        flush()
        result.append(blocks)
    return result
