from web.utils.prompt_prefix_ui import (
    create_prompt_prefix_item,
    get_localized_prompt_prefix_category_options,
    persist_uploaded_prompt_prefix_preview,
    sanitize_prompt_prefix_preview_selection,
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
        preview_asset_path=" resources/prompt_prefix_previews/custom/card.svg ",
    )

    assert item["id"] == "manual-test"
    assert item["name"] == "Warm Storybook"
    assert item["content"] == "warm storybook illustration"
    assert item["style_category_id"] == "storybook"
    assert item["scene_category_id"] == "childrens_story"
    assert item["note"] == "soft and healing"
    assert item["preview_asset_path"] == "resources/prompt_prefix_previews/custom/card.svg"


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


def test_sanitize_prompt_prefix_preview_selection_prunes_stale_ids_and_preserves_order():
    selected_ids = ["library-a", "old-generated", "library-b", "library-a"]

    sanitized = sanitize_prompt_prefix_preview_selection(
        selected_ids,
        valid_ids={"library-a", "library-b", "generated-c"},
    )

    assert sanitized == ["library-a", "library-b"]


class _FakeUpload:
    def __init__(self, name: str, payload: bytes):
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


def test_persist_uploaded_prompt_prefix_preview_writes_relative_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "web.utils.prompt_prefix_ui.CUSTOM_PROMPT_PREFIX_PREVIEW_DIR",
        tmp_path / "prompt_prefix_previews" / "custom",
    )

    asset_path = persist_uploaded_prompt_prefix_preview(
        _FakeUpload("story-cover.svg", b"<svg/>"),
        "manual-test",
    )

    assert asset_path == (tmp_path / "prompt_prefix_previews" / "custom" / "manual-test.svg").as_posix()
    assert Path(asset_path).read_bytes() == b"<svg/>"


def test_persist_uploaded_prompt_prefix_preview_falls_back_to_png_suffix(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "web.utils.prompt_prefix_ui.CUSTOM_PROMPT_PREFIX_PREVIEW_DIR",
        tmp_path / "prompt_prefix_previews" / "custom",
    )

    asset_path = persist_uploaded_prompt_prefix_preview(
        _FakeUpload("story-cover.bin", b"png-bytes"),
        "manual-test",
    )

    assert asset_path.endswith(".png")


def test_style_config_source_references_prompt_prefix_library_ui():
    project_root = Path(__file__).resolve().parent.parent
    source = (project_root / "web" / "components" / "style_config.py").read_text(encoding="utf-8")

    assert "prompt_prefix_library" in source
    assert "toggle_prompt_prefix_preview_selection" in source
    assert "build_prompt_prefix_generation_prompt" in source
    assert "get_prompt_prefix_preview_asset" in source
    assert "prompt_prefix_panel_mode" in source
    assert "style.prefix_library.toolbar_add" in source
    assert "style.prefix_library.compare_count" in source


def test_prompt_prefix_library_locale_keys_exist():
    project_root = Path(__file__).resolve().parent.parent

    for locale_name in ("en_US", "zh_CN"):
        locale_path = project_root / "web" / "i18n" / "locales" / f"{locale_name}.json"
        translations = json.loads(locale_path.read_text(encoding="utf-8"))["t"]

        assert "style.prefix_library.title" in translations
        assert "style.prefix_library.add_to_preview" in translations
        assert "style.prefix_library.ai_generate" in translations
        assert "style.prefix_library.toolbar_add" in translations
        assert "style.prefix_library.compare_count" in translations
