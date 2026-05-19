#!/usr/bin/env python3
"""Seed MongoDB knowledge chunks with embeddings for hybrid RAG."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.db.client import close_mongo_client, get_mongo_client
from app.db.repository import ensure_indexes, upsert_knowledge_chunk
from app.rag.embeddings import embed_documents

CHUNKS = ROOT / "app" / "data" / "knowledge" / "chunks.json"


async def main() -> None:
    if not CHUNKS.exists():
        print("chunks.json missing; nothing to do.")
        return
    data = json.loads(CHUNKS.read_text(encoding="utf-8"))
    rows = [item for item in data if isinstance(item, dict) and item.get("text")]
    texts = [str(item["text"]) for item in rows]
    embeddings = await embed_documents(texts)

    settings = get_settings()
    client = get_mongo_client()
    try:
        db = client[settings.mongo_db_name]
        await ensure_indexes(db)
        for item, embedding in zip(rows, embeddings, strict=True):
            await upsert_knowledge_chunk(
                db,
                chunk_id=str(item.get("id", "")),
                text=str(item["text"]),
                topic=str(item.get("topic", "")),
                embedding=embedding,
                source="chunks.json",
            )
        print(f"Seeded {len(rows)} knowledge chunks into MongoDB.")
    finally:
        await close_mongo_client()


if __name__ == "__main__":
    asyncio.run(main())
