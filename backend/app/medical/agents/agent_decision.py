"""
Agent Decision System for Multi-Agent Medical Chatbot

This module handles the orchestration of different agents using LangGraph.
It dynamically routes user queries to the appropriate agent based on content and context.
"""

import json
from typing import Dict, List, Optional, Any, Literal, TypedDict, Union, Annotated
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import MessagesState, StateGraph, END
import os, getpass
from app.medical.agents.rag_agent import get_medical_rag
from app.medical.agents.rag_agent.response_generator import (
    format_rag_sources_section,
    strip_embedded_sources_section,
)
from app.medical.prompts import MARKDOWN_RESPONSE_INSTRUCTIONS, PLAIN_LANGUAGE_MEDICAL_INSTRUCTIONS
from app.medical.agents.web_search_processor_agent import WebSearchProcessorAgent
from app.medical.agents.guardrails.local_guardrails import LocalGuardrails
from app.medical.config import get_medical_config
from app.medical.rag_catalog import build_decision_system_prompt
from app.medical.validation_input import extract_input_text
from app.medical.agents.structured_output import (
    ACTIVITIES_INTRO_RULES,
    SUGGEST_ACTIVITIES_RULES,
    RouteAgentDecision,
    conversation_format_instructions,
    merge_activities_intro,
    parse_conversation_output,
)

from langgraph.checkpoint.memory import MemorySaver

# Initialize memory (per-process; thread_id isolates sessions)
memory = MemorySaver()


# Agent that takes the decision of routing the request further to correct task specific agent
class AgentConfig:
    """Configuration settings for the agent decision system."""
    
    # Decision model
    DECISION_MODEL = "gpt-4o"  # or whichever model you prefer
    
    # Confidence threshold for responses
    CONFIDENCE_THRESHOLD = 0.85
    
    # Routing instructions are built dynamically from data/medical/raw via build_decision_system_prompt().

class AgentState(MessagesState):
    """State maintained across the workflow."""
    # messages: List[BaseMessage]  # Conversation history
    session_id: Optional[str]
    conversation_summary: Optional[str]
    user_long_term_memory: Optional[str]
    prior_user_questions: Optional[List[str]]
    agent_name: Optional[str]  # Current active agent
    current_input: Optional[Union[str, Dict]]  # Input to be processed
    output: Optional[str]  # Final output to user
    retrieval_confidence: float  # Confidence in retrieval (for RAG agent)
    bypass_routing: bool  # Flag to bypass agent routing for guardrails
    insufficient_info: bool  # Deprecated alias; use web_search
    web_search: bool  # RAG requests follow-up web search when context is incomplete
    suggest_activities: bool  # Set by executing agent (conversation / RAG / web)
    suggested_activities: Optional[List[Dict[str, str]]]  # Wellness activity suggestions for UI
    wellness_retrieval_score: Optional[float]
    wellness_retrieval_source: Optional[str]
    user_language: Optional[str]  # ISO 639-1 code from input guardrail (e.g. vi, en)
    rag_sources: Optional[List[Dict[str, str]]]  # RAG citations appended after guardrails
    rag_sub_queries: Optional[List[str]]  # Retrieval sub-queries from route agent


class AgentDecision(TypedDict):
    """Output structure for the decision agent."""
    agent: str
    reasoning: str
    confidence: float


def _input_text_from_state(state: AgentState) -> str:
    current_input = state.get("current_input")
    if isinstance(current_input, str):
        return current_input
    if isinstance(current_input, dict):
        return str(current_input.get("text", ""))
    return ""


def _agent_memory_context(state: AgentState) -> str:
    from app.conversation.context import build_agent_memory_context

    prior = state.get("prior_user_questions")
    prior_list = prior if isinstance(prior, list) else None
    return build_agent_memory_context(
        conversation_summary=str(state.get("conversation_summary") or ""),
        user_long_term_memory=str(state.get("user_long_term_memory") or ""),
        messages=state.get("messages") or [],
        current_input=_input_text_from_state(state),
        prior_user_questions=prior_list,
    )


