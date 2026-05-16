from app.llm.factory import parse_fallback_chain, resolve_provider


def test_parse_fallback_chain():
    assert parse_fallback_chain("groq,openai") == ["groq", "openai"]
    assert parse_fallback_chain("bad,groq") == ["groq"]


def test_resolve_provider():
    assert resolve_provider(None, default="openai") == "openai"
    assert resolve_provider("GROQ", default="openai") == "groq"
    assert resolve_provider("nope", default="gemini") == "gemini"
