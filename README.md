# doc-ingest

One pipeline from PDF, HTML and DOCX to clean, metadata-rich chunks for any vector store.

> **Project status: planning. There is no working code in this repository yet.**
> This README describes what the project will do. Nothing below can be installed or run today.
> Features are ticked off in the checklist as they are built.

## What it is

A Python library and command-line tool.

**The problem it solves:** The boring 80% of every RAG project is getting clean text, tables and metadata out of messy documents.

## Who it is for

Anyone feeding PDFs, web pages or Word files into a search index or vector database.

## How it will work

1. You point the tool at a folder of documents.
2. It extracts text (using OCR for scanned pages), keeps tables and headings, and splits the result into chunks along section boundaries.
3. It writes the chunks with their source file, page and section so every answer can be traced back.

## Planned features

Unticked items are not built yet.

- [ ] PDF, HTML, DOCX, Markdown inputs
- [ ] OCR fallback for scanned pages
- [ ] Table preservation as Markdown
- [ ] Structure-aware chunking (headings, sections)
- [ ] Source provenance metadata (file, page, section)
- [ ] Exporters for common vector stores and JSONL

## Planned usage

This is the intended interface, shown so you can judge the design. **It does not work yet**, and names may change before the first release.

```bash
doc-ingest ./corpus --out chunks.jsonl --chunk-size 800
```

## Contributing

Feedback on the design is the most useful contribution right now. Open an issue to suggest a feature, question an approach or describe your use case. Code contributions are welcome once the first version lands.

## Author

Built and maintained by [Narayana Vemburaj](https://github.com/narayana006).

## License

[MIT](LICENSE)
