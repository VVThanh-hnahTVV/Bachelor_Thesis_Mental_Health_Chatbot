from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "mental_health"

    # OpenAI (chat + optional embeddings for seed script)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Groq
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"

    # Gemini
    google_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    # Modal or any OpenAI-compatible custom base (fine-tuned server)
    modal_base_url: str | None = None
    modal_api_key: str = "dummy"
    modal_model: str = "default"

    # Fallback order when primary fails (comma-separated provider names)
    llm_fallback_chain: str = "modal,openai,gemini,groq"

    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 7200  # 2 hours

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 168

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


ProviderName = Literal["modal", "groq", "openai", "gemini"]
