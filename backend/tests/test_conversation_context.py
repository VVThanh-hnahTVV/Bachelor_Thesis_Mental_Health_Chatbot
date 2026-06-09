"""Conversation memory formatting."""

from langchain_core.messages import AIMessage, HumanMessage

from app.conversation.context import (
    build_agent_memory_context,
    format_recent_user_questions,
)


def test_format_recent_user_questions_newest_is_one():
    messages = [
        HumanMessage(content="Tôi thường xuyên buồn chán, có phải bị trầm cảm không"),
        AIMessage(content="..."),
        HumanMessage(content="Tôi bị áp lực thi cử quá nhiều."),
        AIMessage(content="..."),
        HumanMessage(content="Hiện tại tôi mất ngủ"),
    ]
    out = format_recent_user_questions(
        messages,
        limit=5,
        exclude_current="Hiện tại tôi mất ngủ",
    )
    assert out.startswith("1. Tôi bị áp lực thi cử quá nhiều.")
    assert "2. Tôi thường xuyên buồn chán" in out


def test_build_agent_memory_context_header_explains_numbering():
    block = build_agent_memory_context(
        conversation_summary="User asks about sleep.",
        messages=[HumanMessage(content="prior")],
        current_input="current",
    )
    assert "1 = most recent" in block
    assert "RECENT USER QUESTIONS" in block
