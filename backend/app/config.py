from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator

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

    enable_internal_mcp_server: bool = False
    enable_external_mcp_gateway: bool = False
    enable_graph_external_enrichment: bool = False
    external_mcp_servers_json: str = "{}"
    external_mcp_allowed_tools: str = ""
    external_mcp_timeout_seconds: float = 6.0
    external_mcp_max_response_chars: int = 2000
    conversation_summary_max_tokens: int = Field(
        default=512,
        validation_alias=AliasChoices("CONVERSATION_SUMMARY_MAX_TOKENS"),
    )
    handoff_confidence_threshold: float = Field(
        default=0.85,
        validation_alias=AliasChoices("HANDOFF_CONFIDENCE_THRESHOLD"),
    )
    graph_external_mcp_server: str | None = None
    graph_external_mcp_tool: str | None = None

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

    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: str | None = None

    @field_validator(
        "cloudinary_cloud_name",
        "cloudinary_api_key",
        "cloudinary_api_secret",
        mode="before",
    )
    @classmethod
    def strip_cloudinary_settings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


ProviderName = Literal["local", "modal", "groq", "openai", "gemini"]
