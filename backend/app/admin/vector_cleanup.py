from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.crawl.staging import (
    DEFAULT_STAGING_DIR,
    add_to_blocklist,
    get_article,
    move_article,
    remove_article,
)
from app.crawl.web_ingest import refresh_web_catalog
from app.medical.agents.rag_agent.vectorstore_qdrant import CorpusVectorStore
from app.medical.config import get_medical_config


def _remove_web_vectors(source_id: str) -> int:
    cfg = get_medical_config()
    store = CorpusVectorStore.for_web_corpus(cfg)
    return store.delete_by_metadata_field(field="source_id", value=source_id)


def delete_web_article(
    source_id: str,
    *,
    staging_dir: str | Path = DEFAULT_STAGING_DIR,
) -> dict[str, Any]:
    """
    Delete a staged web article.

    - indexed: remove vectors and move back to pending for re-review
    - other statuses: remove from staging and block future crawls
    """
    cfg = get_medical_config()
    base_dir = Path(staging_dir)
    article = get_article(source_id, base_dir=base_dir)
    if article is None:
        return {"found": False, "action": "not_found", "points_deleted": 0}

    if article.status == "indexed":
        points_deleted = _remove_web_vectors(source_id)
        moved = move_article(
            source_id,
            from_status="indexed",
            to_status="pending",
            base_dir=base_dir,
        )
        if moved is None:
            return {
                "found": True,
                "action": "error",
                "points_deleted": points_deleted,
                "source_id": source_id,
            }
        refresh_web_catalog(
            base_dir=base_dir,
            catalog_path=Path(cfg.web_corpus.web_catalog_path),
        )
        return {
            "found": True,
            "action": "recycled",
            "points_deleted": points_deleted,
            "moved_to": "pending",
            "source_id": source_id,
        }

    removed = remove_article(
        source_id,
        from_status=article.status,
        base_dir=base_dir,
    )
    if removed is None:
        return {"found": False, "action": "not_found", "points_deleted": 0}

    add_to_blocklist(removed, base_dir=base_dir)
    return {
        "found": True,
        "action": "blocked",
        "points_deleted": 0,
        "source_id": source_id,
    }


def unindex_web_article(
    source_id: str,
    *,
    staging_dir: str | Path = DEFAULT_STAGING_DIR,
) -> dict[str, Any]:
    """Backward-compatible alias: recycle indexed article to pending."""
    return delete_web_article(source_id, staging_dir=staging_dir)


def unindex_pdf_vectors(relative_path: str) -> dict[str, Any]:
    """Remove all vector chunks for a PDF identified by its relative path."""
    cfg = get_medical_config()
    filename = os.path.basename(relative_path)
    if not filename:
        return {"found": False, "points_deleted": 0, "source": ""}

    store = CorpusVectorStore.for_pdf_corpus(cfg)
    points_deleted = store.delete_by_metadata_field(field="source", value=filename)

    return {
        "found": True,
        "points_deleted": points_deleted,
        "source": filename,
        "path": relative_path,
    }
