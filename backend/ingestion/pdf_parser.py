"""PDF parser — extract text pages and compute a document hash.

Uses PyMuPDF (fitz) which handles Thai Unicode well and is significantly
faster than pdfplumber for large documents.

Returns one dict per page: {text, page_num, doc_hash, source_path}.
The doc_hash (SHA-256 of raw file bytes) lets the ingester skip
documents that haven't changed since last run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz  # PyMuPDF


def parse_pdf(path: str) -> tuple[str, list[dict]]:
    """Parse a PDF and return (doc_hash, pages).

    Each page dict: {text: str, page_num: int, doc_hash: str, source_path: str}
    Pages with no extractable text are skipped.
    """
    raw = Path(path).read_bytes()
    doc_hash = hashlib.sha256(raw).hexdigest()

    pages: list[dict] = []
    with fitz.open(path) as doc:
        for page in doc:
            text = page.get_text("text").strip()
            if text:
                pages.append({
                    "text": text,
                    "page_num": page.number + 1,
                    "doc_hash": doc_hash,
                    "source_path": str(path),
                })

    return doc_hash, pages
