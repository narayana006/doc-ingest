"""HTML to blocks using only the standard library parser."""

from __future__ import annotations

from html.parser import HTMLParser

from .blocks import Block, markdown_table

# Content inside these elements is dropped: not prose, or page chrome.
SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "aside", "form", "button", "iframe"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
BREAKS = {"p", "div", "section", "article", "main", "header", "blockquote", "ul", "ol", "dl", "dt", "dd",
          "figure", "figcaption", "hr", "body", "table", "tr"}
_TABLE_TAGS = {"table", "tr", "td", "th", "br"}
VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.title: str | None = None
        self._buf: list[str] = []
        self._kind = "paragraph"
        self._level = 0
        self._skip_depth = 0
        self._in_title = False
        self._pre_depth = 0
        self._rows: list[list[str]] | None = None
        self._row: list[str] | None = None

    def _flush(self) -> None:
        raw = "".join(self._buf)
        self._buf = []
        text = raw.strip("\n") if self._kind == "code" else " ".join(raw.split())
        if text.strip():
            if self._kind == "list" and self.blocks and self.blocks[-1].kind == "list":
                self.blocks[-1].text += f"\n- {text}"  # items of one list stay together
            elif self._kind == "list":
                self.blocks.append(Block("list", f"- {text}"))
            elif self._kind == "code":
                self.blocks.append(Block("code", f"```\n{text}\n```"))
            else:
                self.blocks.append(Block(self._kind, text, self._level))
        self._kind, self._level = "paragraph", 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP and tag not in VOID:
            self._skip_depth += 1
        if self._skip_depth:
            return
        if self._rows is not None and tag not in _TABLE_TAGS:
            return  # inside a table only cell structure matters
        if tag == "title":
            self._in_title = True
        elif tag in HEADINGS:
            self._flush()
            self._kind, self._level = "heading", HEADINGS[tag]
        elif tag == "pre":
            self._flush()
            self._kind = "code"
            self._pre_depth += 1
        elif tag == "table":
            self._flush()
            if self._rows is None:
                self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._buf = []
        elif tag == "li":
            self._flush()
            self._kind = "list"
        elif tag == "br":
            self._buf.append("\n" if self._pre_depth else " ")
        elif tag in BREAKS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in SKIP and tag not in VOID:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if self._rows is not None and tag not in _TABLE_TAGS:
            return
        if tag == "title":
            self._in_title = False
        elif tag in ("td", "th") and self._row is not None:
            self._row.append("".join(self._buf))
            self._buf = []
        elif tag == "tr" and self._rows is not None and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._rows is not None:
            table = markdown_table(self._rows)
            self._rows, self._row, self._buf = None, None, []
            if table:
                self.blocks.append(Block("table", table))
        elif tag == "pre":
            self._pre_depth = max(0, self._pre_depth - 1)
            self._flush()
        elif tag in HEADINGS or tag == "li" or tag in BREAKS:
            self._flush()

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title = ((self.title or "") + data).strip() or None
            return
        if self._rows is not None and self._row is None:
            return  # whitespace or captions between rows
        self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def parse_html(text: str) -> tuple[list[Block], str | None]:
    parser = _Extractor()
    parser.feed(text)
    parser.close()
    title = parser.title
    if title is None:
        title = next((b.text for b in parser.blocks if b.kind == "heading" and b.level == 1), None)
    return parser.blocks, title
