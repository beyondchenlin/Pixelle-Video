import inspect
import asyncio
import json
import os
from pathlib import Path

import pytest

from pixelle_video.config import prompt_prefix_library
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from web.components import style_config
from web.utils.preview_media import PreviewMediaData
from web.utils.prompt_prefix_ui import (
    clone_prompt_prefix_preview_asset,
    create_prompt_prefix_item,
    delete_prompt_prefix_preview_asset,
    get_localized_prompt_prefix_category_options,
    get_prompt_prefix_form_item_id,
    persist_generated_prompt_prefix_preview,
    persist_generated_prompt_prefix_workflow_preview,
    persist_uploaded_prompt_prefix_preview,
    sanitize_prompt_prefix_preview_selection,
    toggle_prompt_prefix_preview_selection,
)


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
        workflow_preview_assets={
            " selfhost/image_z_image_turbo.json ": {
                "asset_path": " resources/prompt_prefix_previews/custom/manual-test.webp ",
            },
        },
    )

    assert item["id"] == "manual-test"
    assert item["name"] == "Warm Storybook"
    assert item["content"] == "warm storybook illustration"
    assert item["style_category_id"] == "storybook"
    assert item["scene_category_id"] == "childrens_story"
    assert item["note"] == "soft and healing"
    assert item["preview_asset_path"] == "resources/prompt_prefix_previews/custom/card.svg"
    assert item["workflow_preview_assets"] == {
        "selfhost/image_z_image_turbo.json": {
            "asset_path": "resources/prompt_prefix_previews/custom/manual-test.webp",
            "reference_prompt": None,
            "generated_at": None,
            "status": "ready",
        },
    }


def test_create_prompt_prefix_item_rejects_legacy_workflow_preview_strings():
    with pytest.raises(ValueError):
        create_prompt_prefix_item(
            item_id="manual-test",
            name="Warm Storybook",
            content="warm storybook illustration",
            style_category_id="storybook",
            scene_category_id="childrens_story",
            workflow_preview_assets={
                "selfhost/image_z_image_turbo.json": "resources/prompt_prefix_previews/custom/manual-test.webp",
            },
        )


def test_create_prompt_prefix_item_preserves_workflow_preview_metadata():
    item = create_prompt_prefix_item(
        item_id="manual-test",
        name="Warm Storybook",
        content="warm storybook illustration",
        style_category_id="storybook",
        scene_category_id="childrens_story",
        workflow_preview_assets={
            " selfhost/image_z_image_turbo.json ": {
                "asset_path": " resources/prompt_prefix_previews/custom/manual-test.webp ",
                "reference_prompt": " gallery cover prompt ",
                "generated_at": " 2026-04-22T12:34:56Z ",
                "status": " ready ",
            }
        },
    )

    assert item["workflow_preview_assets"] == {
        "selfhost/image_z_image_turbo.json": {
            "asset_path": "resources/prompt_prefix_previews/custom/manual-test.webp",
            "reference_prompt": "gallery cover prompt",
            "generated_at": "2026-04-22T12:34:56Z",
            "status": "ready",
        }
    }


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
    monkeypatch.setattr("web.utils.prompt_prefix_ui.PROJECT_ROOT", tmp_path)

    asset_path = persist_uploaded_prompt_prefix_preview(
        _FakeUpload("story-cover.svg", b"<svg/>"),
        "manual-test",
    )

    assert asset_path == "resources/prompt_prefix_previews/custom/manual-test.svg"
    assert (tmp_path / asset_path).read_bytes() == b"<svg/>"


def test_persist_uploaded_prompt_prefix_preview_falls_back_to_png_suffix(monkeypatch, tmp_path):
    monkeypatch.setattr("web.utils.prompt_prefix_ui.PROJECT_ROOT", tmp_path)

    asset_path = persist_uploaded_prompt_prefix_preview(
        _FakeUpload("story-cover.bin", b"png-bytes"),
        "manual-test",
    )

    assert asset_path.endswith(".png")


