"""Application settings and LangChain chat models wired from environment."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _secret_present(value: SecretStr | None) -> bool:
    if value is None:
        return False
    return bool(value.get_secret_value().strip())


@dataclass(frozen=True, slots=True)
class LLMRegistry:
    """Holds initialized chat models; entries are ``None`` when no API key was set."""

    groq: ChatGroq | None
    openai: ChatOpenAI | None
    gemini: ChatGoogleGenerativeAI | None

    def available_providers(self) -> tuple[str, ...]:
        names: list[str] = []
        if self.groq is not None:
            names.append("groq")
        if self.openai is not None:
            names.append("openai")
        if self.gemini is not None:
            names.append("gemini")
        return tuple(names)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    groq_api_key: SecretStr | None = Field(default=None)
    open_api_key: SecretStr | None = Field(default=None)
    openai_api_key: SecretStr | None = Field(default=None)
    gemini_api_key: SecretStr | None = Field(default=None)

    groq_model: str = Field(default="llama-3.3-70b-versatile")
    openai_model: str = Field(default="gpt-4o-mini")
    gemini_model: str = Field(default="gemini-2.0-flash")

    mongo_uri: SecretStr = Field(..., alias='MONGO_URI')
    mongo_db_name: str = Field(default='mental_health', alias='MONGO_DB_NAME')
    jwt_secret_key: SecretStr = Field(..., alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    @model_validator(mode="after")
    def _strip_dummy_keys(self) -> Settings:
        updates: dict[str, object] = {}
        for name in (
            "groq_api_key",
            "open_api_key",
            "openai_api_key",
            "gemini_api_key",
        ):
            val = getattr(self, name)
            if val is not None and not val.get_secret_value().strip():
                updates[name] = None
        if updates:
            return self.model_copy(update=updates)
        return self

    def resolved_openai_key(self) -> SecretStr | None:
        if _secret_present(self.open_api_key):
            return self.open_api_key
        if _secret_present(self.openai_api_key):
            return self.openai_api_key
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()


def build_llm_registry(settings: Settings | None = None) -> LLMRegistry:
    """Construct chat clients only for providers with a non-empty API key."""
    s = settings or get_settings()

    groq: ChatGroq | None = None
    if _secret_present(s.groq_api_key):
        groq = ChatGroq(
            model=s.groq_model,
            api_key=s.groq_api_key.get_secret_value(),
        )

    openai: ChatOpenAI | None = None
    okey = s.resolved_openai_key()
    if okey is not None:
        openai = ChatOpenAI(
            model=s.openai_model,
            api_key=okey.get_secret_value(),
        )

    gemini: ChatGoogleGenerativeAI | None = None
    if _secret_present(s.gemini_api_key):
        gemini = ChatGoogleGenerativeAI(
            model=s.gemini_model,
            google_api_key=s.gemini_api_key.get_secret_value(),
        )

    return LLMRegistry(groq=groq, openai=openai, gemini=gemini)


@lru_cache
def get_llm_registry() -> LLMRegistry:
    """Cached registry for use across the app lifecycle (invalidate cache in tests if env changes)."""
    return build_llm_registry(get_settings())


@lru_cache
def get_mongo_client() -> AsyncIOMotorClient:
    s = get_settings()
    return AsyncIOMotorClient(s.mongo_uri.get_secret_value())

def get_database() -> AsyncIOMotorDatabase:
    s = get_settings()
    return get_mongo_client()[s.mongo_db_name]

