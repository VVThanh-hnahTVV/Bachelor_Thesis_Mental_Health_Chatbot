from app.crawl.keywords import passes_strict_mental_health_filter


def test_primary_keyword_in_title_passes():
    ok, score, kw = passes_strict_mental_health_filter(
        "Tưởng rối loạn tâm thần, người bệnh hôn mê sâu",
        "Nội dung bài viết không có keyword mạnh.",
    )
    assert ok is True
    assert score > 0
    assert any("tâm thần" in k for k in kw)


def test_secondary_only_title_fails():
    ok, score, kw = passes_strict_mental_health_filter(
        "Điều gì xảy ra với não bộ khi uống cà phê mỗi ngày?",
        "Cà phê có thể ảnh hưởng tâm trạng.",
    )
    assert ok is False
    assert score == 0.0
    assert kw == []


def test_english_mental_health_title_passes():
    ok, _, kw = passes_strict_mental_health_filter(
        "CDC Launches Campaign for Youth Mental Health",
        "",
    )
    assert ok is True
    assert "mental health" in kw


def test_health_guide_passes_via_body():
    ok, score, kw = passes_strict_mental_health_filter(
        "Borderline Personality Disorder",
        "Borderline personality disorder is a serious mental illness.",
        content_type="health_guide",
    )
    assert ok is True
    assert score > 0
    assert "mental illness" in kw or "personality disorder" in kw


def test_research_passes_via_abstract():
    ok, score, kw = passes_strict_mental_health_filter(
        "A randomized trial of intervention X in adolescents",
        "Background: Patients with major depression and anxiety were enrolled.",
        content_type="research_article",
    )
    assert ok is True
    assert score > 0
    assert "depression" in kw or "anxiety" in kw