def test_persist_uploaded_prompt_prefix_preview_removes_replaced_custom_asset(monkeypatch, tmp_path):
    monkeypatch.setattr("web.utils.prompt_prefix_ui.PROJECT_ROOT", tmp_path)
    old_asset_path = tmp_path / "resources" / "prompt_prefix_previews" / "custom" / "manual-test.png"
    old_asset_path.parent.mkdir(parents=True, exist_ok=True)
    old_asset_path.write_bytes(b"old-bytes")

    asset_path = persist_uploaded_prompt_prefix_preview(
        _FakeUpload("story-cover.svg", b"<svg/>"),
        "manual-test",
        previous_preview_asset_path="resources/prompt_prefix_previews/custom/manual-test.png",
    )

    assert asset_path == "resources/prompt_prefix_previews/custom/manual-test.svg"
    assert not old_asset_path.exists()
    assert (tmp_path / asset_path).read_bytes() == b"<svg/>"


def test_delete_prompt_prefix_preview_asset_only_removes_custom_assets(monkeypatch, tmp_path):
    monkeypatch.setattr("web.utils.prompt_prefix_ui.PROJECT_ROOT", tmp_path)
    custom_asset_path = tmp_path / "resources" / "prompt_prefix_previews" / "custom" / "manual-test.svg"
    builtin_asset_path = tmp_path / "resources" / "prompt_prefix_previews" / "builtin" / "warm-storybook.svg"
    custom_asset_path.parent.mkdir(parents=True, exist_ok=True)
    builtin_asset_path.parent.mkdir(parents=True, exist_ok=True)
    custom_asset_path.write_bytes(b"custom")
    builtin_asset_path.write_bytes(b"builtin")

    assert delete_prompt_prefix_preview_asset("resources/prompt_prefix_previews/custom/manual-test.svg") is True
    assert not custom_asset_path.exists()
    assert delete_prompt_prefix_preview_asset("resources/prompt_prefix_previews/builtin/warm-storybook.svg") is False
    assert builtin_asset_path.exists()


def test_persist_generated_prompt_prefix_preview_saves_relative_asset(monkeypatch, tmp_path):
    monkeypatch.setattr("web.utils.prompt_prefix_ui.PROJECT_ROOT", tmp_path)

    def fake_load_preview_media(path, media_type):
        assert path == "http://127.0.0.1:8000/view?filename=story-cover.webp&type=output"
        assert media_type == "image"
        return PreviewMediaData(data=b"preview-bytes")

    monkeypatch.setattr("web.utils.prompt_prefix_ui.load_preview_media", fake_load_preview_media)

    asset_path = persist_generated_prompt_prefix_preview(
        "http://127.0.0.1:8000/view?filename=story-cover.webp&type=output",
        "llm-test",
    )

    assert asset_path == "resources/prompt_prefix_previews/custom/llm-test.webp"
    assert (tmp_path / asset_path).read_bytes() == b"preview-bytes"


def test_persist_generated_prompt_prefix_workflow_preview_includes_workflow_slug(monkeypatch, tmp_path):
    monkeypatch.setattr("web.utils.prompt_prefix_ui.PROJECT_ROOT", tmp_path)

    def fake_load_preview_media(path, media_type):
        assert path == "http://127.0.0.1:8000/view?filename=story-cover.webp&type=output"
        assert media_type == "image"
        return PreviewMediaData(data=b"preview-bytes")

    monkeypatch.setattr("web.utils.prompt_prefix_ui.load_preview_media", fake_load_preview_media)

    asset_path = persist_generated_prompt_prefix_workflow_preview(
        "http://127.0.0.1:8000/view?filename=story-cover.webp&type=output",
        "llm-test",
        "selfhost/image_z_image_turbo.json",
    )

    assert asset_path == (
        "resources/prompt_prefix_previews/custom/"
        "llm-test__selfhost_image_z_image_turbo_json.webp"
    )
    assert (tmp_path / asset_path).read_bytes() == b"preview-bytes"


