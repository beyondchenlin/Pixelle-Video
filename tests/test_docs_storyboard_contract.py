from pathlib import Path

REFERENCE_DOCS = (
    Path("docs/en/reference/api-overview.md"),
    Path("docs/zh/reference/api-overview.md"),
)


def test_reference_api_docs_use_storyboard_generation_contract():
    for path in REFERENCE_DOCS:
        content = path.read_text(encoding="utf-8")
        assert "n_scenes" not in content
        assert "split_mode" not in content
        assert "storyboard_mode" in content
        assert "storyboard_count_mode" in content
        assert "storyboard_max_scene_count" in content
        assert "10000" in content


def test_storyboard_contract_doc_does_not_model_narration_text_as_frame_field():
    content = Path(
        "docs/superpowers/specs/2026-04-25-storyboard-generation-contract-design.md"
    ).read_text(encoding="utf-8")

    assert "narration_text: str" not in content
    assert '"narration_text"' not in content
    assert "frame.narration_text" not in content
    assert "CaptionSpeechPlan" in content
