from __future__ import annotations

import inspect
from pathlib import Path

from web.components import content_input, recent_video_gallery, style_config


def test_home_page_uses_conditional_pipeline_rendering_instead_of_tabs():
    source = Path("web/pages/1_🎬_Home.py").read_text(encoding="utf-8")

    assert "st.tabs" not in source
    assert "get_all_pipeline_uis" not in source
    assert "get_pipeline_selection_entries" in source
    assert "get_pipeline_ui(selected_name)" in source


def test_home_recent_gallery_uses_one_on_demand_player_without_opening_local_files():
    card_source = inspect.getsource(recent_video_gallery.render_recent_video_card)
    player_source = inspect.getsource(recent_video_gallery.render_recent_video_player)

    assert "st.video" not in card_source
    assert "open(" not in card_source
    assert "download_button" not in card_source
    assert "link_button" in card_source
    assert "render_recent_video_player" in card_source
    assert "st.video" in player_source
    assert "autoplay=True" in player_source


def test_style_config_uses_one_template_selector_instead_of_preview_tabs():
    source = inspect.getsource(style_config.render_style_config)
    preview_source = inspect.getsource(
        style_config._render_template_picker_preview_on_demand
    )

    assert "st.tabs" not in source
    assert "template_gallery_choice_" in source
    assert "_render_template_picker_preview_on_demand" in source
    assert "st.button" in preview_source
    assert "_render_template_gallery_preview(" in preview_source


def test_version_panel_does_not_make_an_automatic_third_party_badge_request():
    source = inspect.getsource(content_input.render_version_info)

    assert "img.shields.io" not in source
    assert "link_button" in source
