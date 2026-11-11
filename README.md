# doc-ingest

One command from a folder of text, Markdown, HTML, DOCX and PDF files to clean, section-aware chunks in JSONL, each tagged with the file, heading path and page it came from.

**Status: first working version (0.1.0).** Text, Markdown, HTML and DOCX work with no dependencies; PDF text extraction works with the optional `pypdf` extra. Tables are kept as Markdown, chunks follow heading boundaries, and output is JSONL. Not built yet: OCR for scanned pages, table detection inside PDFs, and exporters that write straight to a vector store.

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
doc-ingest PATH [PATH ...] [--out FILE] [--chunk-size N] [--prepend-section] [--quiet]
```

| Option | Default | Effect |
| --- | --- | --- |
| `PATH` | | Files or directories. Directories are searched recursively; hidden files and folders are ignored |
| `--out FILE` | stdout | Where to write JSONL. With stdout, the summary goes to stderr so the output can be piped |
| `--chunk-size N` | 800 | Maximum characters per chunk |
| `--prepend-section` | off | Start each chunk's text with its heading path, which helps keyword and embedding search on short chunks |
| `--quiet` | off | No summary |

Exit code is 0 on success, 1 if any file could not be read (the rest are still written, and each failure is listed on stderr), 2 for a bad argument.

### What each format gives you

| Format | Extensions | Needs | Headings | Tables | Page numbers |
| --- | --- | --- | --- | --- | --- |
| Plain text | `.txt`, `.text` | nothing | no | no | no |
| Markdown | `.md`, `.markdown` | nothing | `#` and underlined | pipe tables kept as written | no |
| HTML | `.html`, `.htm` | nothing | `h1` to `h6` | converted to Markdown | no |
| Word | `.docx` | nothing | Heading 1 to 6 and Title styles | converted to Markdown | no |
| PDF | `.pdf` | `pypdf` extra | no | no | yes |

HTML extraction drops `script`, `style`, `nav`, `footer`, `aside`, `form` and similar page chrome. Markdown front matter is removed and its `title` is used. Fenced code and `<pre>` blocks are kept intact as fenced code.

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
- [ ] OCR fallback for scanned pages
- [ ] Table and heading detection in PDFs
- [ ] Exporters for common vector stores
- [ ] Chunk overlap and token-based (rather than character-based) sizes

## Limitations

- Scanned PDFs produce no text: there is no OCR. PDF text comes out as paragraphs in the order `pypdf` reports them, with no headings or tables, so multi-column layouts may interleave.
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