def test_clone_prompt_prefix_preview_asset_copies_custom_asset(monkeypatch, tmp_path):
    monkeypatch.setattr("web.utils.prompt_prefix_ui.PROJECT_ROOT", tmp_path)
    source_asset = tmp_path / "resources" / "prompt_prefix_previews" / "custom" / "manual-source.webp"
    source_asset.parent.mkdir(parents=True, exist_ok=True)
    source_asset.write_bytes(b"cover-bytes")

    cloned_asset_path = clone_prompt_prefix_preview_asset(
        "resources/prompt_prefix_previews/custom/manual-source.webp",
        "manual-copy",
    )

    assert cloned_asset_path == "resources/prompt_prefix_previews/custom/manual-copy.webp"
    assert (tmp_path / cloned_asset_path).read_bytes() == b"cover-bytes"
    assert source_asset.read_bytes() == b"cover-bytes"


def test_get_prompt_prefix_form_item_id_reuses_manual_draft_id():
    session_state = {}

    first_id = get_prompt_prefix_form_item_id(session_state)
    second_id = get_prompt_prefix_form_item_id(session_state)

    assert first_id == second_id
    assert first_id.startswith("manual-")


def test_delete_image_prompt_prefix_item_cleans_up_custom_preview_asset(monkeypatch):
    fake_library = {
        "active_prefix_id": "manual-test",
        "items": [
            {
                "id": "manual-test",
                "preview_asset_path": "resources/prompt_prefix_previews/custom/manual-test.png",
                "workflow_preview_assets": {
                    "selfhost/image_z_image_turbo.json": {
                        "asset_path": (
                            "resources/prompt_prefix_previews/custom/manual-test__"
                            "selfhost_image_z_image_turbo_json.webp"
                        )
                    }
                },
            }
        ],
    }

    class _FakeConfigManager:
        def __init__(self):
            self.saved_library = fake_library
            self.save_calls = 0

        def get_image_prompt_prefix_library(self):
            return {
                "active_prefix_id": self.saved_library["active_prefix_id"],
                "items": [dict(item) for item in self.saved_library["items"]],
            }

        def set_image_prompt_prefix_library(self, library):
            self.saved_library = library

        def save(self):
            self.save_calls += 1

    fake_manager = _FakeConfigManager()
    deleted_assets = []

    monkeypatch.setattr(style_config, "config_manager", fake_manager)
    monkeypatch.setattr(
        style_config,
        "delete_prompt_prefix_preview_asset",
        lambda asset_path: deleted_assets.append(asset_path) or True,
    )

    style_config._delete_image_prompt_prefix_item("manual-test")

    assert deleted_assets == [
        "resources/prompt_prefix_previews/custom/manual-test.png",
        "resources/prompt_prefix_previews/custom/manual-test__selfhost_image_z_image_turbo_json.webp",
    ]
    assert fake_manager.saved_library["items"] == []
    assert fake_manager.saved_library["active_prefix_id"] is None
    assert fake_manager.save_calls == 1


