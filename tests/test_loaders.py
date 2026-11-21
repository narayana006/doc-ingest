import pytest

from builders import build_docx, build_pdf
from doc_ingest.chunker import chunk_document
from doc_ingest.html_loader import parse_html
from doc_ingest.loaders import load_document, parse_markdown


def kinds(blocks):
    return [(b.kind, b.level) for b in blocks]


def test_plain_text_splits_on_blank_lines_and_unwraps(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes("﻿First line\r\nwraps here.\r\n\r\n\r\nSecond paragraph.\r\n".encode("utf-8"))
    doc = load_document(path)
    assert doc.format == "text"
    assert [b.text for b in doc.blocks] == ["First line wraps here.", "Second paragraph."]


def test_markdown_block_types():
    text = (
        "# Title\n\nIntro line one\nline two.\n\n## Setup ##\n\n- one\n- two\n  continued\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\n# not a heading\nx = 1\n```\n\nSetext\n------\n\n---\n\nEnd.\n"
    )
    blocks, title = parse_markdown(text)
    assert title == "Title"
    assert kinds(blocks) == [
        ("heading", 1), ("paragraph", 0), ("heading", 2), ("list", 0), ("table", 0),
        ("code", 0), ("heading", 2), ("paragraph", 0),
    ]
    assert blocks[1].text == "Intro line one line two."
    assert blocks[2].text == "Setup"
    assert blocks[3].text == "- one\n- two\n  continued"
    assert blocks[4].text == "| a | b |\n|---|---|\n| 1 | 2 |"
    assert "# not a heading" in blocks[5].text
    assert blocks[6].text == "Setext"
    assert blocks[7].text == "End."


def test_markdown_front_matter_title_and_unclosed_fence():
    blocks, title = parse_markdown('---\ntitle: "From front matter"\ntags: x\n---\n\n# Heading\n\n```\nopen forever\n')
    assert title == "From front matter"
    assert kinds(blocks) == [("heading", 1), ("code", 0)]


def test_html_drops_chrome_and_keeps_structure():
    html = """<html><head><title>Page &amp; title</title><style>p{color:red}</style></head><body>
    <nav>Home | About</nav><script>var x = "<p>not text</p>";</script>
    <h1>Main</h1><p>Hello <b>bold</b> world &amp; more.<br>Next line.</p>
    <ul><li>one</li><li>two <a href="#">link</a></li></ul>
    <h2>Data</h2>
    <table><tr><th>K</th><th>V</th></tr><tr><td><p>a|b</p></td><td>1</td></tr><tr><td>only</td></tr></table>
    <pre>line 1
  line 2</pre>
    <footer>copyright</footer></body></html>"""
    blocks, title = parse_html(html)
    assert title == "Page & title"
    assert kinds(blocks) == [("heading", 1), ("paragraph", 0), ("list", 0), ("heading", 2), ("table", 0), ("code", 0)]
    assert blocks[1].text == "Hello bold world & more. Next line."
    assert blocks[2].text == "- one\n- two link"
    assert blocks[4].text == "| K | V |\n| --- | --- |\n| a\\|b | 1 |\n| only |  |"
    assert blocks[5].text == "```\nline 1\n  line 2\n```"
    everything = " ".join(b.text for b in blocks)
    assert "Home" not in everything and "copyright" not in everything and "not text" not in everything


def test_html_without_title_falls_back_to_h1_and_survives_bad_markup():
    blocks, title = parse_html("<h1>Only heading<p>Unclosed paragraph<div>text in div")
    assert title == "Only heading"
    assert [b.text for b in blocks] == ["Only heading", "Unclosed paragraph", "text in div"]


def test_docx_headings_lists_tables(tmp_path):
    path = tmp_path / "d.docx"
    build_docx(
        path,
        [("h1", "Guide"), ("p", "Intro & more."), ("h2", "Steps"), ("li", "first"), ("li", "second"),
         ("table", [["Name", "Qty"], ["bolt", "4"]])],
        title="Core title",
    )
    doc = load_document(path)
    assert doc.format == "docx" and doc.title == "Core title"
    assert kinds(doc.blocks) == [("heading", 1), ("paragraph", 0), ("heading", 2), ("list", 0), ("table", 0)]
    assert doc.blocks[1].text == "Intro & more."
    assert doc.blocks[3].text == "- first\n- second"
    assert doc.blocks[4].text == "| Name | Qty |\n| --- | --- |\n| bolt | 4 |"


def test_docx_that_is_not_a_zip_is_a_clear_error(tmp_path):
    path = tmp_path / "bad.docx"
    path.write_text("plain text")
    with pytest.raises(ValueError, match="not a readable .docx"):
        load_document(path)


def test_unsupported_suffix(tmp_path):
    path = tmp_path / "x.xyz"
    path.write_text("x")
    with pytest.raises(ValueError, match="unsupported"):
        load_document(path)


def test_pdf_pages_are_recorded(tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "p.pdf"
    build_pdf(path, [["Page one says hello.", "Second line (with parens)."], ["Page two is here."]])
    doc = load_document(path)
    assert doc.format == "pdf"
    assert [b.page for b in doc.blocks] == [1, 2]
    assert "Page one says hello." in doc.blocks[0].text and "(with parens)" in doc.blocks[0].text
    assert doc.blocks[1].text == "Page two is here."


def _heading_pdf(tmp_path):
    path = tmp_path / "h.pdf"
    build_pdf(
        path,
        [
            [
                ("Rover Manual", 24),
                ("Daily checks", 16),
                ("Inspect the wheels before every shift and wipe the lidar dome clean.", 12),
                ("Battery", 14),
                ("Charge to full overnight.", 12),
            ],
            [("Fault codes", 16), ("Codes are shown on the display.", 12)],
        ],
    )
    return path


def test_pdf_headings_found_by_font_size(tmp_path):
    pytest.importorskip("pypdf")
    doc = load_document(_heading_pdf(tmp_path))
    kinds = [(b.kind, b.level, b.text, b.page) for b in doc.blocks]
    assert kinds == [
        ("heading", 1, "Rover Manual", 1),
        ("heading", 2, "Daily checks", 1),
        ("paragraph", 0, "Inspect the wheels before every shift and wipe the lidar dome clean.", 1),
        ("heading", 3, "Battery", 1),
        ("paragraph", 0, "Charge to full overnight.", 1),
        ("heading", 2, "Fault codes", 2),
        ("paragraph", 0, "Codes are shown on the display.", 2),
    ]
    assert doc.title == "Rover Manual"


def test_pdf_headings_drive_chunk_sections(tmp_path):
    pytest.importorskip("pypdf")
    doc = load_document(_heading_pdf(tmp_path))
    sections = [c.section for c in chunk_document(doc, chunk_size=400)]
    assert "Rover Manual > Daily checks > Battery" in sections
    assert "Rover Manual > Fault codes" in sections


def test_pdf_same_size_text_has_no_headings(tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "flat.pdf"
    build_pdf(path, [["Just a line.", "Another line."]])
    doc = load_document(path)
    assert all(b.kind == "paragraph" for b in doc.blocks)
