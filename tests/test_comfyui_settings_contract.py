from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_settings_page_does_not_render_retired_gguf_cleanup_strategy():
    source = (PROJECT_ROOT / "web" / "components" / "settings.py").read_text(
        encoding="utf-8"
    )

    assert "gguf_cleanup_strategy" not in source