def test_prepare_prompt_prefix_item_for_library_save_persists_generated_workflow_preview(monkeypatch):
    candidate = create_prompt_prefix_item(
        item_id="llm-test",
        name="AI Candidate",
        content="soft watercolor illustration",
        style_category_id="watercolor",
        scene_category_id="childrens_story",
        source="llm",
    )
    persisted_calls = []

    def fake_persist_generated_prompt_prefix_workflow_preview(
        preview_media_path,
        item_id,
        workflow_key,
        previous_preview_asset_path=None,
    ):
        persisted_calls.append((preview_media_path, item_id, workflow_key, previous_preview_asset_path))
        return "resources/prompt_prefix_previews/custom/llm-test__workflow.webp"

    monkeypatch.setattr(
        style_config,
        "persist_generated_prompt_prefix_workflow_preview",
        fake_persist_generated_prompt_prefix_workflow_preview,
    )

    prepared_item = style_config._prepare_prompt_prefix_item_for_library_save(
        candidate,
        workflow_key="selfhost/image_z_image_turbo.json",
        preview_media_path="http://127.0.0.1:8000/view?filename=llm-test.png",
        reference_prompt="storybook gallery cover",
    )

    assert prepared_item["preview_asset_path"] is None
    preview_record = prepared_item["workflow_preview_assets"]["selfhost/image_z_image_turbo.json"]
    assert preview_record["asset_path"] == "resources/prompt_prefix_previews/custom/llm-test__workflow.webp"
    assert preview_record["reference_prompt"] == "storybook gallery cover"
    assert preview_record["status"] == "ready"
    assert preview_record["generated_at"]
    assert persisted_calls == [
        (
            "http://127.0.0.1:8000/view?filename=llm-test.png",
            "llm-test",
            "selfhost/image_z_image_turbo.json",
            None,
        )
    ]


def test_resolve_prompt_prefix_gallery_cover_prefers_current_workflow_then_stale_then_reference(monkeypatch, tmp_path):
    monkeypatch.setattr(prompt_prefix_library, "PROJECT_ROOT", tmp_path)

    reference_asset = tmp_path / "resources" / "prompt_prefix_previews" / "builtin" / "warm_storybook.svg"
    stale_asset = tmp_path / "resources" / "prompt_prefix_previews" / "custom" / "item__old.webp"
    current_asset = tmp_path / "resources" / "prompt_prefix_previews" / "custom" / "item__current.webp"
    current_asset.parent.mkdir(parents=True, exist_ok=True)
    reference_asset.parent.mkdir(parents=True, exist_ok=True)
    reference_asset.write_text("<svg/>", encoding="utf-8")
    stale_asset.write_bytes(b"old")
    current_asset.write_bytes(b"current")
    os.utime(stale_asset, (1, 1))
    os.utime(current_asset, (2, 2))

    item = {
        "preview_asset_path": "resources/prompt_prefix_previews/builtin/warm_storybook.svg",
        "workflow_preview_assets": {
            "selfhost/old.json": {
                "asset_path": "resources/prompt_prefix_previews/custom/item__old.webp",
            },
            "selfhost/current.json": {
                "asset_path": "resources/prompt_prefix_previews/custom/item__current.webp",
            },
        },
    }

    current = prompt_prefix_library.resolve_prompt_prefix_gallery_cover(item, "selfhost/current.json")
    stale = prompt_prefix_library.resolve_prompt_prefix_gallery_cover(item, "selfhost/missing.json")
    empty = prompt_prefix_library.resolve_prompt_prefix_gallery_cover(
        {"preview_asset_path": "resources/prompt_prefix_previews/builtin/warm_storybook.svg"},
        "selfhost/missing.json",
    )

    assert current["asset_path"] == "resources/prompt_prefix_previews/custom/item__current.webp"
    assert current["is_stale"] is False
    assert current["source"] == "workflow"

    assert stale["asset_path"] == "resources/prompt_prefix_previews/custom/item__current.webp"
    assert stale["is_stale"] is True
    assert stale["source"] == "workflow"

    assert empty["asset_path"] == "resources/prompt_prefix_previews/builtin/warm_storybook.svg"
    assert empty["is_stale"] is False
    assert empty["source"] == "reference"