def create_agent_graph():
    """Create and configure the LangGraph for agent orchestration."""
    config = get_medical_config()

    # Initialize guardrails with the same LLM used elsewhere
    guardrails = LocalGuardrails(config.guardrails.llm)

    # LLM
    decision_model = config.agent_decision.llm
    
    # Initialize the output parser
    json_parser = JsonOutputParser(pydantic_object=RouteAgentDecision)
    
    decision_runner = decision_model | json_parser

    # Define graph state transformations
    def analyze_input(state: AgentState) -> AgentState:
        """Analyze the input to detect images and determine input type."""
        from app.chat_progress import emit_progress

        emit_progress("medical_analyze_input")
        current_input = state["current_input"]
        
        input_text = extract_input_text(current_input)

        # Check input through guardrails if text is present
        if input_text:
            from app.config import get_settings
            from app.conversation.context import resolve_recent_user_questions
            from app.medical.agents.guardrails.schemas import (
                DEFAULT_USER_LANGUAGE,
                detect_user_language_fallback,
                has_clear_language_signal,
                normalize_language_code,
                resolve_user_language,
            )

            def _prior_user_texts() -> list[str]:
                texts: list[str] = []
                for msg in state.get("messages") or []:
                    if isinstance(msg, HumanMessage):
                        texts.append(str(msg.content or ""))
                return texts

            def _resolved_language(detected: str | None = None) -> str:
                if has_clear_language_signal(input_text):
                    return detect_user_language_fallback(input_text)
                return resolve_user_language(
                    input_text,
                    prior_user_messages=_prior_user_texts(),
                    default=detected or DEFAULT_USER_LANGUAGE,
                )

            settings = get_settings()
            if not settings.enable_input_guardrails:
                return {
                    **state,
                    "bypass_routing": False,
                    "user_language": _resolved_language(),
                }

            summary = str(state.get("conversation_summary") or "").strip()
            ltm = str(state.get("user_long_term_memory") or "").strip()
            prior = state.get("prior_user_questions")
            prior_list = prior if isinstance(prior, list) else None
            recent_questions = resolve_recent_user_questions(
                state.get("messages") or [],
                prior_user_questions=prior_list,
                limit=5,
                exclude_current=input_text,
            )
            guard_result = guardrails.check_input(
                input_text,
                conversation_summary=summary,
                recent_user_questions=recent_questions,
                user_long_term_memory=ltm,
            )
            user_language = _resolved_language(
                normalize_language_code(guard_result.user_language),
            )
            if not guard_result.is_allowed:
                agent_label = (
                    "OFF_TOPIC_GUARDRAILS"
                    if guard_result.is_off_topic
                    else "INPUT_GUARDRAILS"
                )
                print(f"Selected agent: {agent_label}, Message: ", guard_result.message)
                blocked = (
                    guard_result.message
                    if isinstance(guard_result.message, AIMessage)
                    else AIMessage(content=str(guard_result.message))
                )
                return {
                    **state,
                    "messages": [blocked],
                    "output": blocked,
                    "agent_name": agent_label,
                    "bypass_routing": True,
                    "user_language": user_language,
                }

            from app.handoff.messages import handoff_consent_notice

            threshold = settings.handoff_confidence_threshold
            if guard_result.needs_human and guard_result.handoff_confidence >= threshold:
                emit_progress("HUMAN_HANDOFF")
                ack_text = handoff_consent_notice(user_language)
                ack = AIMessage(content=ack_text)
                print(
                    f"Selected agent: HUMAN_HANDOFF "
                    f"(confidence={guard_result.handoff_confidence:.2f})"
                )
                return {
                    **state,
                    "messages": [ack],
                    "output": ack,
                    "agent_name": "HUMAN_HANDOFF",
                    "bypass_routing": True,
                    "user_language": user_language,
                }

            return {
                **state,
                "bypass_routing": False,
                "user_language": user_language,
            }

        return {
            **state,
            "bypass_routing": False,
            "user_language": "vi",
        }
    
    def route_after_analyze(state: AgentState) -> str:
        if state.get("bypass_routing", False):
            return "apply_guardrails"
        return "route_to_agent"

    def route_to_agent(state: AgentState) -> Dict:
        """Make decision about which agent should handle the query."""
        from app.chat_progress import emit_progress
        from app.conversation.context import build_routing_conversation_section

        emit_progress("medical_route")
        input_text = _input_text_from_state(state)
        prior = state.get("prior_user_questions")
        prior_list = prior if isinstance(prior, list) else None
        routing_context = build_routing_conversation_section(
            conversation_summary=str(state.get("conversation_summary") or ""),
            messages=state.get("messages") or [],
            current_input=input_text,
            prior_user_questions=prior_list,
        )

        decision_input = f"""Current user message:
{input_text}

Which agent should handle this message? If RAG_AGENT, write sub_queries that preserve the topic from the conversation context in the system instructions (especially for short follow-ups)."""

        system_prompt = build_decision_system_prompt(
            raw_dir=config.rag.raw_documents_dir,
            metadata_path=config.rag.document_metadata_path,
            web_catalog_path=config.web_corpus.web_catalog_path,
            conversation_context=routing_context,
        )
        decision = decision_runner.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=decision_input),
            ]
        )

        # Decided agent
        print(f"Decision: {decision['agent']}")
        from app.chat_progress import emit_progress
        from app.medical.agents.rag_agent.query_expander import normalize_sub_queries

        emit_progress(str(decision["agent"]))

        rag_sub_queries: List[str] = []
        if decision["agent"] == "RAG_AGENT":
            rag_sub_queries = normalize_sub_queries(
                decision.get("sub_queries"),
                input_text,
                max_count=config.rag.max_sub_queries,
            )
            print(f"RAG sub-queries: {rag_sub_queries}")
        
        # Update state with decision
        updated_state = {
            **state,
            "agent_name": decision["agent"],
            "rag_sub_queries": rag_sub_queries,
        }
        
        # Route based on agent name and confidence
        if decision["confidence"] < AgentConfig.CONFIDENCE_THRESHOLD:
            return {**updated_state, "next": "needs_validation"}

        return {**updated_state, "next": decision["agent"]}

    # Define agent execution functions (these will be implemented in their respective modules)
    def run_conversation_agent(state: AgentState) -> AgentState:
        """Handle general conversation."""
        from app.chat_progress import emit_progress

        emit_progress("CONVERSATION_AGENT")
        print(f"Selected agent: CONVERSATION_AGENT")

        input_text = _input_text_from_state(state)
        memory_context = _agent_memory_context(state)

        user_language = str(state.get("user_language") or "vi")

        conversation_prompt = f"""User query: {input_text}

        Conversation memory:
        {memory_context}

        Detected user language code: {user_language}

        **Language (required):** Write the JSON "answer" (and "activities_intro" if used) entirely in Vietnamese when user_language is "vi", and in English when user_language is "en". For unclear or mistyped input, respond warmly in Vietnamese and invite the user to rephrase.

        You are Helios, an AI assistant for **mental health information and supportive guidance** (tra cứu & tư vấn sức khỏe tâm thần). Your goal is warm, clear, empathetic conversation — not cold or generic chatbot replies.

        ### Identity & tone
        - Say "I am Helios" (or introduce yourself by name) ONLY on the first turn of a chat, when the user greets you, or when they explicitly ask who you are.
        - If there is prior conversation in the memory context above, do NOT re-introduce yourself — answer the user's question directly.
        - Never open follow-up replies with a repeated self-introduction.
        - Prefer **warm, human** tone (empathetic, concise). Avoid stiff phrases like "AI medical assistant" alone — describe your role as mental health lookup and supportive guidance.

        ### Role & Capabilities
        - Listen and respond empathetically to feelings (anxiety, stress, low mood, burnout).
        - Explain mental health topics in **plain language**.
        - Answer factual health questions using verified knowledge when relevant.
        - Handle **follow-up questions** while keeping track of conversation context.

        ### Guidelines for Responding:
        1. **General Conversations & greetings:**
        - If the user greets you or asks what you can help with (e.g. "Hello", "What can you do?", "Bạn có thể giúp gì cho tôi?"):
          - Briefly introduce yourself as Helios.
          - Give a **short bullet list** (2–3 items) of what you can help with: emotions/stress, mental health topics in plain language, gentle wellness suggestions when fitting.
          - Add **one sentence** disclaimer: informational support only, not a substitute for licensed professional diagnosis or treatment.
          - End with an open invitation (what would they like to talk about today).
          - Do NOT reply with only one generic line like "How can I help you today?" without explaining your scope.
        - On follow-up messages: skip greetings and self-introduction; respond to what they asked.
        - Keep responses **concise and engaging**, unless a detailed answer is needed.

        2. **When suggest_activities is true:**
        - Keep "answer" short and warm (2–4 sentences).
        - Do NOT list long generic DIY tip lists — the app shows guided exercise buttons below.
        - Use "activities_intro" to invite the user to tap **Open** on exercise buttons below.

        3. **Medical Questions:**
        - If you have **high confidence** in answering, provide a medically accurate response.
        - Ensure responses are **clear, concise, and factual**.

        4. **Follow-Up & Clarifications:**
        - Maintain conversation history for better responses.
        - If a query is unclear, ask **follow-up questions** before answering.

        {PLAIN_LANGUAGE_MEDICAL_INSTRUCTIONS}

        5. **Uncertainty & Ethical Considerations:**
        - If unsure, **never assume** medical facts.
        - Recommend consulting a **licensed healthcare professional** for serious medical concerns.
        - Avoid providing **medical diagnoses** or **prescriptions**—stick to general knowledge.

        {SUGGEST_ACTIVITIES_RULES}

        {ACTIVITIES_INTRO_RULES}

        {MARKDOWN_RESPONSE_INSTRUCTIONS}

        Respond with JSON only (no markdown fences):
        {conversation_format_instructions()}"""

        response = config.conversation.llm.invoke(conversation_prompt)
        structured = parse_conversation_output(response)
        response_text = merge_activities_intro(
            structured.answer,
            suggest_activities=structured.suggest_activities,
            activities_intro=structured.activities_intro,
        )
        suggest_activities = structured.suggest_activities

        print(f"CONVERSATION_AGENT suggest_activities: {suggest_activities}")

        return {
            **state,
            "output": AIMessage(content=response_text),
            "agent_name": "CONVERSATION_AGENT",
            "suggest_activities": suggest_activities,
        }
    
    def run_rag_agent(state: AgentState) -> AgentState:
        """Handle medical knowledge queries using RAG."""
        from app.chat_progress import emit_progress

        emit_progress("RAG_AGENT")
        print(f"Selected agent: RAG_AGENT")

        rag_agent = get_medical_rag(config)
        query = state["current_input"]
        memory_context = _agent_memory_context(state)

        response = rag_agent.process_query(
            query,
            chat_history=memory_context,
            sub_queries=state.get("rag_sub_queries") or [],
        )
        retrieval_confidence = response.get("confidence", 0.0)  # Default to 0.0 if not provided
        web_search = bool(response.get("web_search", False))
        suggest_activities = bool(response.get("suggest_activities", False))

        print(f"Retrieval Confidence: {retrieval_confidence}")
        print(f"RAG web_search: {web_search}, suggest_activities: {suggest_activities}")
        print(f"Sources: {len(response['sources'])}")

        response_content = response["response"]
        if isinstance(response_content, dict) and hasattr(response_content, "content"):
            response_text = response_content.content
        else:
            response_text = response_content

        print(f"Response text preview: {str(response_text)[:100]}...")

        use_rag_answer = not (
            web_search or retrieval_confidence < config.rag.min_retrieval_confidence
        )
        rag_sources = list(response.get("sources") or []) if use_rag_answer else []

        # Keep partial RAG answer unless we are delegating to web search
        if use_rag_answer:
            response_output = AIMessage(
                content=strip_embedded_sources_section(str(response_text))
            )
        else:
            response_output = AIMessage(content="")

        return {
            **state,
            "output": response_output,
            "retrieval_confidence": retrieval_confidence,
            "agent_name": "RAG_AGENT",
            "web_search": web_search,
            "insufficient_info": web_search,
            "suggest_activities": suggest_activities,
            "rag_sources": rag_sources,
        }

    # Web Search Processor Node
    def run_web_search_processor_agent(state: AgentState) -> AgentState:
        """Handles web search results, processes them with LLM, and generates a refined response."""
        from app.chat_progress import emit_progress

        emit_progress("WEB_SEARCH_PROCESSOR_AGENT")
        print(f"Selected agent: WEB_SEARCH_PROCESSOR_AGENT")
        print("[WEB_SEARCH_PROCESSOR_AGENT] Processing Web Search Results...")
        
        memory_context = _agent_memory_context(state)
        web_search_processor = WebSearchProcessorAgent(config)

        processed = web_search_processor.process_web_search_results(
            query=state["current_input"],
            chat_history=memory_context,
        )
        response_content = str(processed.get("response", ""))
        suggest_activities = bool(processed.get("suggest_activities", False))
        web_sources = list(processed.get("sources") or [])

        # Merge any RAG citations gathered earlier (e.g. RAG -> web fallback)
        # with the fresh web-search sources, deduplicating by path.
        merged_sources: List[Dict[str, str]] = []
        seen_paths: set[str] = set()
        for src in (state.get("rag_sources") or []) + web_sources:
            path = str(src.get("path") or "").strip()
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            merged_sources.append(src)

        print(f"[WEB_SEARCH_PROCESSOR_AGENT] Sources: {len(merged_sources)}")

        if state['agent_name'] != None:
            involved_agents = f"{state['agent_name']}, WEB_SEARCH_PROCESSOR_AGENT"
        else:
            involved_agents = "WEB_SEARCH_PROCESSOR_AGENT"

        return {
            **state,
            "output": AIMessage(content=response_content),
            "agent_name": involved_agents,
            "suggest_activities": suggest_activities,
            "web_search": False,
            "rag_sources": merged_sources,
        }

    # Define Routing Logic
    def confidence_based_routing(state: AgentState) -> Dict[str, str]:
        """Route to web search when RAG explicitly requests it or retrieval confidence is low."""
        web_search = bool(state.get("web_search", False))
        low_confidence = state.get("retrieval_confidence", 0.0) < config.rag.min_retrieval_confidence
        print(f"Routing check - web_search: {web_search}, retrieval_confidence: {state.get('retrieval_confidence', 0.0)}")

        if web_search or low_confidence:
            from app.chat_progress import emit_progress

            emit_progress("WEB_SEARCH_PROCESSOR_AGENT")
            reason = "web_search flag" if web_search else "low retrieval confidence"
            print(f"Re-routed to Web Search Agent ({reason})...")
            return "WEB_SEARCH_PROCESSOR_AGENT"
        return "apply_guardrails"
    
    def _append_rag_sources(
        output_text: str,
        *,
        rag_sources: List[Dict[str, str]] | None,
        user_language: str,
    ) -> str:
        body = strip_embedded_sources_section(str(output_text or "")).rstrip()
        sources_section = format_rag_sources_section(rag_sources or [], user_language)
        if not sources_section:
            return body
        return f"{body}{sources_section}"

    # Check output through guardrails
    def apply_output_guardrails(state: AgentState) -> AgentState:
        """Apply output guardrails to the generated response."""
        from app.chat_progress import emit_progress

        emit_progress("apply_guardrails")
        output = state["output"]
        current_input = state["current_input"]

        # Check if output is valid
        if not output or not isinstance(output, (str, AIMessage)):
            return state

        output_text = output if isinstance(output, str) else output.content
        user_language = str(state.get("user_language") or "vi")
        rag_sources = state.get("rag_sources") or []
        
        # Get the original input text
        input_text = ""
        if isinstance(current_input, str):
            input_text = current_input
        elif isinstance(current_input, dict):
            input_text = current_input.get("text", "")

        from app.config import get_settings

        settings = get_settings()
        if not settings.enable_output_guardrails:
            final_text = _append_rag_sources(
                str(output_text or ""),
                rag_sources=rag_sources,
                user_language=user_language,
            )
            sanitized_message = AIMessage(content=final_text)
            updated: AgentState = {
                **state,
                "messages": sanitized_message,
                "output": sanitized_message,
            }
            from app.medical.agents.wellness_agent.retrieval import attach_wellness_after_retrieval

            return attach_wellness_after_retrieval(updated)
        
        # Apply output sanitization
        sanitized_output = guardrails.check_output(
            strip_embedded_sources_section(str(output_text or "")),
            input_text,
            user_language=user_language,
        )
        final_text = _append_rag_sources(
            sanitized_output,
            rag_sources=rag_sources,
            user_language=user_language,
        )

        sanitized_message = AIMessage(content=final_text)

        updated: AgentState = {
            **state,
            "messages": sanitized_message,
            "output": sanitized_message,
        }

        from app.medical.agents.wellness_agent.retrieval import attach_wellness_after_retrieval

        return attach_wellness_after_retrieval(updated)

    
    # Create the workflow graph
    workflow = StateGraph(AgentState)
    
    # Add nodes for each step
    workflow.add_node("analyze_input", analyze_input)
    workflow.add_node("route_to_agent", route_to_agent)
    workflow.add_node("CONVERSATION_AGENT", run_conversation_agent)
    workflow.add_node("RAG_AGENT", run_rag_agent)
    workflow.add_node("WEB_SEARCH_PROCESSOR_AGENT", run_web_search_processor_agent)
    workflow.add_node("apply_guardrails", apply_output_guardrails)
    
    # Define the edges (workflow connections)
    workflow.set_entry_point("analyze_input")
    workflow.add_conditional_edges(
        "analyze_input",
        route_after_analyze,
        {
            "apply_guardrails": "apply_guardrails",
            "route_to_agent": "route_to_agent",
        },
    )
    
    # Connect decision router to agents
    workflow.add_conditional_edges(
        "route_to_agent",
        lambda x: x["next"],
        {
            "CONVERSATION_AGENT": "CONVERSATION_AGENT",
            "RAG_AGENT": "RAG_AGENT",
            "WEB_SEARCH_PROCESSOR_AGENT": "WEB_SEARCH_PROCESSOR_AGENT",
            "needs_validation": "RAG_AGENT"  # Default to RAG if confidence is low
        }
    )
    
    workflow.add_edge("CONVERSATION_AGENT", "apply_guardrails")
    workflow.add_conditional_edges("RAG_AGENT", confidence_based_routing)
    workflow.add_edge("WEB_SEARCH_PROCESSOR_AGENT", "apply_guardrails")
    workflow.add_edge("apply_guardrails", END)
    
    # Compile the graph
    return workflow.compile(checkpointer=memory)


