"""Output formats: plain JSONL, or files shaped for loading into a vector store.

The exporters only reshape chunk records. They do not compute embeddings or
talk to any service; the stores below embed the text themselves on upload.
"""

from __future__ import annotations

import json

FORMATS = ("jsonl", "chroma", "pinecone")

_METADATA_FIELDS = ("source", "format", "title", "section", "page", "page_end", "chunk_index", "n_chars")


def _metadata(record: dict) -> dict:
    # Vector stores reject null metadata values, so unset fields are left out.
    return {key: record[key] for key in _METADATA_FIELDS if record.get(key) is not None}


def to_jsonl(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def to_chroma(records: list[dict]) -> str:
    """One JSON object whose keys match ``collection.add(ids=, documents=, metadatas=)``."""
    payload = {
        "ids": [r["id"] for r in records],
        "documents": [r["text"] for r in records],
        "metadatas": [_metadata(r) for r in records],
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def to_pinecone(records: list[dict]) -> str:
    """JSONL records for ``index.upsert_records``: ``_id``, ``chunk_text`` and flat metadata."""
    lines = []
    for r in records:
        row = {"_id": r["id"], "chunk_text": r["text"], **_metadata(r)}
        lines.append(json.dumps(row, ensure_ascii=False) + "\n")
    return "".join(lines)


def export_records(records: list[dict], fmt: str) -> str:
    if fmt == "jsonl":
        return to_jsonl(records)
    if fmt == "chroma":
        return to_chroma(records)
    if fmt == "pinecone":
        return to_pinecone(records)
    raise ValueError(f"unknown format {fmt!r}; choose from {', '.join(FORMATS)}")