def test_resolve_prompt_prefix_gallery_cover_reads_metadata_records(monkeypatch, tmp_path):
    monkeypatch.setattr(prompt_prefix_library, "PROJECT_ROOT", tmp_path)

    current_asset = tmp_path / "resources" / "prompt_prefix_previews" / "custom" / "item__current.webp"
    current_asset.parent.mkdir(parents=True, exist_ok=True)
    current_asset.write_bytes(b"current")

    item = {
        "workflow_preview_assets": {
            "selfhost/current.json": {
                "asset_path": "resources/prompt_prefix_previews/custom/item__current.webp",
                "reference_prompt": "storybook gallery cover",
                "generated_at": "2026-04-22T12:34:56Z",
                "status": "ready",
            }
        },
    }

    current = prompt_prefix_library.resolve_prompt_prefix_gallery_cover(item, "selfhost/current.json")

    assert current["asset_path"] == "resources/prompt_prefix_previews/custom/item__current.webp"
    assert current["reference_prompt"] == "storybook gallery cover"
    assert current["generated_at"] == "2026-04-22T12:34:56Z"
    assert current["status"] == "ready"


def test_format_prompt_prefix_generated_at_uses_compact_timestamp():
    assert style_config._format_prompt_prefix_generated_at("2026-04-22T12:34:56Z") == "04-22 12:34"
    assert style_config._format_prompt_prefix_generated_at("  ") is None
    assert style_config._format_prompt_prefix_generated_at("not-an-iso-string") == "not-an-iso-string"


def test_resolve_prompt_prefix_workflow_display_label_prefers_display_name_map():
    workflow_display_map = {
        "selfhost/image_z_image_turbo.json": "image_z_image_turbo.json - Selfhost",
    }

    assert (
        style_config._resolve_prompt_prefix_workflow_display_label(
            "selfhost/image_z_image_turbo.json",
            workflow_display_map,
        )
        == "image_z_image_turbo.json - Selfhost"
    )
    assert (
        style_config._resolve_prompt_prefix_workflow_display_label(
            "selfhost/missing.json",
            workflow_display_map,
        )
        == "selfhost/missing.json"
    )
    assert style_config._resolve_prompt_prefix_workflow_display_label(None, workflow_display_map) is None


def test_get_prompt_prefix_source_label_maps_known_sources():
    translations = {
        "style.prefix_library.source_builtin": "Built-in",
        "style.prefix_library.source_manual": "Manual",
        "style.prefix_library.source_llm": "AI",
    }

    original_tr = style_config.tr
    style_config.tr = lambda key, **_: translations.get(key, key)
    try:
        assert style_config._get_prompt_prefix_source_label("builtin") == "Built-in"
        assert style_config._get_prompt_prefix_source_label("manual") == "Manual"
        assert style_config._get_prompt_prefix_source_label("llm") == "AI"
        assert style_config._get_prompt_prefix_source_label("custom") == "custom"
    finally:
        style_config.tr = original_tr


def test_build_prompt_prefix_live_preview_map_ignores_compare_preview_results(monkeypatch):
    fake_streamlit = type(
        "FakeStreamlit",
        (),
        {
            "session_state": {
                "prompt_prefix_preview_results": [
                    {"id": "library-a", "preview_media_path": "compare-preview.png"}
                ],
                "prompt_prefix_generated_preview_results": [
                    {"id": "generated-a", "preview_media_path": "candidate-preview.png"}
                ],
            }
        },
    )()

    monkeypatch.setattr(style_config, "st", fake_streamlit)

    assert style_config._build_prompt_prefix_live_preview_map() == {
        "generated-a": "candidate-preview.png"
    }


def test_remove_generated_candidate_from_session_cleans_saved_candidate(monkeypatch):
    fake_streamlit = type(
        "FakeStreamlit",
        (),
        {
            "session_state": {
                "prompt_prefix_generated_candidates": [
                    {"id": "llm-test"},
                    {"id": "llm-keep"},
                ],
                "prompt_prefix_generated_preview_results": [
                    {"id": "llm-test", "preview_media_path": "preview-a.png"},
                    {"id": "llm-keep", "preview_media_path": "preview-b.png"},
                ],
                "prompt_prefix_preview_ids": ["llm-test", "library-a"],
            }
        },
    )()

    monkeypatch.setattr(style_config, "st", fake_streamlit)

    style_config._remove_generated_candidate_from_session("llm-test")

    assert fake_streamlit.session_state["prompt_prefix_generated_candidates"] == [
        {"id": "llm-keep"}
    ]
    assert fake_streamlit.session_state["prompt_prefix_generated_preview_results"] == [
        {"id": "llm-keep", "preview_media_path": "preview-b.png"}
    ]
    assert fake_streamlit.session_state["prompt_prefix_preview_ids"] == ["llm-test", "library-a"]


