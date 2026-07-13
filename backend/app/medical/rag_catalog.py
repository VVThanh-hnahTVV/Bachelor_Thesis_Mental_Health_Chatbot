"""Build RAG document catalog for the medical routing prompt from data/medical/raw."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf"}

TOPIC_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "infectious_disease": ("aids", "hiv", "outbreak", "infection"),
    "general_medicine": ("medical", "medicine", "clinical", "handbook", "book"),
}


@dataclass
class RawDocumentEntry:
    filename: str
    title: str
    topics: List[str] = field(default_factory=list)
    document_type: str = "document"
    authors: str = ""
    year: str = ""
    summary: str = ""

    def format_prompt_line(self) -> str:
        parts = [f"- {self.filename}: {self.title}"]
        if self.authors:
            parts.append(f"authors={self.authors}")
        if self.year:
            parts.append(f"year={self.year}")
        if self.topics:
            parts.append(f"topics={', '.join(self.topics)}")
        if self.document_type:
            parts.append(f"type={self.document_type}")
        if self.summary:
            parts.append(f"covers={self.summary}")
        return " | ".join(parts)


def _humanize_filename(stem: str) -> str:
    text = stem.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.title() if text else stem


def _infer_topics(filename: str) -> List[str]:
    lowered = filename.lower()
    topics: List[str] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            topics.append(topic)
    return topics or ["general_medicine"]


def _load_metadata_registry(metadata_path: str) -> Dict[str, Dict[str, Any]]:
    path = Path(metadata_path)
    if not path.is_file():
        return {}

    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load document metadata from %s: %s", path, exc)
        return {}

    documents = payload.get("documents", payload)
    if not isinstance(documents, dict):
        logger.warning("Invalid document metadata format in %s", path)
        return {}

    registry: Dict[str, Dict[str, Any]] = {}
    for filename, raw in documents.items():
        if isinstance(raw, dict):
            registry[os.path.basename(filename).lower()] = raw
    return registry


def _parse_topics(raw_topics: Any, filename: str) -> List[str]:
    if isinstance(raw_topics, list):
        return [str(topic).strip() for topic in raw_topics if str(topic).strip()]
    if isinstance(raw_topics, str) and raw_topics.strip():
        return [topic.strip() for topic in raw_topics.split(",") if topic.strip()]
    return _infer_topics(filename)


def _build_entry(filename: str, metadata: Optional[Dict[str, Any]]) -> RawDocumentEntry:
    stem = Path(filename).stem
    if metadata:
        authors_raw = metadata.get("authors", "")
        if isinstance(authors_raw, list):
            authors = "; ".join(str(author) for author in authors_raw)
        else:
            authors = str(authors_raw or "")

        year_raw = metadata.get("year")
        year = str(year_raw) if year_raw not in (None, "") else ""

        return RawDocumentEntry(
            filename=filename,
            title=str(metadata.get("title") or _humanize_filename(stem)),
            topics=_parse_topics(metadata.get("topics"), filename),
            document_type=str(metadata.get("document_type") or "document"),
            authors=authors,
            year=year,
            summary=str(metadata.get("summary") or ""),
        )

    return RawDocumentEntry(
        filename=filename,
        title=_humanize_filename(stem),
        topics=_infer_topics(filename),
        document_type="document",
    )


def list_raw_documents(
    raw_dir: str,
    metadata_path: str,
) -> List[RawDocumentEntry]:
    """Scan raw PDFs and merge optional bibliographic metadata."""
    raw_path = Path(raw_dir)
    if not raw_path.is_dir():
        logger.warning("Raw documents directory not found: %s", raw_path)
        return []

    registry = _load_metadata_registry(metadata_path)
    entries: List[RawDocumentEntry] = []

    for file_path in sorted(raw_path.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        entries.append(
            _build_entry(file_path.name, registry.get(file_path.name.lower()))
        )

    return entries


def _load_web_catalog(web_catalog_path: str) -> List[Dict[str, Any]]:
    path = Path(web_catalog_path)
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load web catalog from %s: %s", path, exc)
        return []
    articles = payload.get("articles", [])
    return [a for a in articles if isinstance(a, dict)]


def build_web_catalog_section(web_catalog_path: str) -> str:
    articles = _load_web_catalog(web_catalog_path)
    if not articles:
        return (
            "   (No indexed mental-health news articles yet. "
            "Mental-health news questions may still use RAG_AGENT if PDF sources match.)"
        )
    lines = [
        "   Indexed mental-health news / web articles (curated, admin-approved):",
    ]
    for article in articles[:25]:
        title = str(article.get("title") or "Untitled")
        publisher = str(article.get("publisher") or "")
        language = str(article.get("language") or "")
        lines.append(f"   - {title} | publisher={publisher} | lang={language} | topics=mental_health")
    return "\n".join(lines)


def build_rag_catalog_section(
    raw_dir: str,
    metadata_path: str,
    web_catalog_path: str = "",
) -> str:
    """Format ingested-source metadata for the routing system prompt."""
    entries = list_raw_documents(raw_dir, metadata_path)
    sections: List[str] = []

    if entries:
        sections.append("   PDF / textbook ingested sources:")
        sections.extend(f"   {entry.format_prompt_line()}" for entry in entries)
    else:
        sections.append(
            "   (No ingested PDF documents found in the raw knowledge base yet.)"
        )

    if web_catalog_path:
        sections.append(build_web_catalog_section(web_catalog_path))

    if not entries and not web_catalog_path:
        return (
            "   (No ingested documents found. "
            "Prefer CONVERSATION_AGENT or WEB_SEARCH_PROCESSOR_AGENT for medical questions.)"
        )

    header = "   Use RAG_AGENT when the user's question matches one of these ingested sources:"
    return header + "\n" + "\n".join(sections)


DECISION_SYSTEM_PROMPT_BASE = """You are an intelligent medical triage system that routes user queries to
the appropriate specialized agent. Your job is to analyze the user's request and determine which agent
is best suited to handle it based on the query content, presence of images, and conversation context.