def init_agent_state() -> AgentState:
    """Initialize the agent state with default values."""
    return {
        "messages": [],
        "session_id": None,
        "conversation_summary": None,
        "user_long_term_memory": None,
        "prior_user_questions": None,
        "agent_name": None,
        "current_input": None,
        "output": None,
        "retrieval_confidence": 0.0,
        "bypass_routing": False,
        "insufficient_info": False,
        "web_search": False,
        "suggest_activities": False,
        "suggested_activities": [],
        "wellness_retrieval_score": None,
        "wellness_retrieval_source": None,
        "user_language": "vi",
        "rag_sources": [],
        "rag_sub_queries": [],
    }


def process_query(
    query: Union[str, Dict],
    *,
    thread_id: str,
    conversation_history: List[BaseMessage] | None = None,
    conversation_summary: str = "",
    user_long_term_memory: str = "",
    prior_user_questions: List[str] | None = None,
) -> dict:
    """
    Process a user query through the agent decision system.

    Args:
        query: User input text
        thread_id: LangGraph checkpoint id (use thesis session_id)
        conversation_history: Unused; history kept in MemorySaver per thread_id
        user_long_term_memory: Cross-session profile for logged-in users
        prior_user_questions: Mongo fallback for recent session questions

    Returns:
        Final graph state dict (messages, agent_name, output, ...)
    """
    from app.medical.workflow import get_compiled_medical_graph

    config = get_medical_config()
    graph = get_compiled_medical_graph()

    state = init_agent_state()
    state["current_input"] = query
    state["session_id"] = thread_id
    state["conversation_summary"] = (conversation_summary or "").strip()
    state["user_long_term_memory"] = (user_long_term_memory or "").strip()
    state["prior_user_questions"] = prior_user_questions or []

    message_text = extract_input_text(query) or str(query)

    state["messages"] = [HumanMessage(content=message_text)]

    thread_config = {"configurable": {"thread_id": thread_id}}
    # Progress is emitted at node entry (not on stream chunk) so UI updates during long LLM calls.
    for _chunk in graph.stream(state, thread_config):
        pass

    snapshot = graph.get_state(thread_config)
    result: dict = dict(snapshot.values) if snapshot and snapshot.values else {}
    if not result:
        result = graph.invoke(state, thread_config)

    messages = result.get("messages") or []
    if not isinstance(messages, list):
        messages = [messages] if messages else []
    if len(messages) > config.max_conversation_history:
        result["messages"] = messages[-config.max_conversation_history :]

    return result