def test_style_config_source_references_prompt_prefix_library_ui():
    project_root = Path(__file__).resolve().parent.parent
    source = (project_root / "web" / "components" / "style_config.py").read_text(encoding="utf-8")
    standard_source = (project_root / "web" / "pipelines" / "standard.py").read_text(encoding="utf-8")
    current_prefix_section = source.split("def _render_image_prompt_prefix_library(", 1)[1]
    current_prefix_section = current_prefix_section.split("\ndef render_style_config(", 1)[0]
    gallery_section = current_prefix_section.split("with gallery_col:", 1)[1]
    gallery_section = gallery_section.split("\n    with panel_col:", 1)[0]

    assert "prompt_prefix_library" in source
    assert "toggle_prompt_prefix_preview_selection" in source
    assert "build_prompt_prefix_generation_prompt" in source
    assert "resolve_prompt_prefix_gallery_cover" in source
    assert "get_prompt_prefix_form_item_id" in source
    assert "persist_generated_prompt_prefix_workflow_preview" in source
    assert "clone_prompt_prefix_preview_asset" in source
    assert "delete_prompt_prefix_preview_asset" in source
    assert "_remove_generated_candidate_from_session" in source
    assert "prompt_prefix_panel_mode" in source
    assert "style.prefix_library.toolbar_add" in source
    assert "style.prefix_library.compare_count" in source
    assert "style.prefix_library.thumbnail_prompt" in source
    assert "style.prefix_library.filter_panel" in source
    assert "style.prefix_library.generate_thumbnails" in source
    assert "style.prefix_library.thumbnail_workflow_label" in source
    assert "style.prefix_library.thumbnail_generated_at_label" in source
    assert "style.prefix_library.thumbnail_reference_prompt_label" in source
    assert "style.prefix_library.source_builtin" in source
    assert "style.prefix_library.source_manual" in source
    assert "style.prefix_library.source_llm" in source
    assert "_format_prompt_prefix_generated_at" in source
    assert "_resolve_prompt_prefix_workflow_display_label" in source
    assert "_get_prompt_prefix_source_label" in source
    assert "workflow_display_map=workflow_display_map" in source
    assert 'st.container(key="prompt_prefix_library_root")' in current_prefix_section
    filter_panel_section = current_prefix_section.split('tr("style.prefix_library.filter_panel")', 1)[1]
    filter_panel_section = filter_panel_section.split("filtered_items = ", 1)[0]
    assert "expanded=False" in filter_panel_section
    assert ".st-key-prompt_prefix_library_root div.stButton > button p" in current_prefix_section
    assert "word-break: keep-all !important" in current_prefix_section
    assert "padding-inline: 0.45rem" in current_prefix_section
    assert "style.prefix_library.compare_chip_short" in source
    assert "num_cols = 4" in current_prefix_section
    assert "num_cols = 5" not in current_prefix_section
    assert " 路 " not in current_prefix_section
    assert "generated_at:" not in current_prefix_section
    assert "reference_prompt:" not in current_prefix_section
    assert "num_cols = 1" not in source
    assert "cover_asset" not in gallery_section
    assert "compare_prefix_card_new_" not in gallery_section
    assert 'continue\n' not in gallery_section
    assert "st.columns([2.25, 1.05]" not in source
    assert "st.columns([1, 1, 1.2, 0.8, 0.9]" not in source
    assert "st.columns([1, 1, 1])" in standard_source


