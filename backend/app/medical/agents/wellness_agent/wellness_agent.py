"""Helios WELLNESS_AGENT — suggest catalog activities by user goal."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.medical.agents.agent_decision import AgentState
from app.medical.agents.wellness_agent.retrieval import retrieve_wellness_suggestions
from app.medical.config import get_medical_config
from app.medical.prompts import MARKDOWN_RESPONSE_INSTRUCTIONS
from app.medical.validation_input import extract_input_text


def run_wellness_agent(state: AgentState) -> AgentState:
    from app.chat_progress import emit_progress

    emit_progress("WELLNESS_AGENT")

    query = extract_input_text(state.get("current_input")) or ""
    # Explicit wellness intent — always surface matches (no post-RAG threshold).
    retrieval = retrieve_wellness_suggestions(
        query,
        limit=3,
        lang="vi",
        require_threshold=False,
        log_context="WELLNESS_AGENT",
    )
    suggestions = retrieval.suggestions

    activity_lines = "\n".join(
        f"- {s['id']}: {s['title']} — {s['description']}" for s in suggestions
    ) or "- (no activities matched)"

    config = get_medical_config()
    system = f"""You are Helios wellness assistant. The user wants a relaxing or grounding activity.
Recommend 1–3 activities from the catalog below. Explain briefly why each fits their request.
Tell them they can tap an activity button below the message to start.
Do not diagnose medical conditions. Keep the tone warm and concise.

Matched activities:
{activity_lines}

{MARKDOWN_RESPONSE_INSTRUCTIONS}
"""
    response = config.conversation.llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=query or "Gợi ý bài tập thư giãn"),
        ]
    )
    reply = response.content if hasattr(response, "content") else str(response)

    return {
        **state,
        "output": AIMessage(content=str(reply)),
        "agent_name": "WELLNESS_AGENT",
        "suggested_activities": suggestions,
        "wellness_retrieval_score": retrieval.top_score,
        "wellness_retrieval_source": retrieval.source,
    }
