from pathlib import Path


def test_style_config_renders_series_visual_signature_controls() -> None:
    source = Path("web/components/series_visual_signature_controls.py").read_text(encoding="utf-8")

    assert "def render_series_visual_signature_controls(" in source
    assert '"series_visual_signature_enabled": True' in source
    assert '"series_visual_signature_asset_bible_id": asset_bible_id' in source
    assert '"series_visual_signature_profile_id": series_visual_signature_profile_id' in source


def test_style_config_returns_ip_prompt_chain_params_to_video_params() -> None:
    source = Path("web/components/content_series_visual_signature_controls.py").read_text(encoding="utf-8")

    assert "ip_payload = render_series_visual_signature_controls(" in source
    assert "return build_content_ip_world_payload(" in source
    assert "ip_payload=ip_payload" in source