def test_collapsible_section_helper_does_not_require_key_parameter():
    assert "key" not in inspect.signature(style_config.render_middle_column_collapsible_section).parameters


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
        assert "style.prefix_library.thumbnail_prompt" in translations
        assert "style.prefix_library.filter_panel" in translations
        assert "style.prefix_library.generate_thumbnails" in translations
        assert "style.prefix_library.compare_chip_short" in translations
        assert "style.prefix_library.thumbnail_workflow_label" in translations
        assert "style.prefix_library.thumbnail_generated_at_label" in translations
        assert "style.prefix_library.thumbnail_reference_prompt_label" in translations
        assert "style.prefix_library.source_builtin" in translations
        assert "style.prefix_library.source_manual" in translations
        assert "style.prefix_library.source_llm" in translations


def test_runtime_asset_dirs_are_gitignored():
    project_root = Path(__file__).resolve().parent.parent
    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")

    assert ".superpowers/" in gitignore
    assert "resources/prompt_prefix_previews/custom/" in gitignore


def test_generate_prompt_prefix_preview_results_uses_shared_styled_batch(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        return StyledImagePromptBatch(
            prompts=["preview final prompt"],
            negative_prompt="avoid realism",
            resolved_style=None,
        )

    class _FakePixelleVideo:
        llm = object()
        config = {
            "comfyui": {
                "image": {
                    "prompt_prefix": "",
                    "prompt_prefix_library": {"active_prefix_id": None, "items": []},
                }
            }
        }

        async def media(self, **kwargs):
            captured["media_kwargs"] = kwargs
            return type("MediaResult", (), {"url": "preview.png"})()

    monkeypatch.setattr(style_config, "generate_styled_image_prompt_batch", fake_generate_styled_image_prompt_batch)
    monkeypatch.setattr(style_config, "run_async", lambda coro: asyncio.run(coro))

    preview_results = style_config._generate_prompt_prefix_preview_results(
        pixelle_video=_FakePixelleVideo(),
        workflow_key="selfhost/image_z_image_turbo.json",
        media_width=1024,
        media_height=1024,
        test_prompt="a dog",
        items=[{"id": "prefix-1", "name": "Bird World", "content": "angry birds world"}],
    )

    assert preview_results[0]["final_prompt"] == "preview final prompt"
    assert captured["media_kwargs"]["negative_prompt"] == "avoid realism"


def test_generate_single_video_style_preview_uses_shared_styled_batch(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["media_type"] = kwargs["media_type"]
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        return StyledImagePromptBatch(
            prompts=["video preview final prompt"],
            negative_prompt="avoid blur",
            resolved_style=None,
        )

    class _FakePixelleVideo:
        llm = object()
        config = {
            "comfyui": {
                "video": {
                    "prompt_prefix": "legacy video",
                    "prompt_prefix_library": {"active_prefix_id": None, "items": []},
                }
            }
        }

        async def media(self, **kwargs):
            captured["media_kwargs"] = kwargs
            return type("MediaResult", (), {"url": "preview.mp4"})()

    monkeypatch.setattr(style_config, "generate_styled_image_prompt_batch", fake_generate_styled_image_prompt_batch)
    monkeypatch.setattr(style_config, "run_async", lambda coro: asyncio.run(coro))

    preview = style_config._generate_single_style_preview_result(
        pixelle_video=_FakePixelleVideo(),
        workflow_key="runninghub/video_wan2.1_fusionx.json",
        media_width=1024,
        media_height=1024,
        test_prompt="a dog running in the park",
        prompt_prefix="angry birds world",
        media_type="video",
    )

    assert preview["final_prompt"] == "video preview final prompt"
    assert captured["media_type"] == "video"
    assert captured["media_kwargs"]["negative_prompt"] == "avoid blur"
