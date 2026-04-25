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
