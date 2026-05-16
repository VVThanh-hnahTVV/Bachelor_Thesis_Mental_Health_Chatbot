"""Main LangGraph pipeline.

Graph flow:
  input_normalize
    → emotion_intent
        → off_topic_reply  (if intent == "off_topic")         → END
        → memory_retrieval → therapy_router → response_generator → response_filter → END
        (casual / all other health intents go to memory_retrieval)

Safety engine runs OUTSIDE this graph (parallel asyncio task in routes.py).
"""
from __future__ import annotations

import logging
import re
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.config import ProviderName
from app.graph.nodes.emotion_intent import node_emotion_intent
from app.graph.nodes.input_normalizer import node_input_normalize
from app.graph.nodes.memory_retrieval import node_memory_retrieval
from app.graph.nodes.response_filter import node_response_filter
from app.graph.nodes.response_generator import node_response_generator
from app.graph.nodes.therapy_router import node_therapy_router
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

_OFF_TOPIC_SYSTEM = """\
You are Luna, a mental wellness companion.
The user just sent a message that is NOT related to health, emotions, or mental wellbeing.

Your task:
1. Briefly and warmly acknowledge what they said (1 sentence max).
2. Explain naturally WHY you can only help with health and emotional topics — not as a rigid rule,
   but as a gentle reminder of your purpose.
3. Invite them to share how they are feeling or if there is something on their mind.

Tone: warm, non-judgmental, brief (2–3 sentences total).
IMPORTANT: Reply in exactly the same language the user wrote in.
"""


class GraphState(TypedDict, total=False):
    # Input
    user_input: str
    history: list[dict[str, str]]
    provider: ProviderName
    session_id: str
    db: Any  # AsyncIOMotorDatabase — passed for memory_retrieval

    # Phase 1: Normalize
    language: str

    # Phase 2: Emotion + Intent
    primary_emotion: str
    emotion_intensity: float
    intent: str

    # Phase 3: Memory
    retrieved_chunks: list[str]
    long_term_context: dict[str, Any]

    # Phase 4: Therapy
    therapy_strategy: str

    # Phase 5: Response
    final_reply: str
    response_safe: bool

    # Output type (set by graph; safety override set in routes.py)
    message_type: str   # "normal" | "off_topic" | "crisis"

    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# LLM-generated off-topic redirect node
# ---------------------------------------------------------------------------

async def node_off_topic_reply(state: GraphState) -> dict[str, Any]:
    """Generate a natural, context-aware explanation + health redirect."""
    user_input: str = state.get("user_input", "")
    provider: ProviderName = state.get("provider", "openai")
    fallback = (
        "I'm Luna — a mental wellness companion. "
        "That topic is a bit outside my area, but I'm always here if you'd like to talk "
        "about how you're feeling or anything on your mind."
    )
    try:
        llm = get_chat_model(provider)
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_OFF_TOPIC_SYSTEM), HumanMessage(content=user_input)],
            primary=provider,
        )
        reply = msg.content if isinstance(msg.content, str) else str(msg.content)
        reply = reply.strip() or fallback
    except Exception as exc:
        logger.warning("node_off_topic_reply LLM failed: %s", exc)
        reply = fallback
    return {"final_reply": reply, "message_type": "off_topic"}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_emotion_intent(state: GraphState) -> str:
    if state.get("intent") == "off_topic":
        return "off_topic_reply"
    # casual, greetings, and all health-related intents → normal pipeline
    return "memory_retrieval"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(GraphState)

    g.add_node("input_normalize", node_input_normalize)
    g.add_node("emotion_intent", node_emotion_intent)
    g.add_node("off_topic_reply", node_off_topic_reply)
    g.add_node("memory_retrieval", node_memory_retrieval)
    g.add_node("therapy_router", node_therapy_router)
    g.add_node("response_generator", node_response_generator)
    g.add_node("response_filter", node_response_filter)

    g.set_entry_point("input_normalize")
    g.add_edge("input_normalize", "emotion_intent")
    g.add_conditional_edges(
        "emotion_intent",
        route_after_emotion_intent,
        {"off_topic_reply": "off_topic_reply", "memory_retrieval": "memory_retrieval"},
    )
    g.add_edge("off_topic_reply", END)
    g.add_edge("memory_retrieval", "therapy_router")
    g.add_edge("therapy_router", "response_generator")
    g.add_edge("response_generator", "response_filter")
    g.add_edge("response_filter", END)

    return g


_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph().compile()
    return _compiled


def reset_compiled_graph() -> None:
    """Force recompile — call after hot-reload in dev."""
    global _compiled
    _compiled = None


async def run_turn(state: dict[str, Any]) -> dict[str, Any]:
    graph = get_compiled_graph()
    result: dict[str, Any] = await graph.ainvoke(state)
    if "message_type" not in result:
        result["message_type"] = "normal"
    return result
