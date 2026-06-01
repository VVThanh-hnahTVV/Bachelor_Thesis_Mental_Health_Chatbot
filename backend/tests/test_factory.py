from app.llm.factory import build_provider_chain, parse_fallback_chain, resolve_provider


def test_parse_fallback_chain():
    assert parse_fallback_chain("groq,openai") == ["groq", "openai"]
    assert parse_fallback_chain("bad,groq") == ["groq"]
    assert parse_fallback_chain("local,groq,openai,gemini") == [
        "local",
        "groq",
        "openai",
        "gemini",
    ]


def test_resolve_provider():
    assert resolve_provider(None, default="openai") == "openai"
    assert resolve_provider("local", default="openai") == "local"
    assert resolve_provider("GROQ", default="openai") == "groq"
    assert resolve_provider("nope", default="gemini") == "gemini"


def test_build_provider_chain_uses_settings_fallback_order(monkeypatch):
    class Settings:
        llm_fallback_chain = "local,groq,openai,gemini"
        enable_local_chat = True
        local_base_url = "http://localhost:11434/v1"
        groq_api_key = "g"
        openai_api_key = "o"
        google_api_key = "x"
        modal_base_url = None

    monkeypatch.setattr("app.llm.factory.get_settings", lambda: Settings())
    assert build_provider_chain("openai") == ["openai", "local", "groq", "gemini"]
