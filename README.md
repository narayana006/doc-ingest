# doc-ingest

One command from a folder of text, Markdown, HTML, DOCX and PDF files to clean, section-aware chunks in JSONL, each tagged with the file, heading path and page it came from.

**Status: first working version (0.1.0).** Text, Markdown, HTML and DOCX work with no dependencies; PDF text extraction works with the optional `pypdf` extra, and `--ocr` reads scanned PDF pages through the `tesseract` program. Tables are kept as Markdown, chunks follow heading boundaries, and output is JSONL. PDF headings are detected from font size and PDF tables laid out in aligned columns are kept as Markdown. Output can be reshaped for Chroma or Pinecone loading (`--format`). Not built yet: ruled or merged-cell PDF tables, direct uploads to a vector store, and chunk overlap.

## Install

```bash
pip install git+https://github.com/narayana006/doc-ingest
```

With PDF support (adds [pypdf](https://pypi.org/project/pypdf/), pure Python):

```bash
pip install "doc-ingest[pdf] @ git+https://github.com/narayana006/doc-ingest"
```

Python 3.10 or newer.

## Quick start

`examples/corpus` holds four small documents about a made-up delivery rover: a Markdown handbook, an HTML release-notes page, a Word document and a plain-text log.

```bash
git clone https://github.com/narayana006/doc-ingest
cd doc-ingest
doc-ingest examples/corpus --out chunks.jsonl --chunk-size 400
```

```text
files read:    4 (1 docx, 1 html, 1 markdown, 1 text)
chunks:        13
chunk chars:   min 98, mean 202, max 389
written to:    chunks.jsonl
```

Each line of `chunks.jsonl` is one chunk. This is the fourth, pretty-printed:

```json
{
    "id": "9f08bf9cb0ee",
    "text": "| Code | Meaning | Action |\n| --- | --- | --- |\n| E12 | Wheel motor over temperature | Stop for 10 minutes, then resume |\n| E27 | Lidar blocked | Clean the dome and restart |\n| E40 | Cargo latch open | Close the latch; replace it if the code returns |\n\nReport any code that is not in the table to depot-support@larkspur.example.com.",
    "source": "handbook.md",
    "format": "markdown",
    "title": "Larkspur Field Handbook",
    "section": "Larkspur Field Handbook > Fault codes",
    "page": null,
    "page_end": null,
    "chunk_index": 3,
    "n_chars": 332
}
```

The HTML table in `release-notes.html` comes out as Markdown too, under the section `Rover firmware 4.2 > Compatibility`:

```text
| Hardware revision | Supported | Notes |
| --- | --- | --- |
| L2 rev A | Yes | Needs bootloader 1.9 or newer |
| L2 rev B | Yes |  |
| L1 | No | Stay on firmware 3.x |
```

## Usage

```text
doc-ingest PATH [PATH ...] [--out FILE] [--format FORMAT] [--chunk-size N] [--prepend-section] [--ocr] [--ocr-lang LANG] [--quiet]
```

| Option | Default | Effect |
| --- | --- | --- |
| `PATH` | | Files or directories. Directories are searched recursively; hidden files and folders are ignored |
| `--out FILE` | stdout | Where to write the output. With stdout, the summary goes to stderr so the output can be piped |
| `--format FORMAT` | `jsonl` | `jsonl`, `chroma` or `pinecone` (see "Loading into a vector store") |
| `--chunk-size N` | 800 | Maximum characters per chunk |
| `--prepend-section` | off | Start each chunk's text with its heading path, which helps keyword and embedding search on short chunks |
| `--ocr` | off | Run OCR on PDF pages that have no text layer (needs `tesseract`, see below) |
| `--ocr-lang LANG` | `eng` | Tesseract language code(s) for `--ocr`, such as `deu` or `eng+fra` |
| `--quiet` | off | No summary |

Exit code is 0 on success, 1 if any file could not be read (the rest are still written, and each failure is listed on stderr), 2 for a bad argument or for `--ocr` when `tesseract` is not installed.

PDF pages that yield no text are listed on stderr (`no text found on pages of: scan.pdf (pages 1-3)`), with a hint to use `--ocr` when it was not given.

### What each format gives you

| Format | Extensions | Needs | Headings | Tables | Page numbers |
| --- | --- | --- | --- | --- | --- |
| Plain text | `.txt`, `.text` | nothing | no | no | no |
| Markdown | `.md`, `.markdown` | nothing | `#` and underlined | pipe tables kept as written | no |
| HTML | `.html`, `.htm` | nothing | `h1` to `h6` | converted to Markdown | no |
| Word | `.docx` | nothing | Heading 1 to 6 and Title styles | converted to Markdown | no |
| PDF | `.pdf` | `pypdf` extra (`tesseract` for `--ocr`) | by font size | aligned columns, converted to Markdown | yes |

HTML extraction drops `script`, `style`, `nav`, `footer`, `aside`, `form` and similar page chrome. Markdown front matter is removed and its `title` is used. Fenced code and `<pre>` blocks are kept intact as fenced code.

### PDF headings

PDFs carry no heading markup, so `doc-ingest` reads the font size of every text line, takes the most common size as the body size, and treats clearly larger short lines as headings. The largest heading size becomes level 1, the next level 2, and so on, so chunks get the same `section` paths as other formats. For a PDF with a 24pt title, 16pt section heads and 14pt subsections:

```text
Rover Manual > Daily checks | page 1
Rover Manual > Daily checks > Battery | page 1
Rover Manual > Fault codes | page 2
```

If the PDF has no metadata title, the first level-1 heading is used as `title`.

### PDF tables

PDF text is placed on the page piece by piece, so a table is found from geometry: two or more consecutive rows, each with two or more text pieces on one baseline, the same number of pieces per row, and left edges that line up column by column (within 8 points) with no big vertical gap. The first row becomes the header. Such a block becomes a `table` block, so it is kept whole (or split by row with the header repeated) when chunking:

```text
Fault codes (section)
Codes are shown on the display.

| Code | Meaning | Action |
| --- | --- | --- |
| E12 | Motor hot | Wait ten minutes |
| E27 | Lidar blocked | Clean the dome |
```

This works when the PDF writes each cell as its own text piece, which is how most generated PDFs (word processors, reports, exports) do it. It does not look at ruling lines, so tables with merged cells, cells that wrap over several lines, or columns that start at drifting positions are not recognised and come out as ordinary paragraphs.

### Scanned PDFs (OCR)

A scanned page has no text layer, so normal extraction gives nothing. With `--ocr`, each such page's images are passed to [Tesseract](https://github.com/tesseract-ocr/tesseract) and the recognised text is chunked like any other page, keeping its page number. Pages that already have text are never OCRed.

Install the program first (it is not a Python package): `brew install tesseract` on macOS, `apt install tesseract-ocr` on Debian or Ubuntu. Extra languages come as separate packages, such as `tesseract-ocr-deu`.

```bash
doc-ingest scanned-checklist.pdf --out chunks.jsonl --ocr
```

```text
files read:    1 (1 pdf)
chunks:        1
pages OCRed:   2
chunk chars:   min 172, mean 172, max 172
written to:    chunks.jsonl
```

Image encodings read: JPEG, JPEG 2000 and CCITT fax (passed to Tesseract as they are), plus uncompressed or Flate, LZW or run-length compressed greyscale and RGB images (wrapped as PNG with the standard library). JBIG2, indexed-colour and CMYK images are skipped, so a page made only of those stays empty and is listed on stderr. OCR quality is whatever Tesseract gives for the scan; nothing is deskewed or cleaned up first.

From Python, pass any callable that takes `(image_bytes, suffix)` and returns text, which is also how the tests run without Tesseract:

```python
from doc_ingest import load_document
from doc_ingest.ocr import TesseractOcr

doc = load_document("scanned-checklist.pdf", ocr=TesseractOcr(lang="eng"))
print(doc.ocr_pages)  # [1, 2]
```

### Loading into a vector store

`--format` reshapes the same chunks for a vector store. It only rewrites the file: no embeddings are computed and nothing is uploaded, so the store (or your own code) embeds the text. Metadata fields that are unset (such as `page` outside PDFs) are left out, because these stores reject null values.

| Format | File | Shape |
| --- | --- | --- |
| `chroma` | one JSON object | `{"ids": [...], "documents": [...], "metadatas": [...]}`, the arguments of Chroma's `collection.add` |
| `pinecone` | JSONL | one record per line with `_id`, `chunk_text` and flat metadata, the input of `index.upsert_records` (indexes with integrated embedding) |

```bash
doc-ingest examples/corpus --out chunks.json --format chroma --chunk-size 400
```

```python
import json, chromadb

collection = chromadb.Client().create_collection("rover-docs")
collection.add(**json.load(open("chunks.json")))
```

The Python snippet needs `pip install chromadb` and has not been run as part of this project's tests; the tests check the file shape. Pinecone's batch size limits apply when you upload, so send the records in batches.

### How chunking works

1. A heading always starts a new chunk. The chunk's `section` is the full heading path, such as `Larkspur Field Handbook > Daily checks > Battery`.
2. Within a section, paragraphs, lists, tables and code blocks are packed together until the next one would go past `--chunk-size`.
3. A block that is too big on its own is split where it hurts least: paragraphs between sentences (then between words), lists and code between lines, tables between rows with the header row repeated in every part.
4. A single line longer than the limit (one very wide table row, one long line of code, one unbroken word) is kept whole, so a chunk can exceed the limit in that case only.

### Output fields

| Field | Meaning |
| --- | --- |
| `id` | 12 hex characters, a hash of source, position and text; stable across runs on unchanged input |
| `text` | The chunk |
| `source` | File path relative to the directory you passed (or the file name for a single file) |
| `format` | `text`, `markdown`, `html`, `docx` or `pdf` |
| `title` | Document title where one can be found, else `null` |
| `section` | Heading path, empty string if the text sits under no heading |
| `page`, `page_end` | First and last page the chunk covers (PDF only, else `null`) |
| `chunk_index` | Position of the chunk within its document, from 0 |
| `n_chars` | Length of `text` |

### From Python

```python
from doc_ingest import load_document, chunk_document

doc = load_document("examples/corpus/handbook.md")
for chunk in chunk_document(doc, chunk_size=400):
    print(chunk.section, "|", chunk.n_chars)
```

```text
Larkspur Field Handbook | 154
Larkspur Field Handbook > Daily checks | 267
Larkspur Field Handbook > Daily checks > Battery | 234
Larkspur Field Handbook > Fault codes | 332
Larkspur Field Handbook > Resetting the controller | 157
```

## Features

- [x] Plain text, Markdown, HTML and DOCX inputs (standard library only)
- [x] PDF text input with page numbers (optional `pypdf` extra)
- [x] Table preservation as Markdown (Markdown, HTML, DOCX)
- [x] Structure-aware chunking (headings, sections, tables and code kept intact)
- [x] Source provenance metadata (file, section, page)
- [x] JSONL export
- [x] OCR fallback for scanned PDF pages (`--ocr`, uses the `tesseract` program)
- [x] Heading detection in PDFs (by font size)
- [x] Table detection in PDFs (aligned columns)
- [x] Exporters for common vector stores (`--format chroma` and `--format pinecone` write load-ready files; no direct upload)
- [ ] Chunk overlap and token-based (rather than character-based) sizes

## Limitations

- Scanned PDFs produce no text unless you pass `--ocr` and have `tesseract` installed; OCR only covers the image encodings listed above, and OCR output is not marked as such per chunk (the summary counts OCRed pages). Images embedded in DOCX and HTML are not OCRed. PDF text comes out in the order `pypdf` reports it, so multi-column page layouts may interleave and tables are only found when their columns align (see above). PDF headings are guessed: a short line (up to 120 characters, not ending in `.`, `,` or `;`) set at least 15% larger than the most common font size counts as a heading, with levels ranked by size. Bold-only headings at body size are missed, and a PDF whose text is all one size gets no headings. Scanned pages read through OCR carry no heading information.
- The exporters write files only and were checked against the documented record shapes, not against live Chroma or Pinecone instances.
- Chunk size is counted in characters, not model tokens, and there is no overlap between chunks.
- DOCX reading covers the main document body: headings, paragraphs, numbered or bulleted paragraphs and top-level tables. Headers, footers, footnotes, text boxes, images and tracked-change markup are ignored, and merged table cells are flattened.
- HTML is read as static markup; anything a page renders with JavaScript is not there. Nested tables are flattened into the outer table.
- Files are decoded as UTF-8, with undecodable bytes replaced.
- The older binary `.doc` format is not supported.

## Contributing

Bug reports with a small sample file that extracts badly are the most useful contribution. To work on the code:

```bash
pip install -e ".[test,pdf]"
pytest
```

`examples/make_docx.py` regenerates the sample Word file, and `tests/builders.py` builds DOCX and PDF fixtures on the fly so no binary test data is needed.

Built and maintained by [Narayana Vemburaj](https://github.com/narayana006).

## License

[MIT](LICENSE)
