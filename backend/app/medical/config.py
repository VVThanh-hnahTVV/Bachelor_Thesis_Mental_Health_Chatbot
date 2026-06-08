"""Medical multi-agent configuration (paths under backend/)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from app.medical.embeddings import (
    build_embeddings,
    get_embedding_dim,
    get_embedding_provider,
    get_qdrant_collection_name,
)
from app.medical.llm import build_chat_llm, build_ingest_llm

load_dotenv()

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MEDICAL_AGENTS = BACKEND_ROOT / "app" / "medical" / "agents"
DATA_MEDICAL = BACKEND_ROOT / "data" / "medical"
UPLOADS_MEDICAL = BACKEND_ROOT / "uploads" / "medical"


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_domain_list(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


class AgentDecisoinConfig:
    def __init__(self) -> None:
        self.llm = build_chat_llm(temperature=0.1)


class ConversationConfig:
    def __init__(self) -> None:
        self.llm = build_chat_llm(temperature=0.7)


class WebSearchConfig:
    def __init__(self) -> None:
        self.llm = build_chat_llm(temperature=0.3)
        self.context_limit = 20
        self.enable_tavily = _env_bool("ENABLE_TAVILY_SEARCH", True)
        self.enable_pubmed = _env_bool("ENABLE_PUBMED_SEARCH", True)
        self.tavily_max_results = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
        self.tavily_search_depth = os.getenv("TAVILY_SEARCH_DEPTH", "advanced")
        self.tavily_include_domains = _parse_domain_list(
            os.getenv("TAVILY_INCLUDE_DOMAINS")
        )
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        self.pubmed_max_results = int(os.getenv("PUBMED_MAX_RESULTS", "5"))
        self.pubmed_esearch_url = os.getenv(
            "PUBMED_ESEARCH_URL",
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        )
        self.pubmed_efetch_url = os.getenv(
            "PUBMED_EFETCH_URL",
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        )
        self.pubmed_tool = os.getenv("PUBMED_TOOL", "MultiAgentMedicalAssistant")
        self.pubmed_email = os.getenv("PUBMED_EMAIL") or None
        self.pubmed_api_key = os.getenv("PUBMED_API_KEY") or os.getenv("NCBI_API_KEY")
        self.pubmed_europepmc_fallback = _env_bool("PUBMED_EUROPEPMC_FALLBACK", True)
        # false = Europe PMC only (recommended if NCBI blocked your IP)
        self.pubmed_use_ncbi = _env_bool("PUBMED_USE_NCBI", True)


class RAGConfig:
    def __init__(self) -> None:
        self.embedding_provider = get_embedding_provider()
        self.embedding_dim = get_embedding_dim(self.embedding_provider)
        self.vector_db_type = "qdrant"
        self.distance_metric = "Cosine"
        self.use_local = True
        self.vector_local_path = str(DATA_MEDICAL / "qdrant_db")
        self.doc_local_path = str(DATA_MEDICAL / "docs_db")
        self.parsed_content_dir = str(DATA_MEDICAL / "parsed_docs")
        self.raw_documents_dir = str(DATA_MEDICAL / "raw")
        self.document_metadata_path = os.getenv(
            "RAG_DOCUMENT_METADATA_PATH",
            str(DATA_MEDICAL / "document_metadata.json"),
        )
        self.url = os.getenv("QDRANT_URL")
        self.api_key = os.getenv("QDRANT_API_KEY")
        self.collection_name = get_qdrant_collection_name(
            self.embedding_provider, self.embedding_dim
        )
        self.chunk_size = int(os.getenv("INGEST_CHUNK_SIZE_WORDS", "512"))
        self.chunk_overlap = int(os.getenv("INGEST_CHUNK_OVERLAP_WORDS", "50"))
        self.chunk_batch_max_words = int(os.getenv("INGEST_CHUNK_BATCH_MAX_WORDS", "12000"))
        self.chunk_batch_max_sections = int(os.getenv("INGEST_CHUNK_BATCH_MAX_SECTIONS", "35"))
        self.chunk_target_min_words = int(os.getenv("INGEST_CHUNK_TARGET_MIN_WORDS", "256"))
        self.enable_llm_chunking = _env_bool("INGEST_LLM_CHUNKING", True)
        self.embedding_model = build_embeddings()
        self.llm = build_chat_llm(temperature=0.3)
        self.summarizer_model = build_ingest_llm(temperature=0.5, for_vision=True)
        self.chunker_model = build_ingest_llm(temperature=0.0)
        self.response_generator_model = build_chat_llm(temperature=0.3)
        self.top_k = 5
        self.vector_search_type = "similarity"
        self.huggingface_token = os.getenv("HUGGINGFACE_TOKEN")
        self.reranker_model = "cross-encoder/ms-marco-TinyBERT-L-6"
        self.reranker_top_k = 3
        self.max_context_length = 8192
        self.include_sources = True
        self.min_retrieval_confidence = 0.40
        self.context_limit = 20


class MedicalCVConfig:
    def __init__(self) -> None:
        cv_root = MEDICAL_AGENTS / "image_analysis_agent"
        self.brain_tumor_model_path = str(
            cv_root / "brain_tumor_agent" / "models" / "multi_class_resnet.pth"
        )
        self.brain_tumor_overlay_output_path = str(
            UPLOADS_MEDICAL / "brain_tumor_output" / "attention_overlay.png"
        )
        self.chest_xray_weights = os.getenv(
            "CHEST_XRAY_WEIGHTS", "densenet121-res224-all"
        )
        self.chest_xray_threshold = float(os.getenv("CHEST_XRAY_THRESHOLD", "0.5"))
        self.skin_lesion_model_path = str(
            cv_root / "skin_lesion_agent" / "models" / "checkpointN25_.pth.tar"
        )
        self.skin_lesion_segmentation_output_path = str(
            UPLOADS_MEDICAL / "skin_lesion_output" / "segmentation_plot.png"
        )
        self.llm = build_chat_llm(temperature=0.1, for_vision=True)


class SpeechConfig:
    def __init__(self) -> None:
        self.eleven_labs_api_key = os.getenv("ELEVEN_LABS_API_KEY")
        self.eleven_labs_voice_id = os.getenv(
            "ELEVEN_LABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"
        )
        self.eleven_labs_model_id = os.getenv(
            "ELEVEN_LABS_MODEL", "eleven_flash_v2_5"
        )


class ValidationConfig:
    def __init__(self) -> None:
        self.require_validation = {
            "CONVERSATION_AGENT": False,
            "RAG_AGENT": False,
            "WEB_SEARCH_AGENT": False,
            "BRAIN_TUMOR_AGENT": True,
            "CHEST_XRAY_AGENT": True,
            "SKIN_LESION_AGENT": True,
        }
        self.validation_timeout = 300
        self.default_action = "reject"


class APIConfig:
    def __init__(self) -> None:
        self.host = "0.0.0.0"
        self.port = 8000
        self.debug = True
        self.rate_limit = 10
        self.max_image_upload_size = 5


class UIConfig:
    def __init__(self) -> None:
        self.theme = "light"
        self.enable_speech = True
        self.enable_image_upload = True


class MedicalConfig:
    def __init__(self) -> None:
        self.agent_decision = AgentDecisoinConfig()
        self.conversation = ConversationConfig()
        self.rag = RAGConfig()
        self.medical_cv = MedicalCVConfig()
        self.web_search = WebSearchConfig()
        self.api = APIConfig()
        self.speech = SpeechConfig()
        self.validation = ValidationConfig()
        self.ui = UIConfig()
        self.eleven_labs_api_key = os.getenv("ELEVEN_LABS_API_KEY")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        self.max_conversation_history = 20
        self.llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()
        self.groq_model = os.getenv(
            "GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
        )
        self.embedding_provider = get_embedding_provider()
        self.ollama_embedding_model = os.getenv(
            "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text-v2-moe"
        )


# Alias used by vendored agent code
Config = MedicalConfig


@lru_cache
def get_medical_config() -> MedicalConfig:
    return MedicalConfig()
