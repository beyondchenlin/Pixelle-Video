from pathlib import Path


def test_style_config_renders_ip_prompt_chain_controls() -> None:
    source = Path("web/components/style_config.py").read_text(encoding="utf-8")

    assert "def render_ip_prompt_chain_controls()" in source
    assert 'key="ip_enabled"' in source
    assert 'key="ip_asset_bible_id"' in source
    assert 'key="ip_profile_id"' in source


def test_style_config_returns_ip_prompt_chain_params_to_video_params() -> None:
    source = Path("web/components/style_config.py").read_text(encoding="utf-8")

    assert "ip_prompt_chain_settings = render_ip_prompt_chain_controls()" in source
    assert "**ip_prompt_chain_settings," in source
