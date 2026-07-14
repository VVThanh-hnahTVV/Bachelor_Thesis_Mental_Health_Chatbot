from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "mental_health"

    # Local OpenAI-compatible chat (Ollama /v1). Off by default — use Ollama for embeddings only.
    enable_local_chat: bool = False
    local_base_url: str | None = "http://localhost:11434/v1"
    local_api_key: str = "ollama"
    completion_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("COMPLETION_MODEL", "OPENAI_MODEL"),
    )
    local_model: str = Field(
        default="llama3.1",
        validation_alias=AliasChoices("LOCAL_MODEL", "COMPLETION_MODEL"),
    )

    # OpenAI (chat + optional embeddings)
    openai_api_key: str | None = None
    openai_admin_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_ADMIN_API_KEY"),
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "COMPLETION_MODEL"),
    )

    # Groq
    groq_api_key: str | None = None
    groq_model: str = Field(
        default="meta-llama/llama-4-scout-17b-16e-instruct",
        validation_alias=AliasChoices("GROQ_MODEL", "COMPLETION_MODEL"),
    )

    # Gemini
    google_api_key: str | None = None
    gemini_model: str = Field(
        default="gemini-1.5-flash",
        validation_alias=AliasChoices("GEMINI_MODEL", "COMPLETION_MODEL"),
    )

    # Modal or any OpenAI-compatible custom base (fine-tuned server)
    modal_base_url: str | None = None
    modal_api_key: str = "dummy"
    modal_model: str = Field(
        default="default",
        validation_alias=AliasChoices("MODAL_MODEL", "COMPLETION_MODEL"),
    )

    # Fallback order when primary fails (comma-separated provider names)
    llm_fallback_chain: str = "groq,openai,gemini"

    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 7200  # 2 hours
    user_long_term_memory_cache_ttl_seconds: int = Field(
        default=86400,
        validation_alias=AliasChoices("USER_LONG_TERM_MEMORY_CACHE_TTL_SECONDS"),
    )

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 168

    frontend_url: str = "http://localhost:3000"
    password_reset_expire_minutes: int = 60

    maildev_incoming_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MAILDEV_INCOMING_USER"),
    )
    maildev_incoming_pass: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MAILDEV_INCOMING_PASS"),
    )

    debug_llm_prompts: bool = True 

    enable_input_guardrails: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_INPUT_GUARDRAILS"),
    )
    enable_output_guardrails: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_OUTPUT_GUARDRAILS"),
    )

    enable_user_daily_chat_limit: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_USER_DAILY_CHAT_LIMIT"),
    )
    user_daily_chat_limit: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("USER_DAILY_CHAT_LIMIT"),
    )
    ip_daily_chat_limit: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("IP_DAILY_CHAT_LIMIT"),
    )

    # Cap for summary/brief completions. Reasoning models (e.g. gpt-5.x)
    # count thinking tokens against this budget, so keep it well above the
    # expected visible output length or the completion comes back empty.
    conversation_summary_max_tokens: int = Field(
        default=2048,
        validation_alias=AliasChoices("CONVERSATION_SUMMARY_MAX_TOKENS"),
    )
    # Consolidate the rolling summary only after this many un-summarized user turns.
    # The last 5 raw turns are always injected into agent context regardless.
    summary_consolidate_after_turns: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("SUMMARY_CONSOLIDATE_AFTER_TURNS"),
    )
    # Hybrid trigger: also consolidate before the turn threshold when the
    # pending (un-summarized) transcript exceeds this estimated token budget
    # (~4 chars/token) — protects the summarizer from very long user messages.
    summary_consolidate_after_tokens: int = Field(
        default=1500,
        ge=100,
        validation_alias=AliasChoices("SUMMARY_CONSOLIDATE_AFTER_TOKENS"),
    )

    # Episodic long-term memory: one record per finished session, retrieved by
    # relevance to the current query instead of one ever-growing merged profile.
    enable_episodic_memory: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_EPISODIC_MEMORY"),
    )
    episodic_memory_top_k: int = Field(
        default=3,
        ge=1,
        validation_alias=AliasChoices("EPISODIC_MEMORY_TOP_K"),
    )
    episodic_memory_min_score: float = Field(
        default=0.35,
        validation_alias=AliasChoices("EPISODIC_MEMORY_MIN_SCORE"),
    )
    episodic_memory_recency_half_life_days: float = Field(
        default=30.0,
        gt=0,
        validation_alias=AliasChoices("EPISODIC_MEMORY_RECENCY_HALF_LIFE_DAYS"),
    )
    episodic_memory_recency_weight: float = Field(
        default=0.10,
        ge=0,
        validation_alias=AliasChoices("EPISODIC_MEMORY_RECENCY_WEIGHT"),
    )
    # First turn of a new session waits this long for previous sessions to be
    # folded into episodic memory, so retrieval can already see them.
    episodic_finalize_inline_timeout_seconds: float = Field(
        default=8.0,
        gt=0,
        validation_alias=AliasChoices("EPISODIC_FINALIZE_INLINE_TIMEOUT_SECONDS"),
    )
    # Sessions shorter than this many user turns are not worth remembering
    # (single vague questions pollute retrieval with near-duplicate text).
    episodic_memory_min_turns: int = Field(
        default=2,
        ge=1,
        validation_alias=AliasChoices("EPISODIC_MEMORY_MIN_TURNS"),
    )
    # Idle checkpoint: a session with no new messages for this long is folded
    # into episodic memory early. The session stays open — the user keeps the
    # full short-term context when they resume. 0 disables the sweeper.
    session_idle_finalize_minutes: int = Field(
        default=30,
        ge=0,
        validation_alias=AliasChoices("SESSION_IDLE_FINALIZE_MINUTES"),
    )
    session_idle_sweep_interval_seconds: int = Field(
        default=300,
        ge=30,
        validation_alias=AliasChoices("SESSION_IDLE_SWEEP_INTERVAL_SECONDS"),
    )
    handoff_confidence_threshold: float = Field(
        default=0.85,
        validation_alias=AliasChoices("HANDOFF_CONFIDENCE_THRESHOLD"),
    )

    # None = auto: OpenAI embeddings when OPENAI_API_KEY is set, else Ollama
    embedding_provider: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_PROVIDER"),
    )
    embedding_model: str = Field(
        default="nomic-embed-text-v2-moe",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "OLLAMA_EMBEDDING_MODEL"),
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias=AliasChoices("OPENAI_EMBEDDING_MODEL"),
    )
    ollama_base_url: str = "http://localhost:11434"
    llm_judge_provider: str = "openai"
    llm_judge_model: str = "gpt-4o-mini"

    enable_medical_mode: bool = True
    tavily_api_key: str | None = None
    huggingface_token: str | None = None

    eleven_labs_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ELEVEN_LABS_API_KEY"),
    )
    eleven_labs_stt_model: str = Field(
        default="scribe_v2",
        validation_alias=AliasChoices("ELEVEN_LABS_STT_MODEL"),
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


ProviderName = Literal["local", "modal", "groq", "openai", "gemini"]
