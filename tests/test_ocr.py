import os
import stat
import struct
import zlib

import pytest

from builders import build_pdf, build_scan_pdf
from doc_ingest import cli, load_document
from doc_ingest.cli import main
from doc_ingest.ocr import OcrUnavailable, TesseractOcr, png_bytes

GREY_2x2 = bytes([0, 255, 255, 0])


class FakeOcr:
    """Records every image it is given and returns canned text per call."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = []

    def __call__(self, image, suffix):
        self.calls.append((image, suffix))
        return self.texts.pop(0) if self.texts else ""


def read_png(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, {}
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(kind + body) & 0xFFFFFFFF
        chunks[kind] = body
        pos += 12 + length
    width, height, bits, colour, *_ = struct.unpack(">IIBBBBB", chunks[b"IHDR"])
    return width, height, bits, colour, zlib.decompress(chunks[b"IDAT"])


def test_png_bytes_wraps_rows_with_filter_bytes():
    width, height, bits, colour, raw = read_png(png_bytes(2, 2, 1, 8, GREY_2x2))
    assert (width, height, bits, colour) == (2, 2, 8, 0)
    assert raw == b"\x00\x00\xff\x00\xff\x00"


def test_png_bytes_handles_one_bit_and_rgb():
    *_, raw = read_png(png_bytes(10, 1, 1, 1, b"\xaa\xc0"))
    assert raw == b"\x00\xaa\xc0"
    _, _, bits, colour, raw = read_png(png_bytes(1, 1, 3, 8, b"\x01\x02\x03"))
    assert (bits, colour, raw) == (8, 2, b"\x00\x01\x02\x03")


def test_png_bytes_rejects_short_data():
    with pytest.raises(ValueError):
        png_bytes(4, 4, 1, 8, b"\x00")


def test_scanned_pages_are_ocred_and_keep_page_numbers(tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "scan.pdf"
    jpeg = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"
    build_scan_pdf(path, [{"width": 2, "height": 2, "data": GREY_2x2}, {"width": 2, "height": 2, "data": jpeg, "filter": "/DCTDecode"}])
    engine = FakeOcr("Pump room checklist\n\nClose valve A.", "Second page text.")
    doc = load_document(path, ocr=engine)
    assert [(b.text, b.page) for b in doc.blocks] == [
        ("Pump room checklist", 1),
        ("Close valve A.", 1),
        ("Second page text.", 2),
    ]
    assert doc.ocr_pages == [1, 2] and doc.empty_pages == []
    (png, png_suffix), (jpg, jpg_suffix) = engine.calls
    assert png_suffix == ".png" and read_png(png)[4] == b"\x00\x00\xff\x00\xff\x00"
    assert (jpg, jpg_suffix) == (jpeg, ".jpg")


def test_pages_with_text_are_not_ocred(tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "text.pdf"
    build_pdf(path, [["Real text layer."]])
    engine = FakeOcr("should not appear")
    doc = load_document(path, ocr=engine)
    assert engine.calls == [] and doc.ocr_pages == []
    assert doc.blocks[0].text == "Real text layer."


def test_without_ocr_scanned_pages_are_reported_empty(tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "scan.pdf"
    build_scan_pdf(path, [{"width": 2, "height": 2, "data": GREY_2x2}, None])
    doc = load_document(path)
    assert doc.blocks == [] and doc.empty_pages == [1, 2]


def test_cli_ocr_flag_uses_engine_and_reports_pages(tmp_path, capsys, monkeypatch):
    pytest.importorskip("pypdf")
    build_scan_pdf(tmp_path / "scan.pdf", [{"width": 2, "height": 2, "data": GREY_2x2}, None, None])
    engine = FakeOcr("Recovered words.")
    monkeypatch.setattr(TesseractOcr, "executable", lambda self: "/bin/tesseract")
    monkeypatch.setattr(TesseractOcr, "__call__", lambda self, image, suffix: engine(image, suffix))
    out = tmp_path / "out.jsonl"
    assert main([str(tmp_path), "--out", str(out), "--ocr"]) == 0
    assert '"page": 1' in out.read_text() and "Recovered words." in out.read_text()
    captured = capsys.readouterr()
    assert "pages OCRed:   1" in captured.out
    assert "no text found on pages of: scan.pdf (pages 2-3)" in captured.err
    assert "--ocr" not in captured.err


def test_cli_hints_at_ocr_for_empty_pages(tmp_path, capsys):
    pytest.importorskip("pypdf")
    build_scan_pdf(tmp_path / "scan.pdf", [{"width": 2, "height": 2, "data": GREY_2x2}])
    assert main([str(tmp_path / "scan.pdf"), "--out", str(tmp_path / "o.jsonl")]) == 0
    assert "scan.pdf (page 1); scanned pages need --ocr" in capsys.readouterr().err


def test_cli_ocr_without_tesseract_is_a_usage_error(tmp_path, capsys, monkeypatch):
    def missing(self):
        raise OcrUnavailable("OCR needs the 'tesseract' program on PATH")

    monkeypatch.setattr(TesseractOcr, "executable", missing)
    (tmp_path / "a.txt").write_text("hello")
    assert main([str(tmp_path), "--ocr"]) == 2
    assert "needs the 'tesseract' program" in capsys.readouterr().err


def test_page_list_compacts_runs():
    assert cli._page_list([1, 2, 3, 5, 7, 8]) == "pages 1-3, 5, 7-8"
    assert cli._page_list([4]) == "page 4"


@pytest.mark.skipif(os.name == "nt", reason="uses a shell script as a stand-in program")
def test_tesseract_engine_runs_the_program(tmp_path):
    fake = tmp_path / "fake-tesseract"
    fake.write_text('#!/bin/sh\nprintf "lang=%s file=%s\\n" "$4" "$(basename "$1")"\nprintf "out=%s" "$2"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    text = TesseractOcr(lang="deu", binary=str(fake))(b"img", ".png")
    assert text == "lang=deu file=page.png\nout=stdout"


@pytest.mark.skipif(os.name == "nt", reason="uses a shell script as a stand-in program")
def test_tesseract_engine_reports_failures(tmp_path):
    fake = tmp_path / "broken-tesseract"
    fake.write_text("#!/bin/sh\necho 'Error opening data file' >&2\nexit 1\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    with pytest.raises(RuntimeError, match="Error opening data file"):
        TesseractOcr(binary=str(fake))(b"img", ".png")


def test_tesseract_engine_missing_program():
    with pytest.raises(OcrUnavailable, match="brew install tesseract"):
        TesseractOcr(binary="no-such-ocr-program-xyz").executable()
