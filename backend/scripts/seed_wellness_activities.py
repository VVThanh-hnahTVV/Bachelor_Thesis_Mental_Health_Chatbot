#!/usr/bin/env python3
"""Seed wellness activities into MongoDB and optionally index Qdrant."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running from repo root or backend/
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.client import close_mongo_client, get_mongo_client
from app.db.repository import upsert_wellness_activity
from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def seed_mongo() -> int:
    from app.config import get_settings

    settings = get_settings()
    client = get_mongo_client()
    db = client[settings.mongo_db_name]
    for doc in DEFAULT_WELLNESS_ACTIVITIES:
        await upsert_wellness_activity(db, doc)
        logger.info("Upserted activity: %s", doc["id"])
    await close_mongo_client()
    return len(DEFAULT_WELLNESS_ACTIVITIES)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed wellness activities catalog.")
    parser.add_argument(
        "--ingest-qdrant",
        action="store_true",
        help="Also run Qdrant ingest after Mongo seed",
    )
    args = parser.parse_args()

    count = asyncio.run(seed_mongo())
    logger.info("Seeded %d activities into MongoDB", count)

    if args.ingest_qdrant:
        from app.medical.agents.wellness_agent.ingest import ingest_all

        result = ingest_all()
        logger.info("Qdrant ingest: %s", result)
        return 0 if result.get("success") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
