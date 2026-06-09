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
from app.medical.agents.rag_agent import MedicalRAG
from app.medical.prompts import MARKDOWN_RESPONSE_INSTRUCTIONS, PLAIN_LANGUAGE_MEDICAL_INSTRUCTIONS
from app.medical.agents.web_search_processor_agent import WebSearchProcessorAgent
from app.medical.agents.guardrails.local_guardrails import LocalGuardrails
from app.medical.config import get_medical_config
from app.medical.rag_catalog import build_decision_system_prompt
from app.medical.validation_input import extract_input_text

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
    agent_name: Optional[str]  # Current active agent
    current_input: Optional[Union[str, Dict]]  # Input to be processed
    output: Optional[str]  # Final output to user
    retrieval_confidence: float  # Confidence in retrieval (for RAG agent)
    bypass_routing: bool  # Flag to bypass agent routing for guardrails
    insufficient_info: bool  # Deprecated alias; use web_search
    web_search: bool  # RAG requests follow-up web search when context is incomplete
    suggest_activities: bool  # Agent decision: show wellness activity buttons
    suggested_activities: Optional[List[Dict[str, str]]]  # Wellness activity suggestions for UI
    wellness_retrieval_score: Optional[float]
    wellness_retrieval_source: Optional[str]


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

    return build_agent_memory_context(
        conversation_summary=str(state.get("conversation_summary") or ""),
        messages=state.get("messages") or [],
        current_input=_input_text_from_state(state),
    )


