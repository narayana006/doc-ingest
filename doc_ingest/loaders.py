"""Loaders: one function per format, each returning a Document of blocks."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .blocks import Block, Document, markdown_table
from .html_loader import parse_html
from .ocr import OcrEngine, page_images


class MissingDependency(RuntimeError):
    """Raised when a format needs an optional package that is not installed."""


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _paragraphs(text: str, page: int | None = None) -> list[Block]:
    parts = (" ".join(part.split()) for part in re.split(r"\n\s*\n", text))
    return [Block("paragraph", part, page=page) for part in parts if part]


def load_text(path: Path) -> Document:
    return Document(source=str(path), format="text", blocks=_paragraphs(_read_text(path)))


_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LIST = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def parse_markdown(text: str) -> tuple[list[Block], str | None]:
    """Split Markdown into heading, paragraph, list, table and code blocks.

    Handles ATX (#) and setext (underlined) headings, fenced code, pipe
    tables and a leading ``---`` front matter block. Inline markup is kept
    as written.
    """
    lines = text.split("\n")
    title = None
    if lines and lines[0].strip() == "---" and "---" in (l.strip() for l in lines[1:]):
        end = next(i for i, l in enumerate(lines[1:], start=1) if l.strip() == "---")
        for line in lines[1:end]:
            key, _, value = line.partition(":")
            if key.strip().lower() == "title" and value.strip():
                title = value.strip().strip("\"'")
        lines = lines[end + 1 :]

    blocks: list[Block] = []
    buf: list[str] = []
    kind = "paragraph"

    def flush() -> None:
        nonlocal buf, kind
        if buf:
            joined = "\n".join(buf) if kind in ("list", "table") else " ".join(s.strip() for s in buf)
            blocks.append(Block(kind, joined))
        buf, kind = [], "paragraph"

    i = 0
    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            flush()
            end = next((j for j in range(i + 1, len(lines)) if lines[j].strip().startswith(fence.group(1))), len(lines))
            blocks.append(Block("code", "\n".join(lines[i : end + 1])))
            i = end + 1
            continue
        atx = _ATX.match(line)
        if atx:
            flush()
            blocks.append(Block("heading", atx.group(2), level=len(atx.group(1))))
        elif not line.strip():
            flush()
        elif not buf and re.fullmatch(r"\s*([-*_]\s*){3,}", line):
            pass  # horizontal rule
        elif buf and kind == "paragraph" and len(buf) == 1 and re.fullmatch(r"\s*(=+|-+)\s*", line):
            level = 1 if line.strip().startswith("=") else 2
            blocks.append(Block("heading", buf[0].strip(), level=level))
            buf = []
        elif "|" in line and i + 1 < len(lines) and _TABLE_RULE.match(lines[i + 1]) and "-" in lines[i + 1]:
            flush()
            kind = "table"
            buf.append(line.strip())
        elif kind == "table" and "|" in line:
            buf.append(line.strip())
        elif _LIST.match(line):
            if kind != "list":
                flush()
                kind = "list"
            buf.append(line.rstrip())
        else:
            if kind == "table":
                flush()
            buf.append(line.rstrip() if kind == "list" else line)
        i += 1
    flush()
    if title is None:
        title = next((b.text for b in blocks if b.kind == "heading" and b.level == 1), None)
    return blocks, title


def load_markdown(path: Path) -> Document:
    blocks, title = parse_markdown(_read_text(path))
    return Document(source=str(path), format="markdown", title=title, blocks=blocks)


def load_html(path: Path) -> Document:
    blocks, title = parse_html(_read_text(path))
    return Document(source=str(path), format="html", title=title, blocks=blocks)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DC_TITLE = "{http://purl.org/dc/elements/1.1/}title"


def _docx_text(node) -> str:
    parts = []
    for el in node.iter():
        if el.tag == f"{_W}t":
            parts.append(el.text or "")
        elif el.tag == f"{_W}tab":
            parts.append("\t")
        elif el.tag in (f"{_W}br", f"{_W}cr"):
            parts.append("\n")
    return "".join(parts)


def load_docx(path: Path) -> Document:
    """Read a .docx with zipfile and ElementTree: headings, paragraphs, lists, tables."""
    try:
        with zipfile.ZipFile(path) as archive:
            body = ElementTree.fromstring(archive.read("word/document.xml")).find(f"{_W}body")
            title = None
            if "docProps/core.xml" in archive.namelist():
                node = ElementTree.fromstring(archive.read("docProps/core.xml")).find(_DC_TITLE)
                title = (node.text or "").strip() or None if node is not None else None
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError(f"not a readable .docx file: {exc}") from exc
    blocks: list[Block] = []
    for child in body if body is not None else []:
        if child.tag == f"{_W}p":
            text = " ".join(_docx_text(child).split())
            if not text:
                continue
            style = child.find(f"{_W}pPr/{_W}pStyle")
            style_name = (style.get(f"{_W}val") or "") if style is not None else ""
            heading = re.fullmatch(r"[Hh]eading\s?([1-6])", style_name)
            if heading:
                blocks.append(Block("heading", text, level=int(heading.group(1))))
            elif style_name == "Title":
                blocks.append(Block("heading", text, level=1))
            elif child.find(f"{_W}pPr/{_W}numPr") is not None:
                if blocks and blocks[-1].kind == "list":
                    blocks[-1].text += f"\n- {text}"
                else:
                    blocks.append(Block("list", f"- {text}"))
            else:
                blocks.append(Block("paragraph", text))
        elif child.tag == f"{_W}tbl":
            rows = [[_docx_text(cell) for cell in row.findall(f"{_W}tc")] for row in child.findall(f"{_W}tr")]
            table = markdown_table(rows)
            if table:
                blocks.append(Block("table", table))
    if title is None:
        title = next((b.text for b in blocks if b.kind == "heading" and b.level == 1), None)
    return Document(source=str(path), format="docx", title=title, blocks=blocks)


def load_pdf(path: Path, ocr: OcrEngine | None = None) -> Document:
    """Extract text page by page with pypdf (optional dependency).

    With an ``ocr`` engine, a page that has no text layer is read by
    running OCR over the images on it instead.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise MissingDependency("PDF support needs pypdf: pip install 'doc-ingest[pdf] @ git+https://github.com/narayana006/doc-ingest'") from exc
    reader = PdfReader(str(path))
    blocks: list[Block] = []
    ocr_pages: list[int] = []
    empty_pages: list[int] = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip() and ocr is not None:
            text = "\n\n".join(ocr(data, suffix) for data, suffix in page_images(page))
            if text.strip():
                ocr_pages.append(number)
        if not text.strip():
            empty_pages.append(number)
        blocks.extend(_paragraphs(text, page=number))
    meta_title = getattr(reader.metadata, "title", None) if reader.metadata else None
    return Document(
        source=str(path), format="pdf", title=meta_title or None, blocks=blocks, ocr_pages=ocr_pages, empty_pages=empty_pages
    )


LOADERS = {
    ".txt": load_text,
    ".text": load_text,
    ".md": load_markdown,
    ".markdown": load_markdown,
    ".html": load_html,
    ".htm": load_html,
    ".docx": load_docx,
    ".pdf": load_pdf,
}
SUPPORTED_SUFFIXES = tuple(LOADERS)


def load_document(path: str | Path, ocr: OcrEngine | None = None) -> Document:
    """Load one file. ``ocr`` is only used for PDF pages with no text layer."""
    path = Path(path)
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        raise ValueError(f"unsupported file type: {path.suffix or path.name}")
    if ocr is not None and loader is LOADERS[".pdf"]:
        return loader(path, ocr=ocr)
    return loader(path)
