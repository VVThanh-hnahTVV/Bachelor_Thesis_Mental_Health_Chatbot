import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.objection_detector import (
    _parse_objection,
    classify_objection,
    node_objection_detector,
)


def test_parse_objection_detected():
    raw = json.dumps({
        "objection_detected": True,
        "objection_type": "misunderstanding",
        "confidence": 0.9,
    })
    detected, typ, conf = _parse_objection(raw)
    assert detected is True
    assert typ == "misunderstanding"
    assert conf == 0.9


def test_parse_objection_none():
    raw = json.dumps({"objection_detected": False, "objection_type": None, "confidence": 0.8})
    detected, typ, conf = _parse_objection(raw)
    assert detected is False
    assert typ is None


def _mock_llm_response(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(payload)
    return msg


@pytest.mark.asyncio
async def test_classify_refusal():
    with (
        patch("app.graph.nodes.objection_detector.get_chat_model", return_value=MagicMock()),
        patch(
            "app.graph.nodes.objection_detector.invoke_with_fallback",
            new_callable=AsyncMock,
        ) as mock_invoke,
    ):
        mock_invoke.return_value = _mock_llm_response({
            "objection_detected": True,
            "objection_type": "refusal",
            "confidence": 0.92,
        })
        detected, typ, _ = await classify_objection(
            "đừng bảo tôi thở nữa",
            [{"role": "assistant", "content": "Hãy thử hít thở nhé."}],
            "openai",
        )
    assert detected is True
    assert typ == "refusal"


@pytest.mark.asyncio
async def test_classify_what_now_not_objection():
    """Progression question after exercise should not be flagged as objection."""
    with (
        patch("app.graph.nodes.objection_detector.get_chat_model", return_value=MagicMock()),
        patch(
            "app.graph.nodes.objection_detector.invoke_with_fallback",
            new_callable=AsyncMock,
        ) as mock_invoke,
    ):
        mock_invoke.return_value = _mock_llm_response({
            "objection_detected": False,
            "objection_type": None,
            "confidence": 0.85,
        })
        detected, typ, _ = await classify_objection(
            "làm xong rồi sao nữa",
            [{"role": "assistant", "content": "Hãy đặt chân lên sàn."}],
            "openai",
        )
    assert detected is False
    assert typ is None


@pytest.mark.asyncio
async def test_classify_low_confidence_ignored():
    with (
        patch("app.graph.nodes.objection_detector.get_chat_model", return_value=MagicMock()),
        patch(
            "app.graph.nodes.objection_detector.invoke_with_fallback",
            new_callable=AsyncMock,
        ) as mock_invoke,
    ):
        mock_invoke.return_value = _mock_llm_response({
            "objection_detected": True,
            "objection_type": "repetition",
            "confidence": 0.3,
        })
        detected, _, _ = await classify_objection("chán", [], "openai")
    assert detected is False


@pytest.mark.asyncio
async def test_node_sets_strategy_on_objection():
    with (
        patch("app.graph.nodes.objection_detector.get_chat_model", return_value=MagicMock()),
        patch(
            "app.graph.nodes.objection_detector.invoke_with_fallback",
            new_callable=AsyncMock,
        ) as mock_invoke,
    ):
        mock_invoke.return_value = _mock_llm_response({
            "objection_detected": True,
            "objection_type": "misunderstanding",
            "confidence": 0.88,
        })
        out = await node_objection_detector({
            "user_input": "Bạn hiểu sai rồi",
            "history": [],
            "provider": "openai",
            "metadata": {},
        })
    assert out["objection_detected"] is True
    assert out["objection_type"] == "misunderstanding"
    assert out["therapy_strategy"] == "reflective_listening"
