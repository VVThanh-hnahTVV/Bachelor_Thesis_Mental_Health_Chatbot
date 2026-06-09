from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.crawl.chunking import chunk_text_by_words
from app.crawl.models import CrawledArticle
from app.crawl.staging import (
    DEFAULT_STAGING_DIR,
    list_articles,
    list_indexed_content_hashes,
    move_article,
)
from app.medical.agents.rag_agent.vectorstore_qdrant import CorpusVectorStore
from app.medical.config import get_medical_config

logger = logging.getLogger(__name__)


def _refresh_web_catalog(*, base_dir: Path, catalog_path: Path) -> None:
    indexed = list_articles("indexed", base_dir=base_dir, include_full_text=False)
    entries = [
        {
            "source_id": row["source_id"],
            "title": row["title"],
            "publisher": row.get("publisher", ""),
            "language": row.get("language", ""),
            "url": row.get("url", ""),
            "indexed_at": row.get("indexed_at", ""),
        }
        for row in indexed
    ]
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps({"updated_at": datetime.now(UTC).isoformat(), "articles": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_web_vector_index(
    *,
    staging_dir: str | Path = DEFAULT_STAGING_DIR,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """
    Index all approved articles into the web Qdrant collection.
    Moves successfully indexed articles to indexed staging.
    """
    cfg = get_medical_config()
    base_dir = Path(staging_dir)
    approved = list_articles("approved", base_dir=base_dir, include_full_text=True)
    indexed_hashes = list_indexed_content_hashes(base_dir=base_dir)

    store = CorpusVectorStore.for_web_corpus(cfg)
    indexed_count = 0
    skipped_count = 0
    chunk_count = 0
    errors: list[str] = []

    total = len(approved)
    for idx, row in enumerate(approved):
        article = CrawledArticle.from_dict(row)
        if on_progress:
            on_progress(current=idx, total=total, title=article.title)

        if article.content_hash in indexed_hashes:
            move_article(
                article.source_id,
                from_status="approved",
                to_status="indexed",
                base_dir=base_dir,
            )
            skipped_count += 1
            continue

        try:
            chunks = chunk_text_by_words(
                article.full_text,
                chunk_size=cfg.rag.chunk_size,
                overlap=cfg.rag.chunk_overlap,
            )
            if not chunks:
                errors.append(f"{article.source_id}: no chunks")
                continue

            store.ingest_chunks(
                chunks,
                metadata_base={
                    "source": article.title,
                    "source_path": article.url,
                    "corpus": "mental_health_web",
                    "source_id": article.source_id,
                    "publisher": article.publisher,
                    "language": article.language,
                    "published_at": article.published_at,
                },
            )
            move_article(
                article.source_id,
                from_status="approved",
                to_status="indexed",
                base_dir=base_dir,
            )
            indexed_hashes.add(article.content_hash)
            indexed_count += 1
            chunk_count += len(chunks)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to index %s", article.source_id)
            errors.append(f"{article.source_id}: {exc}")

    _refresh_web_catalog(
        base_dir=base_dir,
        catalog_path=Path(cfg.web_corpus.web_catalog_path),
    )

    if on_progress:
        on_progress(current=total, total=total, title="done")

    return {
        "success": indexed_count > 0 or (total == 0 and not errors),
        "indexed_articles": indexed_count,
        "skipped_duplicate": skipped_count,
        "chunks_indexed": chunk_count,
        "errors": errors,
    }


def count_web_collection_points() -> int | None:
    cfg = get_medical_config()
    store = CorpusVectorStore.for_web_corpus(cfg)
    if not store.collection_exists():
        return 0
    try:
        info = store.client.get_collection(store.collection_name)
        return int(getattr(info, "points_count", 0) or 0)
    except Exception:  # noqa: BLE001
        return None
