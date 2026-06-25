#!/usr/bin/env python3
"""Copy Qdrant vectors from local embedded storage to Qdrant Cloud (no re-embedding)."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import PointStruct, Record

from app.medical.config import get_medical_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CORPUS_CHOICES = ("pdf_rag", "web_corpus", "wellness")


@dataclass(frozen=True)
class CorpusTask:
    name: str
    local_path: str
    collection: str


def _corpus_tasks() -> list[CorpusTask]:
    med = get_medical_config()
    return [
        CorpusTask("pdf_rag", med.rag.vector_local_path, med.rag.collection_name),
        CorpusTask(
            "web_corpus",
            med.web_corpus.vector_local_path,
            med.web_corpus.collection_name,
        ),
        CorpusTask(
            "wellness",
            med.wellness.vector_local_path,
            med.wellness.collection_name,
        ),
    ]


def _open_local_client(path: str) -> QdrantClient:
    try:
        return QdrantClient(path=path)
    except RuntimeError as exc:
        if "already accessed by another instance" in str(exc):
            raise SystemExit(
                f"Local Qdrant path is locked: {path}\n"
                "Stop the backend (uvicorn) and retry — embedded Qdrant allows "
                "only one client per folder."
            ) from exc
        raise


def _open_remote_client() -> QdrantClient:
    med = get_medical_config()
    url = med.rag.url
    api_key = med.rag.api_key
    if not url:
        raise SystemExit(
            "QDRANT_URL is not set. Add it to backend/.env before migrating to cloud."
        )
    return QdrantClient(url=url, api_key=api_key or None)


def _local_collection_names(client: QdrantClient) -> set[str]:
    return {c.name for c in client.get_collections().collections}


def _records_to_points(records: list[Record]) -> list[PointStruct]:
    return [
        PointStruct(id=r.id, vector=r.vector, payload=r.payload)
        for r in records
    ]


def _ensure_target_collection(
    local: QdrantClient,
    remote: QdrantClient,
    collection: str,
    *,
    recreate: bool,
) -> None:
    if remote.collection_exists(collection):
        if recreate:
            logger.info("Deleting existing remote collection %s", collection)
            remote.delete_collection(collection)
        else:
            info = remote.get_collection(collection)
            existing = int(info.points_count or 0)
            if existing > 0:
                raise SystemExit(
                    f"Remote collection {collection!r} already has {existing} points. "
                    "Use --recreate to replace or migrate to a new collection name."
                )
            logger.info("Remote collection %s exists but is empty — reusing", collection)
            return

    info = local.get_collection(collection)
    params = info.config.params
    remote.create_collection(
        collection_name=collection,
        vectors_config=params.vectors,
        sparse_vectors_config=params.sparse_vectors,
    )
    logger.info("Created remote collection %s", collection)


def migrate_collection(
    *,
    local: QdrantClient,
    remote: QdrantClient,
    collection: str,
    batch_size: int,
    dry_run: bool,
    recreate: bool,
) -> int:
    if collection not in _local_collection_names(local):
        logger.warning("Skip %s — not found in local storage", collection)
        return 0

    local_info = local.get_collection(collection)
    total = int(local_info.points_count or 0)
    logger.info("Local collection %s: %d points", collection, total)
    if total == 0 or dry_run:
        return total

    _ensure_target_collection(local, remote, collection, recreate=recreate)

    migrated = 0
    offset = None
    while True:
        points, offset = local.scroll(
            collection_name=collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if points:
            remote.upsert(
                collection_name=collection,
                points=_records_to_points(points),
            )
            migrated += len(points)
            logger.info("  upserted %d / %d", migrated, total)
        if offset is None:
            break

    remote_count = int(remote.get_collection(collection).points_count or 0)
    if remote_count != total:
        logger.warning(
            "Point count mismatch for %s: local=%d remote=%d",
            collection,
            total,
            remote_count,
        )
    else:
        logger.info("Verified %s: %d points on cloud", collection, remote_count)
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate local Qdrant vectors to Qdrant Cloud without re-embedding.",
    )
    parser.add_argument(
        "--corpus",
        choices=CORPUS_CHOICES,
        action="append",
        help="Migrate only selected corpus (default: all)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Scroll/upsert batch size (default: 64)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report local point counts; do not write to cloud",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate remote collections before upsert",
    )
    args = parser.parse_args()

    selected = set(args.corpus or CORPUS_CHOICES)
    tasks = [t for t in _corpus_tasks() if t.name in selected]

    remote: QdrantClient | None = None
    if not args.dry_run:
        remote = _open_remote_client()
        med = get_medical_config()
        logger.info("Target: %s", med.rag.url)

    by_path: dict[str, list[CorpusTask]] = {}
    for task in tasks:
        by_path.setdefault(task.local_path, []).append(task)

    total_migrated = 0
    for local_path, path_tasks in by_path.items():
        logger.info("Opening local storage: %s", local_path)
        local = _open_local_client(local_path)
        for task in path_tasks:
            logger.info("--- %s (%s) ---", task.name, task.collection)
            try:
                count = migrate_collection(
                    local=local,
                    remote=remote,  # type: ignore[arg-type]
                    collection=task.collection,
                    batch_size=args.batch_size,
                    dry_run=args.dry_run,
                    recreate=args.recreate,
                )
                total_migrated += count if not args.dry_run else 0
            except UnexpectedResponse as exc:
                logger.error("Qdrant API error for %s: %s", task.collection, exc)
                raise SystemExit(1) from exc

    if args.dry_run:
        logger.info("Dry run complete — no data written.")
    else:
        logger.info("Migration complete — %d points upserted.", total_migrated)


if __name__ == "__main__":
    main()
