# doc-ingest

> One pipeline from PDF, HTML and DOCX to clean, metadata-rich chunks for any vector store.

**Status:** 🚧 Early stage — design and roadmap published, implementation in progress. Stars, issues and ideas welcome.

## Why

The boring 80% of every RAG project is getting clean text, tables and metadata out of messy documents.

## Planned features

- [ ] PDF, HTML, DOCX, Markdown inputs
- [ ] OCR fallback for scanned pages
- [ ] Table preservation as Markdown
- [ ] Structure-aware chunking (headings, sections)
- [ ] Source provenance metadata (file, page, section)
- [ ] Exporters for common vector stores and JSONL

## Intended usage

```
doc-ingest ./corpus --out chunks.jsonl --chunk-size 800
```

_The interface above is the target design and may change._

## Roadmap

1. Core implementation of the first feature set
2. Examples and tests
3. CI and first tagged release
4. Docs and integrations

## Contributing

Contributions are welcome. Open an issue to discuss an idea or pick an unchecked item from the feature list.

## License

[MIT](LICENSE)
