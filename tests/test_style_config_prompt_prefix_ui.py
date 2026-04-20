from web.utils.prompt_prefix_ui import (
    create_prompt_prefix_item,
    get_localized_prompt_prefix_category_options,
    toggle_prompt_prefix_preview_selection,
)
import json
from pathlib import Path


def test_create_prompt_prefix_item_trims_fields_and_preserves_category_ids():
    item = create_prompt_prefix_item(
        item_id="manual-test",
        name="  Warm Storybook  ",
        content="  warm storybook illustration  ",
        style_category_id="storybook",
        scene_category_id="childrens_story",
        note="  soft and healing  ",
        source="manual",
    )

    assert item["id"] == "manual-test"
    assert item["name"] == "Warm Storybook"
    assert item["content"] == "warm storybook illustration"
    assert item["style_category_id"] == "storybook"
    assert item["scene_category_id"] == "childrens_story"
    assert item["note"] == "soft and healing"


def test_get_localized_prompt_prefix_category_options_exposes_human_labels():
    style_options, scene_options = get_localized_prompt_prefix_category_options(language="en_US")

    assert style_options[0]["id"]
    assert style_options[0]["label"]
    assert any(option["id"] == "storybook" for option in style_options)
    assert any(option["id"] == "childrens_story" for option in scene_options)


def test_toggle_prompt_prefix_preview_selection_adds_and_removes_items():
    selected_ids = []

    selected_ids = toggle_prompt_prefix_preview_selection(selected_ids, "prefix-a")
    assert selected_ids == ["prefix-a"]

    selected_ids = toggle_prompt_prefix_preview_selection(selected_ids, "prefix-a")
    assert selected_ids == []


def test_style_config_source_references_prompt_prefix_library_ui():
    project_root = Path(__file__).resolve().parent.parent
    source = (project_root / "web" / "components" / "style_config.py").read_text(encoding="utf-8")

    assert "prompt_prefix_library" in source
    assert "toggle_prompt_prefix_preview_selection" in source
    assert "build_prompt_prefix_generation_prompt" in source


def test_prompt_prefix_library_locale_keys_exist():
    project_root = Path(__file__).resolve().parent.parent

    for locale_name in ("en_US", "zh_CN"):
        locale_path = project_root / "web" / "i18n" / "locales" / f"{locale_name}.json"
        translations = json.loads(locale_path.read_text(encoding="utf-8"))["t"]

        assert "style.prefix_library.title" in translations
        assert "style.prefix_library.add_to_preview" in translations
        assert "style.prefix_library.ai_generate" in translations
