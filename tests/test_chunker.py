import pytest

from doc_ingest.blocks import Block, Document
from doc_ingest.chunker import chunk_document, split_block


def doc(*blocks):
    return Document(source="t.md", format="markdown", title="T", blocks=list(blocks))


def H(level, text):
    return Block("heading", text, level=level)


def P(text, page=None):
    return Block("paragraph", text, page=page)


def test_headings_start_new_chunks_and_build_section_paths():
    chunks = chunk_document(doc(P("preface"), H(1, "A"), P("a1"), H(2, "B"), P("b1"), H(3, "C"), P("c1"), H(2, "D"), P("d1"), H(1, "E"), P("e1")))
    assert [(c.section, c.text) for c in chunks] == [
        ("", "preface"), ("A", "a1"), ("A > B", "b1"), ("A > B > C", "c1"), ("A > D", "d1"), ("E", "e1"),
    ]
    assert [c.chunk_index for c in chunks] == list(range(6))
    assert all(c.source == "t.md" and c.title == "T" and c.n_chars == len(c.text) for c in chunks)


def test_blocks_are_packed_up_to_chunk_size():
    chunks = chunk_document(doc(H(1, "A"), P("x" * 40), P("y" * 40), P("z" * 40)), chunk_size=90)
    assert [c.text for c in chunks] == ["x" * 40 + "\n\n" + "y" * 40, "z" * 40]
    assert all(c.n_chars <= 90 for c in chunks)


def test_long_paragraph_splits_on_sentences():
    text = "One two three. Four five six. Seven eight nine. Ten eleven twelve."
    chunks = chunk_document(doc(P(text)), chunk_size=32)
    assert [c.text for c in chunks] == ["One two three. Four five six.", "Seven eight nine.", "Ten eleven twelve."]


def test_sentence_longer_than_chunk_splits_on_words():
    pieces = split_block(P("alpha beta gamma delta epsilon"), 12)
    assert pieces == ["alpha beta", "gamma delta", "epsilon"]
    assert all(len(p) <= 12 for p in pieces)


def test_large_table_repeats_header_in_every_part():
    header = "| k | v |\n| --- | --- |"
    rows = [f"| key{i} | value{i} |" for i in range(6)]
    pieces = split_block(Block("table", header + "\n" + "\n".join(rows)), 70)
    assert len(pieces) > 1
    assert all(p.startswith(header) for p in pieces)
    assert [line for p in pieces for line in p.split("\n")[2:]] == rows


def test_code_splits_between_lines_never_inside():
    code = "\n".join(f"line_{i} = {i}" for i in range(10))
    pieces = split_block(Block("code", code), 40)
    assert "\n".join(pieces) == code


def test_heading_without_body_makes_no_chunk_but_sets_section():
    chunks = chunk_document(doc(H(1, "A"), H(2, "Empty"), H(2, "Full"), P("body")))
    assert [(c.section, c.text) for c in chunks] == [("A > Full", "body")]


def test_prepend_section():
    chunks = chunk_document(doc(H(1, "A"), H(2, "B"), P("body")), prepend_section=True)
    assert chunks[0].text == "A > B\n\nbody"


def test_pages_span_is_recorded():
    chunks = chunk_document(doc(P("p1", page=1), P("p2", page=2), P("q" * 50, page=3)), chunk_size=20)
    assert [(c.page, c.page_end) for c in chunks] == [(1, 2), (3, 3)]  # an unbreakable 50-char word is kept whole
    assert chunk_document(doc(P("no pages")))[0].page is None


def test_ids_are_stable_and_unique():
    blocks = [H(1, "A"), P("same"), H(1, "B"), P("same")]
    first, second = chunk_document(doc(*blocks)), chunk_document(doc(*blocks))
    assert [c.id for c in first] == [c.id for c in second]
    assert len({c.id for c in first}) == 2


def test_empty_document_and_bad_size():
    assert chunk_document(doc()) == []
    with pytest.raises(ValueError):
        chunk_document(doc(P("x")), chunk_size=0)
