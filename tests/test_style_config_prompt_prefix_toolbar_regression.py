from pathlib import Path


def test_prompt_prefix_toolbar_is_rendered_via_helper_between_panel_and_preview():
    project_root = Path(__file__).resolve().parent.parent
    source = (project_root / "web" / "components" / "style_config.py").read_text(encoding="utf-8")
    current_prefix_section = source.split("def _render_image_prompt_prefix_library(", 1)[1]
    current_prefix_section = current_prefix_section.split("\ndef render_style_config(", 1)[0]

    assert "def _render_prompt_prefix_library_action_toolbar(" in source

    helper_call_index = current_prefix_section.index("_render_prompt_prefix_library_action_toolbar(")
    ai_panel_index = current_prefix_section.index('    if panel_mode == "ai":')
    preview_section_index = current_prefix_section.index('    preview_title = tr("style.preview_title")')

    assert ai_panel_index < helper_call_index < preview_section_index
