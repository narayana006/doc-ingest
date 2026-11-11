"""OCR fallback for PDF pages that have no text layer, such as scanned pages.

A scanned PDF page is usually one picture of the page. This module pulls
the images out of such a page in a form an OCR program can read (JPEG,
JPEG 2000 and TIFF are passed through unchanged; raw grey or RGB pixels
are wrapped as PNG with the standard library) and hands them to an OCR
engine. The default engine runs the ``tesseract`` command; any callable
with the same signature can be used instead.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import zlib
from collections.abc import Callable
from pathlib import Path

# An OCR engine takes encoded image bytes plus a file suffix (".png",
# ".jpg", ...) and returns the recognised text.
OcrEngine = Callable[[bytes, str], str]


class OcrUnavailable(RuntimeError):
    """Raised when the OCR program cannot be found."""


class TesseractOcr:
    """Run the ``tesseract`` command line program on one image at a time."""

    def __init__(self, lang: str = "eng", binary: str = "tesseract", timeout: float = 120.0):
        self.lang = lang
        self.binary = binary
        self.timeout = timeout

    def executable(self) -> str:
        found = shutil.which(self.binary)
        if found is None:
            raise OcrUnavailable(
                f"OCR needs the '{self.binary}' program on PATH "
                "(macOS: brew install tesseract; Debian/Ubuntu: apt install tesseract-ocr)"
            )
        return found

    def __call__(self, image: bytes, suffix: str) -> str:
        exe = self.executable()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"page{suffix}"
            path.write_bytes(image)
            result = subprocess.run(
                [exe, str(path), "stdout", "-l", self.lang],
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip().splitlines()
            raise RuntimeError(f"tesseract failed: {message[-1] if message else f'exit code {result.returncode}'}")
        return result.stdout.decode("utf-8", errors="replace")


def png_bytes(width: int, height: int, channels: int, bits: int, samples: bytes) -> bytes:
    """Wrap raw, unfiltered pixel rows (grey or RGB) as a PNG file."""
    row = (width * channels * bits + 7) // 8
    if len(samples) < row * height:
        raise ValueError(f"image data too short: {len(samples)} bytes for {width}x{height}")
    raw = b"".join(b"\x00" + samples[y * row : (y + 1) * row] for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    colour_type = 0 if channels == 1 else 2
    header = struct.pack(">IIBBBBB", width, height, bits, colour_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


_PASSTHROUGH = {"/DCTDecode": ".jpg", "/DCT": ".jpg", "/JPXDecode": ".jp2", "/CCITTFaxDecode": ".tiff", "/CCF": ".tiff"}


def _channels(colour_space) -> int | None:
    """Number of colour channels for DeviceGray/DeviceRGB/ICCBased, else None."""
    if isinstance(colour_space, list) and colour_space and colour_space[0] == "/ICCBased":
        n = colour_space[1].get_object().get("/N")
        return int(n) if n in (1, 3) else None
    return {"/DeviceGray": 1, "/G": 1, "/DeviceRGB": 3, "/RGB": 3}.get(colour_space)


def image_for_ocr(xobject) -> tuple[bytes, str] | None:
    """Return (encoded bytes, suffix) for one PDF image XObject, or None if unsupported."""
    filters = xobject.get("/Filter")
    if filters is None:
        filters = []
    elif not isinstance(filters, list):
        filters = [filters]
    last = filters[-1] if filters else None
    if last in _PASSTHROUGH:
        data = xobject.get_data()
        if _PASSTHROUGH[last] == ".tiff" and data[:4] not in (b"II*\x00", b"MM\x00*"):
            return None  # older pypdf versions return CCITT data without a TIFF header
        return data, _PASSTHROUGH[last]
    if last not in (None, "/FlateDecode", "/Fl", "/LZWDecode", "/LZW", "/RunLengthDecode", "/RL"):
        return None  # JBIG2 and other codecs are not handled
    if xobject.get("/ImageMask"):
        return None
    channels = _channels(xobject.get("/ColorSpace"))
    bits = int(xobject.get("/BitsPerComponent", 8))
    if channels is None or bits not in (1, 8) or (channels == 3 and bits != 8):
        return None
    width, height = int(xobject["/Width"]), int(xobject["/Height"])
    return png_bytes(width, height, channels, bits, xobject.get_data()), ".png"


def page_images(page) -> list[tuple[bytes, str]]:
    """Every image on a pypdf page that can be handed to OCR, in resource order."""
    resources = page.get("/Resources")
    xobjects = resources.get_object().get("/XObject") if resources is not None else None
    if xobjects is None:
        return []
    found = []
    for name in xobjects.get_object():
        xobject = xobjects[name].get_object()
        if xobject.get("/Subtype") == "/Image":
            image = image_for_ocr(xobject)
            if image is not None:
                found.append(image)
    return found
