"""CLI entry point for PDF ingestion.

Usage:
    python -m ingestion.ingest_pdfs --pdf-dir data/pdfs

Expects data/pdfs/manifest.json:
[
  {
    "filename": "chula_cs_round3_2567.pdf",
    "university": "Chulalongkorn",
    "major": "Computer Science",
    "round": 3,
    "year": 2567,
    "source_url": "https://..."
  },
  ...
]

PDFs without a manifest entry are still ingested with null metadata fields.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from db.qdrant_client import get_qdrant_client
from ingestion.chunker import chunk_pages
from ingestion.embedder import embed_chunks
from ingestion.pdf_parser import parse_pdf
from ingestion.qdrant_ingester import init_collection, upsert_chunks


def _load_manifest(pdf_dir: Path) -> dict[str, dict]:
    manifest_path = pdf_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    with manifest_path.open(encoding="utf-8") as f:
        entries = json.load(f)
    return {e["filename"]: e for e in entries}


async def ingest_directory(pdf_dir: str) -> None:
    dir_path = Path(pdf_dir)
    if not dir_path.is_dir():
        raise SystemExit(f"Directory not found: {pdf_dir}")

    manifest = _load_manifest(dir_path)
    pdf_files = sorted(dir_path.glob("*.pdf"))
    if not pdf_files:
        print("No PDF files found.")
        return

    client = get_qdrant_client()
    init_collection(client)
    print(f"Collection ready. Processing {len(pdf_files)} PDF(s)...\n")

    total_upserted = 0
    for pdf_path in pdf_files:
        meta = manifest.get(pdf_path.name, {})
        print(f"  Parsing  {pdf_path.name} ...")
        doc_hash, pages = parse_pdf(str(pdf_path))
        print(f"           {len(pages)} page(s) extracted  [hash={doc_hash[:8]}...]")

        chunks = chunk_pages(pages, meta)
        print(f"           {len(chunks)} chunk(s) created")

        print(f"           Embedding (this may take a while) ...")
        embedded = await embed_chunks(chunks)

        n = upsert_chunks(client, embedded)
        total_upserted += n
        print(f"           {n} point(s) upserted into Qdrant\n")

    print(f"Done. Total points upserted: {total_upserted}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDFs into Qdrant")
    parser.add_argument("--pdf-dir", default="data/pdfs", help="Directory containing PDFs + manifest.json")
    args = parser.parse_args()
    asyncio.run(ingest_directory(args.pdf_dir))


if __name__ == "__main__":
    main()
