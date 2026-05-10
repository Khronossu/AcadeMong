"""Hierarchical chunker — sliding window over PDF pages.

Splits page text into overlapping chunks so that context near section
boundaries isn't lost. Each chunk carries the full PDF metadata so
Qdrant payloads are self-describing without extra lookups.

Window: 400 characters / 80-character overlap (tuned for Thai text density).
"""

from __future__ import annotations

CHUNK_SIZE = 400
OVERLAP = 80


def chunk_pages(pages: list[dict], metadata: dict) -> list[dict]:
    """Split extracted pages into overlapping text chunks.

    Args:
        pages:    Output of pdf_parser.parse_pdf — list of page dicts.
        metadata: Per-document metadata from manifest.json:
                  {university, major, round, year, source_url}

    Returns a list of chunk dicts ready for embedding.
    Each dict: {text, page, chunk_index, doc_hash, source_path,
                university, major, round, year, source_url}
    """
    chunks: list[dict] = []
    chunk_index = 0

    for page in pages:
        text = page["text"]
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "page": page["page_num"],
                    "chunk_index": chunk_index,
                    "doc_hash": page["doc_hash"],
                    "source_path": page["source_path"],
                    "university": metadata.get("university"),
                    "major": metadata.get("major"),
                    "round": metadata.get("round"),
                    "year": metadata.get("year"),
                    "source_url": metadata.get("source_url", ""),
                })
                chunk_index += 1
            start += CHUNK_SIZE - OVERLAP

    return chunks
