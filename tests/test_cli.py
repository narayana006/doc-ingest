import json
from pathlib import Path

import pytest

from builders import build_pdf
from doc_ingest import loaders
from doc_ingest.cli import main

CORPUS = Path(__file__).resolve().parent.parent / "examples" / "corpus"


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_example_corpus_end_to_end(tmp_path, capsys):
    out = tmp_path / "chunks.jsonl"
    assert main([str(CORPUS), "--out", str(out), "--chunk-size", "400"]) == 0
    records = read(out)
    assert {r["source"] for r in records} == {"handbook.md", "onboarding.docx", "release-notes.html", "shift-log.txt"}
    assert all(r["n_chars"] <= 400 for r in records)
    fault = next(r for r in records if r["section"] == "Larkspur Field Handbook > Fault codes")
    assert "| E27 | Lidar blocked | Clean the dome and restart |" in fault["text"]
    assert any(r["section"] == "Rover firmware 4.2 > Compatibility" and "| L1 | No |" in r["text"] for r in records)
    assert "files read:    4 (1 docx, 1 html, 1 markdown, 1 text)" in capsys.readouterr().out


def test_stdout_output_keeps_summary_on_stderr(tmp_path, capsys):
    (tmp_path / "a.txt").write_text("hello there")
    assert main([str(tmp_path / "a.txt")]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["text"] == "hello there"
    assert "chunks:" in captured.err


def test_skips_unsupported_and_hidden_files(tmp_path, capsys):
    (tmp_path / "a.md").write_text("# A\n\nbody")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "notes.txt").write_text("hidden")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.txt").write_text("nested body")
    out = tmp_path / "o.jsonl"
    assert main([str(tmp_path), "--out", str(out)]) == 0
    assert [r["source"] for r in read(out)] == ["a.md", "nested/b.txt"]
    assert "files skipped: 1" in capsys.readouterr().out


def test_bad_file_is_reported_and_others_still_processed(tmp_path, capsys):
    (tmp_path / "bad.docx").write_text("not a zip")
    (tmp_path / "good.txt").write_text("fine")
    out = tmp_path / "o.jsonl"
    assert main([str(tmp_path), "--out", str(out), "--quiet"]) == 1
    assert [r["source"] for r in read(out)] == ["good.txt"]
    assert "failed: bad.docx" in capsys.readouterr().err


def test_missing_path_and_bad_chunk_size(tmp_path, capsys):
    assert main([str(tmp_path / "nope")]) == 2
    assert main([str(tmp_path), "--chunk-size", "0"]) == 2


def test_pdf_without_pypdf_gives_install_hint(tmp_path, capsys, monkeypatch):
    def no_pypdf(path):
        raise loaders.MissingDependency("PDF support needs pypdf")

    monkeypatch.setitem(loaders.LOADERS, ".pdf", no_pypdf)
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    assert main([str(tmp_path), "--quiet"]) == 1
    assert "PDF support needs pypdf" in capsys.readouterr().err


def test_pdf_chunks_carry_page_numbers(tmp_path):
    pytest.importorskip("pypdf")
    build_pdf(tmp_path / "manual.pdf", [["First page text."], ["Second page text."]])
    out = tmp_path / "o.jsonl"
    assert main([str(tmp_path), "--out", str(out), "--chunk-size", "20", "--quiet"]) == 0
    assert [(r["page"], r["text"]) for r in read(out)] == [(1, "First page text."), (2, "Second page text.")]


def test_chroma_format_matches_collection_add(tmp_path):
    (tmp_path / "a.md").write_text("# Title\n\nbody text here")
    out = tmp_path / "c.json"
    assert main([str(tmp_path / "a.md"), "--out", str(out), "--format", "chroma", "--quiet"]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload) == {"ids", "documents", "metadatas"}
    assert len(payload["ids"]) == len(payload["documents"]) == len(payload["metadatas"]) == 1
    assert payload["documents"][0].endswith("body text here")
    meta = payload["metadatas"][0]
    assert meta["source"] == "a.md" and meta["section"] == "Title"
    assert "page" not in meta and None not in meta.values()


def test_pinecone_format_is_flat_records(tmp_path):
    (tmp_path / "a.txt").write_text("hello there")
    out = tmp_path / "p.jsonl"
    assert main([str(tmp_path / "a.txt"), "--out", str(out), "--format", "pinecone", "--quiet"]) == 0
    (row,) = read(out)
    assert row["chunk_text"] == "hello there" and len(row["_id"]) == 12
    assert row["source"] == "a.txt" and "id" not in row and "text" not in row
    assert None not in row.values()


def test_unknown_format_is_rejected(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path / "a.txt"), "--format", "parquet"])
    assert exc.value.code == 2
