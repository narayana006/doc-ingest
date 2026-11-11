"""Turn documents into section-aware chunks with provenance."""

from .blocks import Block, Document
from .chunker import Chunk, chunk_document
from .loaders import SUPPORTED_SUFFIXES, load_document

__version__ = "0.1.0"

__all__ = ["Block", "Chunk", "Document", "SUPPORTED_SUFFIXES", "chunk_document", "load_document"]
