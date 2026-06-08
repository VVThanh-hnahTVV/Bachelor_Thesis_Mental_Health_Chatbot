"""CLI: index wellness catalog into local Qdrant."""

from __future__ import annotations

import logging

from app.medical.agents.wellness_agent.activity_store import list_helios_activities
from app.medical.agents.wellness_agent.vectorstore import upsert_activity

logger = logging.getLogger(__name__)


def ingest_all() -> dict[str, object]:
    activities = list_helios_activities()
    indexed = 0
    errors: list[str] = []
    for doc in activities:
        try:
            upsert_activity(doc)
            indexed += 1
            logger.info("Indexed wellness activity: %s", doc.get("id"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{doc.get('id')}: {exc}")
            logger.exception("Failed to index %s", doc.get("id"))

    return {
        "success": indexed > 0 and not errors,
        "indexed": indexed,
        "total": len(activities),
        "errors": errors,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = ingest_all()
    print(result)
