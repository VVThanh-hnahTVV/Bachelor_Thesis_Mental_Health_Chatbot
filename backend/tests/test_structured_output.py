"""Structured RAG / web-search agent metadata."""

from app.medical.agents.structured_output import (
    RAGAgentOutput,
    WebSearchAgentOutput,
    merge_activities_intro,
    parse_rag_output,
    parse_web_search_output,
)


def test_parse_rag_output_json():
    raw = """{
        "answer": "Một số cách hỗ trợ ADHD...",
        "web_search": true,
        "suggest_activities": false,
        "activities_intro": ""
    }"""
    parsed = parse_rag_output(raw)
    assert parsed.web_search is True
    assert parsed.suggest_activities is False
    assert "ADHD" in parsed.answer


def test_merge_activities_intro_appends_when_suggested():
    merged = merge_activities_intro(
        "Các thói quen ngủ tốt...",
        suggest_activities=True,
        activities_intro="Nhấn nút **Mở** bên dưới để thử bài tập thư giãn.",
    )
    assert "Các thói quen ngủ tốt" in merged
    assert "Nhấn nút **Mở**" in merged
    assert merged.index("Các thói quen") < merged.index("Nhấn nút")


def test_merge_activities_intro_skipped_when_not_suggested():
    merged = merge_activities_intro(
        "Chỉ trả lời y khoa.",
        suggest_activities=False,
        activities_intro="Không nên hiện.",
    )
    assert merged == "Chỉ trả lời y khoa."


def test_parse_rag_output_fallback_vietnamese_insufficient():
    raw = "Mình không có đủ thông tin trong phần ngữ cảnh được cung cấp."
    parsed = parse_rag_output(raw)
    assert parsed.web_search is True
    assert parsed.suggest_activities is False


def test_parse_web_search_output_json():
    raw = """{
        "answer": "Các liệu pháp hành vi thường được dùng...",
        "suggest_activities": true,
        "activities_intro": "Bạn có thể mở bài tập bên dưới."
    }"""
    parsed = parse_web_search_output(raw)
    assert parsed.suggest_activities is True
    assert "liệu pháp" in parsed.answer
    assert "bên dưới" in parsed.activities_intro


def test_rag_model_fields():
    out = RAGAgentOutput(
        answer="ok",
        web_search=False,
        suggest_activities=True,
        activities_intro="Mở bài tập bên dưới.",
    )
    assert out.suggest_activities is True
    assert out.activities_intro


def test_web_model_fields():
    out = WebSearchAgentOutput(answer="ok", suggest_activities=False, activities_intro="")
    assert out.suggest_activities is False
