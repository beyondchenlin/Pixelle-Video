from pathlib import Path


def test_style_config_renders_series_visual_signature_controls() -> None:
    source = Path("web/components/style_config.py").read_text(encoding="utf-8")

    assert "def render_series_visual_signature_controls()" in source
    assert 'key="series_visual_signature_enabled"' in source
    assert 'key="series_visual_signature_asset_bible_id"' in source
    assert 'key="series_visual_signature_profile_id"' in source


def test_style_config_returns_ip_prompt_chain_params_to_video_params() -> None:
    source = Path("web/components/style_config.py").read_text(encoding="utf-8")

    assert "ip_prompt_chain_settings = render_series_visual_signature_controls()" in source
    assert "**ip_prompt_chain_settings," in source