Available agents:
1. CONVERSATION_AGENT - For general chat, greetings, and non-medical questions.
2. RAG_AGENT - For specific medical knowledge questions that can be answered from established medical literature in the ingested knowledge base below.
{rag_catalog}
3. WEB_SEARCH_PROCESSOR_AGENT - For questions about recent medical developments, current outbreaks, or time-sensitive medical information not covered by the ingested sources, which mental information don't contain in rag.

### Conversation context for this routing decision
{conversation_context}

Make your decision based on these guidelines:
- Route general conversation, greetings, or non-medical questions to the conversation agent.
- If the user asks about recent medical developments or current health situations, use the web search processor agent.
- If the user asks specific medical knowledge questions that match an ingested source topic above, use the RAG agent.
- If the user shares symptoms or asks about conditions (e.g. anxiety, insomnia, stress, pain), use RAG_AGENT when the topic matches ingested sources, otherwise CONVERSATION_AGENT for empathetic guidance.
- New-session follow-ups: when SESSION SUMMARY and RECENT TURNS are empty but RELEVANT PAST SESSIONS shows what the user discussed most recently, treat a short/vague message (e.g. "sinh viên thì sao", "còn cách điều trị?") as CONTINUING the most recent past session's topic. Route to RAG_AGENT when that inherited topic matches ingested sources, and write sub_queries combining the inherited topic with the new aspect/group (e.g. past topic "đau đầu và sức khỏe tâm thần" + current "sinh viên thì sao" -> ["đau đầu do căng thẳng ở sinh viên", "stress headaches in students"]).
- Do NOT route to a separate wellness agent. Wellness activities are attached automatically after RAG or web search or conversation replies when the responding pipeline opts in (suggest_activities).

When you select RAG_AGENT, also provide sub_queries for retrieval:
- Return 1-4 sub-queries per distinct information need (definition, symptoms, treatment, mechanisms, etc.).
- For simple single-intent questions, sub_queries may contain one item.
- **Each sub_query must be self-contained for vector search** — include the medical topic/condition explicitly (not pronouns like "it", "đó", "bệnh này" alone).
- **Follow-up messages:** Read RECENT TURNS (question/answer pairs) in the conversation context above.
  - If the current message is short or omits the topic (e.g. "cách điều trị", "triệu chứng", "treatment", "how to treat"), inherit the active topic from the most recent prior turn.
  - Every sub_query must name that topic (correct typos when helpful, e.g. pstd -> PTSD).
  - Do NOT retrieve a different condition (e.g. do not answer PTSD follow-up with generic anxiety-disorder queries).
- Generate sub_queries in ALL languages present in the matched ingested sources (check the "lang=" field in the catalog above). If any matched source has lang=vi, also add Vietnamese sub-queries for the same intent.
- For non-RAG agents, set sub_queries to an empty list [].

Examples (assume conversation context shows recent question "pstd là gì" / assistant explained PTSD):
- Current: "cách điều trị" -> sub_queries: ["PTSD treatment methods", "điều trị PTSD", "post-traumatic stress disorder therapy"]
- Current: "triệu chứng" -> sub_queries: ["PTSD symptoms", "triệu chứng PTSD"]

Demographic / group follow-ups inherit the topic too (assume prior turn discussed headaches & mental health):
- Current: "Ở giáo viên thì sao" -> RAG_AGENT with sub_queries: ["đau đầu căng thẳng ở giáo viên", "stress headaches in teachers", "occupational stress and headaches"]
- Current: "sinh viên thì sao" -> RAG_AGENT with sub_queries: ["đau đầu do căng thẳng ở sinh viên", "stress headaches in students"]

Other examples:
- "Dạo này tôi hay lo âu mất ngủ" -> RAG_AGENT or CONVERSATION_AGENT
- "Bạn có hoạt động nào giảm căng thẳng không" -> CONVERSATION_AGENT
- "Tiểu đường type 2 là gì?" -> RAG_AGENT with sub_queries: ["type 2 diabetes definition symptoms"]
- "CBT là gì, cách điều trị?" -> RAG_AGENT with sub_queries: ["definition of cognitive behavioral therapy", "cognitive behavioral therapy treatment methods"]
- "Dị ứng và sức khỏe tâm thần có mối liên hệ ra sao?" -> RAG_AGENT with sub_queries: ["allergy and mental health relationship", "mối liên hệ giữa dị ứng và sức khỏe tâm thần"]
- "Chào Helios" -> CONVERSATION_AGENT with sub_queries: []

You must provide your answer in JSON format with the following structure:
{{
"agent": "AGENT_NAME",
"reasoning": "Your step-by-step reasoning for selecting this agent",
"confidence": 0.95,
"sub_queries": ["retrieval sub-query 1", "retrieval sub-query 2"]
}}
"""


def build_decision_system_prompt(
    raw_dir: str,
    metadata_path: str,
    web_catalog_path: str = "",
    *,
    conversation_context: str = "",
) -> str:
    """Build the full routing system prompt with catalog and per-request conversation context."""
    catalog = build_rag_catalog_section(
        raw_dir,
        metadata_path,
        web_catalog_path=web_catalog_path,
    )
    context_block = (conversation_context or "").strip() or (
        "(First turn — no prior user questions in this session.)"
    )
    return DECISION_SYSTEM_PROMPT_BASE.format(
        rag_catalog=catalog,
        conversation_context=context_block,
    )
