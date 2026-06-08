"""Tests for activity_to_api and rating validation helpers."""

import pytest

from app.db.repository import activity_to_api
from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES


def test_activity_to_api_vi():
    doc = DEFAULT_WELLNESS_ACTIVITIES[0]
    out = activity_to_api(doc, lang="vi")
    assert out["id"] == "breathing_box"
    assert "Hít thở" in out["title"]
    assert out["ui_component"] == "breathing_box"
    assert isinstance(out["benefits"], list)


def test_activity_to_api_en_benefits():
    doc = DEFAULT_WELLNESS_ACTIVITIES[0]
    out = activity_to_api(doc, lang="en")
    assert any("anxiety" in str(b).lower() for b in out["benefits"])


def test_rating_range_validation():
    import asyncio
    from bson import ObjectId

    from app.db.repository import save_activity_rating

    class _FakeDb:
        pass

    with pytest.raises(ValueError):
        asyncio.run(
            save_activity_rating(
                _FakeDb(),  # type: ignore[arg-type]
                session_id="s" * 8,
                activity_id="breathing_box",
                completion_id=ObjectId(),
                rating=6,
            )
        )