def create_agent_graph():
    """Create and configure the LangGraph for agent orchestration."""
    config = get_medical_config()

    # Initialize guardrails with the same LLM used elsewhere
    guardrails = LocalGuardrails(config.rag.llm)

    # LLM
    decision_model = config.agent_decision.llm
    
    # Initialize the output parser
    json_parser = JsonOutputParser(pydantic_object=AgentDecision)
    
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
            from app.conversation.context import format_recent_user_questions

            summary = str(state.get("conversation_summary") or "").strip()
            recent_questions = format_recent_user_questions(
                state.get("messages") or [],
                limit=5,
                exclude_current=input_text,
            )
            is_allowed, message = guardrails.check_input(
                input_text,
                conversation_summary=summary,
                recent_user_questions=recent_questions,
            )
            if not is_allowed:
                # If input is blocked, return early with guardrail message
                print(f"Selected agent: INPUT GUARDRAILS, Message: ", message)
                blocked = message if isinstance(message, AIMessage) else AIMessage(content=str(message))
                return {
                    **state,
                    "messages": [blocked],
                    "output": blocked,
                    "agent_name": "INPUT_GUARDRAILS",
                    "bypass_routing": True,
                }
        
        return {
            **state,
            "bypass_routing": False  # Explicitly set to False for normal flow
        }
    
    def route_after_analyze(state: AgentState) -> str:
        if state.get("bypass_routing", False):
            return "apply_guardrails"
        return "route_to_agent"

    def route_to_agent(state: AgentState) -> Dict:
        """Make decision about which agent should handle the query."""
        from app.chat_progress import emit_progress

        emit_progress("medical_route")
        input_text = _input_text_from_state(state)
        memory_context = _agent_memory_context(state)

        decision_input = f"""
        User query: {input_text}

        Conversation memory:
        {memory_context}

        Based on this information, which agent should handle this query?
        """
        
        # Rebuild routing prompt from raw/ so new ingested PDFs are reflected automatically
        system_prompt = build_decision_system_prompt(
            raw_dir=config.rag.raw_documents_dir,
            metadata_path=config.rag.document_metadata_path,
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

        emit_progress(str(decision["agent"]))
        
        # Update state with decision
        updated_state = {
            **state,
            "agent_name": decision["agent"],
        }
        
        # Route based on agent name and confidence
        if decision["confidence"] < AgentConfig.CONFIDENCE_THRESHOLD:
            return {"agent_state": updated_state, "next": "needs_validation"}
        
        return {"agent_state": updated_state, "next": decision["agent"]}

    # Define agent execution functions (these will be implemented in their respective modules)
    def run_conversation_agent(state: AgentState) -> AgentState:
        """Handle general conversation."""
        from app.chat_progress import emit_progress

        emit_progress("CONVERSATION_AGENT")
        print(f"Selected agent: CONVERSATION_AGENT")

        input_text = _input_text_from_state(state)
        memory_context = _agent_memory_context(state)

        conversation_prompt = f"""User query: {input_text}

        Conversation memory:
        {memory_context}

        You are Helios, an AI-powered medical conversation assistant. Your goal is to facilitate smooth and informative conversations with users, handling both casual and medical-related queries. You must respond naturally while ensuring medical accuracy and clarity.

        ### Identity & tone
        - Say "Mình là Helios" (or introduce yourself by name) ONLY on the first turn of a chat, when the user greets you, or when they explicitly ask who you are.
        - If there is prior conversation in the memory context above, do NOT re-introduce yourself — answer the user's question directly.
        - Never open follow-up replies with "Mình là Helios" or similar self-introductions.

        ### Role & Capabilities
        - Engage in **general conversation** while maintaining professionalism.
        - Answer **medical questions** using verified knowledge.
        - Route **complex queries** to RAG (retrieval-augmented generation) or web search if needed.
        - Handle **follow-up questions** while keeping track of conversation context.

        ### Guidelines for Responding:
        1. **General Conversations:**
        - If the user engages in casual talk (e.g., greetings, small talk), respond in a friendly, engaging manner.
        - On greetings or first contact only: briefly introduce yourself as Helios, then invite their question.
        - On follow-up messages: skip greetings and self-introduction; respond to what they asked.
        - Keep responses **concise and engaging**, unless a detailed answer is needed.

        2. **Medical Questions:**
        - If you have **high confidence** in answering, provide a medically accurate response.
        - Ensure responses are **clear, concise, and factual**.

        3. **Follow-Up & Clarifications:**
        - Maintain conversation history for better responses.
        - If a query is unclear, ask **follow-up questions** before answering.

        {PLAIN_LANGUAGE_MEDICAL_INSTRUCTIONS}

        4. **Uncertainty & Ethical Considerations:**
        - If unsure, **never assume** medical facts.
        - Recommend consulting a **licensed healthcare professional** for serious medical concerns.
        - Avoid providing **medical diagnoses** or **prescriptions**—stick to general knowledge.

        ### Response Format:
        - Maintain a **conversational yet professional tone**.
        - If pulling from external sources (RAG/Web Search), mention **where the information is from** (e.g., "According to Mayo Clinic...").
        - If a user asks for a diagnosis, remind them to **seek medical consultation**.

        {MARKDOWN_RESPONSE_INSTRUCTIONS}

        ### Example User Queries & Responses:

        **User:** "Hey, how's your day going?" (first message)
        **You:** "Chào bạn! Mình là Helios, trợ lý y tế AI. Mình có thể giúp gì cho bạn hôm nay?"

        **User:** "Mình cảm thấy hơi rát họng" (follow-up — Assistant already replied before)
        **You:** "Rát họng thường gặp khi nhiễm đường hô hấp trên. Bạn có thể uống nước ấm, nghỉ giọng và tránh khói thuốc. Nếu kéo dài hoặc sốt cao, nên đi khám bác sĩ."

        **User:** "I have a headache and fever. What should I do?" (follow-up)
        **You:** "Headaches and fever can have various causes, from infections to dehydration. If your symptoms persist, you should see a medical professional."

        Conversational LLM Response:"""

        # print("Conversation Prompt:", conversation_prompt)

        response = config.conversation.llm.invoke(conversation_prompt)
        response_text = response.content if hasattr(response, "content") else str(response)
        if "Conversational LLM Response:" in response_text:
            response_text = response_text.split("Conversational LLM Response:", 1)[-1].strip()

        return {
            **state,
            "output": AIMessage(content=response_text),
            "agent_name": "CONVERSATION_AGENT"
        }
    
    def run_rag_agent(state: AgentState) -> AgentState:
        """Handle medical knowledge queries using RAG."""
        from app.chat_progress import emit_progress

        emit_progress("RAG_AGENT")
        print(f"Selected agent: RAG_AGENT")

        rag_agent = MedicalRAG(config)
        query = state["current_input"]
        memory_context = _agent_memory_context(state)

        response = rag_agent.process_query(query, chat_history=memory_context)
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

        # Keep partial RAG answer unless we are delegating to web search
        if web_search or retrieval_confidence < config.rag.min_retrieval_confidence:
            response_output = AIMessage(content="")
        else:
            response_output = AIMessage(content=str(response_text))

        return {
            **state,
            "output": response_output,
            "retrieval_confidence": retrieval_confidence,
            "agent_name": "RAG_AGENT",
            "web_search": web_search,
            "insufficient_info": web_search,
            "suggest_activities": suggest_activities,
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
        
        # Get the original input text
        input_text = ""
        if isinstance(current_input, str):
            input_text = current_input
        elif isinstance(current_input, dict):
            input_text = current_input.get("text", "")
        
        # Apply output sanitization
        sanitized_output = guardrails.check_output(output_text, input_text)

        sanitized_message = AIMessage(content=sanitized_output)

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
    }


def process_query(
    query: Union[str, Dict],
    *,
    thread_id: str,
    conversation_history: List[BaseMessage] | None = None,
    conversation_summary: str = "",
) -> dict:
    """
    Process a user query through the agent decision system.

    Args:
        query: User input text
        thread_id: LangGraph checkpoint id (use thesis session_id)
        conversation_history: Unused; history kept in MemorySaver per thread_id

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