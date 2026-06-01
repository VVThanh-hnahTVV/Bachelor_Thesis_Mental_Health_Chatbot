"""Singleton compiled medical LangGraph."""

from __future__ import annotations

from typing import Any

_compiled_graph: Any | None = None


def get_compiled_medical_graph():
    global _compiled_graph
    if _compiled_graph is None:
        from app.medical.agents.agent_decision import create_agent_graph

        _compiled_graph = create_agent_graph()
    return _compiled_graph
