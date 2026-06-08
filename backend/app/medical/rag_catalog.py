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
    "brain_tumor": ("brain", "tumor", "mri", "glioma"),
    "chest_imaging": ("chest", "xray", "x-ray", "radiograph", "pneumonia", "covid"),
    "skin_lesion": ("skin", "lesion", "melanoma", "dermat"),
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


def build_rag_catalog_section(
    raw_dir: str,
    metadata_path: str,
) -> str:
    """Format ingested-source metadata for the routing system prompt."""
    entries = list_raw_documents(raw_dir, metadata_path)
    if not entries:
        return (
            "   (No ingested documents found in the raw knowledge base yet. "
            "Prefer CONVERSATION_AGENT or WEB_SEARCH_PROCESSOR_AGENT for medical questions.)"
        )

    lines = [
        "   Use RAG_AGENT when the user's question matches one of these ingested sources:",
        *[
            f"   {entry.format_prompt_line()}"
            for entry in entries
        ],
    ]
    return "\n".join(lines)


DECISION_SYSTEM_PROMPT_BASE = """You are an intelligent medical triage system that routes user queries to
the appropriate specialized agent. Your job is to analyze the user's request and determine which agent
is best suited to handle it based on the query content, presence of images, and conversation context.

Available agents:
1. CONVERSATION_AGENT - For general chat, greetings, and non-medical questions.
2. RAG_AGENT - For specific medical knowledge questions that can be answered from established medical literature in the ingested knowledge base below.
{rag_catalog}
3. WEB_SEARCH_PROCESSOR_AGENT - For questions about recent medical developments, current outbreaks, or time-sensitive medical information not covered by the ingested sources.
4. BRAIN_TUMOR_AGENT - For analysis of brain MRI images to detect and segment tumors.
5. CHEST_XRAY_AGENT - For multi-pathology chest X-ray screening (pneumonia, edema, pneumothorax, cardiomegaly, effusion, and related findings).
6. SKIN_LESION_AGENT - For analysis of skin lesion images to classify them as benign or malignant.

Make your decision based on these guidelines:
- If the user has not uploaded any image, always route to the conversation agent.
- If the user uploads a medical image, decide which medical vision agent is appropriate based on the image type and the user's query. If the image is uploaded without a query, always route to the correct medical vision agent based on the image type.
- If the user asks about recent medical developments or current health situations, use the web search pocessor agent.
- If the user asks specific medical knowledge questions that match an ingested source topic above, use the RAG agent.
- For general conversation, greetings, or non-medical questions, use the conversation agent. But if image is uploaded, always go to the medical vision agents first.

You must provide your answer in JSON format with the following structure:
{{
"agent": "AGENT_NAME",
"reasoning": "Your step-by-step reasoning for selecting this agent",
"confidence": 0.95  // Value between 0.0 and 1.0 indicating your confidence in this decision
}}
"""


def build_decision_system_prompt(
    raw_dir: str,
    metadata_path: str,
) -> str:
    """Build the full routing system prompt with up-to-date raw document metadata."""
    catalog = build_rag_catalog_section(raw_dir, metadata_path)
    return DECISION_SYSTEM_PROMPT_BASE.format(rag_catalog=catalog)
