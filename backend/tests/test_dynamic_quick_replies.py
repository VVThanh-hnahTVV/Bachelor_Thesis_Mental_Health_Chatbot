import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.conversation_ui import should_skip_quick_replies
from app.graph.dynamic_quick_replies import (
    _parse_llm_response,
    generate_follow_up_quick_replies,
)


def test_parse_llm_response_offers_chips():
    raw = json.dumps({
        "offer_chips": True,
        "options": [
            {"id": "1", "label": "Khá ổn", "message": "Hôm nay tôi cảm thấy khá ổn"},
        ],
    })
    offer, opts = _parse_llm_response(raw)
    assert offer is True
    assert len(opts) == 1
    assert opts[0]["label"] == "Khá ổn"


def test_parse_llm_response_declines_chips():
    raw = json.dumps({"offer_chips": False, "options": []})
    offer, opts = _parse_llm_response(raw)
    assert offer is False
    assert opts == []


def test_skip_quick_replies_on_meta():
    assert should_skip_quick_replies(
        user_input="bạn là ai",
        intent="casual",
        therapy_strategy=None,
        objection_detected=False,
        chat_blocked=False,
        message_type="normal",
    )


def test_skip_quick_replies_on_objection():
    assert should_skip_quick_replies(
        user_input="wtf",
        intent="venting",
        therapy_strategy="reflective_listening",
        objection_detected=True,
        chat_blocked=False,
        message_type="normal",
    )


def test_skip_quick_replies_when_activity_buttons_present():
    assert should_skip_quick_replies(
        user_input="tôi buồn",
        intent="venting",
        therapy_strategy="reflective_listening",
        objection_detected=False,
        chat_blocked=False,
        message_type="normal",
        suggested_activities=[{"id": "ocean_sound"}],
    )


@pytest.mark.asyncio
async def test_generate_returns_empty_when_llm_declines():
    mock_msg = MagicMock()
    mock_msg.content = json.dumps({"offer_chips": False, "options": []})

    with (
        patch("app.graph.dynamic_quick_replies.get_chat_model", return_value=MagicMock()),
        patch(
            "app.graph.dynamic_quick_replies.invoke_with_fallback",
            new_callable=AsyncMock,
        ) as mock_invoke,
    ):
        mock_invoke.return_value = mock_msg
        opts = await generate_follow_up_quick_replies(
            user_input="wtf",
            assistant_reply="Có vẻ bạn đang bối rối. Bạn muốn chia sẻ thêm không?",
            lang="vi",
            provider="openai",
            intent="venting",
        )
    assert opts == []


@pytest.mark.asyncio
async def test_generate_returns_chips_when_llm_offers():
    mock_msg = MagicMock()
    mock_msg.content = json.dumps({
        "offer_chips": True,
        "options": [
            {"id": "1", "label": "Công việc", "message": "Tôi muốn nói về công việc"},
            {"id": "2", "label": "Giấc ngủ", "message": "Tôi muốn nói về giấc ngủ"},
        ],
    })

    with (
        patch("app.graph.dynamic_quick_replies.get_chat_model", return_value=MagicMock()),
        patch(
            "app.graph.dynamic_quick_replies.invoke_with_fallback",
            new_callable=AsyncMock,
        ) as mock_invoke,
    ):
        mock_invoke.return_value = mock_msg
        opts = await generate_follow_up_quick_replies(
            user_input="Tôi muốn tìm hiểu",
            assistant_reply="Bạn muốn tìm hiểu chủ đề nào: lo âu, giấc ngủ hay căng thẳng?",
            lang="vi",
            provider="openai",
            intent="learn",
        )
    assert len(opts) == 2
    assert all("message" in o and "label" in o for o in opts)
