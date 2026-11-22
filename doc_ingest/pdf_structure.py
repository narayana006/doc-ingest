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

from .blocks import Block, markdown_table

MIN_RATIO = 1.15  # a heading is at least this much larger than body text
MAX_HEADING_CHARS = 120
MAX_LEVELS = 6
ROW_TOLERANCE = 0.5  # fragments whose baselines differ by less than this many font sizes share a row
COLUMN_TOLERANCE = 8.0  # points; left edges of a column may drift this much between rows
MAX_ROW_GAP = 2.5  # a table row is at most this many font sizes below the previous one


@dataclass
class Line:
    text: str
    size: float
    y: float
    x: float = 0.0


def read_lines(page) -> list[Line]:
    """Return the text lines of a pypdf page with effective font size and y."""
    lines: list[Line] = []

    def visit(text, cm, tm, font_dict, font_size):
        clean = " ".join(text.split())
        if not clean:
            return
        scale = math.hypot(tm[2], tm[3]) * math.hypot(cm[2], cm[3])
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        lines.append(Line(clean, round((font_size or 0) * scale, 1), tm[5] * cm[3] + cm[5], x))

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


def _rows(lines: list[Line], body: float) -> list[list[Line]]:
    """Group text fragments that sit on one baseline, left to right, into rows."""
    rows: list[list[Line]] = []
    for line in lines:
        row = rows[-1] if rows else None
        if (
            row
            and not _is_heading(line, body)
            and not _is_heading(row[-1], body)
            and abs(row[-1].y - line.y) <= ROW_TOLERANCE * max(line.size, 1)
            and line.x > row[-1].x
        ):
            row.append(line)
        else:
            rows.append([line])
    return rows


def _same_columns(a: list[Line], b: list[Line]) -> bool:
    return len(a) == len(b) and all(abs(p.x - q.x) <= COLUMN_TOLERANCE for p, q in zip(a, b))


def group_tables(lines: list[Line], body: float) -> list[Line | list[list[Line]]]:
    """Split a page into plain lines and tables.

    A table is two or more consecutive rows that each hold two or more text
    fragments, with the same number of fragments and left edges that line up
    column by column. Anything else stays a plain line.
    """
    items: list[Line | list[list[Line]]] = []
    rows = _rows(lines, body)
    i = 0
    while i < len(rows):
        j = i + 1
        if len(rows[i]) >= 2:
            while (
                j < len(rows)
                and _same_columns(rows[i], rows[j])
                and rows[j - 1][0].y - rows[j][0].y <= MAX_ROW_GAP * max(rows[j][0].size, 1)
            ):
                j += 1
        if j - i >= 2:
            items.append(rows[i:j])
        else:
            items.extend(rows[i])
            j = i + 1
        i = j
    return items


def blocks_from_pages(pages: list[list[Line]]) -> list[list[Block]] | None:
    """Turn lines into heading and paragraph blocks, one list per page.

    Returns None when there is no heading and no table, so the caller can
    fall back to plain text extraction.
    """
    body = body_size(pages)
    if body is None:
        return None
    sizes = sorted({l.size for lines in pages for l in lines if _is_heading(l, body)}, reverse=True)
    grouped = [group_tables(lines, body) for lines in pages]
    if not sizes and not any(isinstance(item, list) for items in grouped for item in items):
        return None
    level_of = {size: min(rank, MAX_LEVELS) for rank, size in enumerate(sizes, start=1)}
    result: list[list[Block]] = []
    for number, items in enumerate(grouped, start=1):
        blocks: list[Block] = []
        para: list[str] = []
        last: Line | None = None

        def flush():
            if para:
                blocks.append(Block("paragraph", " ".join(para), page=number))
                para.clear()

        for item in items:
            if isinstance(item, list):
                flush()
                blocks.append(Block("table", markdown_table([[cell.text for cell in row] for row in item]), page=number))
                last = item[-1][-1]
                continue
            line = item
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
