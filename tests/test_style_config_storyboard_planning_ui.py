import json
from pathlib import Path

import web.components.style_config as style_config
import web.pipelines.standard as standard_pipeline
from pixelle_video.config.storyboard_preset_library import (
    BUILTIN_SHOT_PRESETS,
    BUILTIN_WORLD_PRESETS,
)
from web.components.style_config import build_storyboard_control_payload


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.top_level_markdowns: list[tuple[str, dict]] = []
        self.expander_markdowns: list[tuple[str, dict]] = []
        self.expanders: list[tuple[str, bool]] = []
        self._in_expander = False

    def markdown(self, body, **kwargs):
        target = self.expander_markdowns if self._in_expander else self.top_level_markdowns
        target.append((body, kwargs))
        return None

    def expander(self, label, expanded=False):
        self.expanders.append((label, expanded))
        fake_st = self

        class _FakeExpander(_FakeContext):
            def __enter__(self):
                fake_st._in_expander = True
                return self

            def __exit__(self, exc_type, exc, tb):
                fake_st._in_expander = False
                return False

        return _FakeExpander()


def test_resolve_storyboard_toggle_default_prefers_session_state_then_preview_snapshot_then_default():
    assert (
        style_config.resolve_storyboard_toggle_default(
            {"storyboard_planning_enabled": False},
            storyboard_default_enabled=True,
            preview_snapshot={"frame_overrides": []},
        )
        is False
    )

    assert (
        style_config.resolve_storyboard_toggle_default(
            {},
            storyboard_default_enabled=True,
            preview_snapshot={"frame_overrides": []},
        )
        is True
    )

    assert (
        style_config.resolve_storyboard_toggle_default(
            {},
            storyboard_default_enabled=False,
            preview_snapshot=None,
        )
        is False
    )


def test_resolve_storyboard_preset_label_uses_translation_key_or_display_name_fallback(monkeypatch):
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: f"localized:{key}")

    assert (
        style_config.resolve_storyboard_preset_label(
            {"preset_id": "balanced_explainer", "display_name_key": "storyboard.preset.shot.balanced_explainer.name"}
        )
        == "localized:storyboard.preset.shot.balanced_explainer.name"
    )

    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    assert (
        style_config.resolve_storyboard_preset_label(
            {
                "preset_id": "fallback_only",
                "display_name_key": "storyboard.preset.shot.fallback_only.name",
                "display_name": "Fallback Name",
            }
        )
        == "Fallback Name"
    )

    assert (
        style_config.resolve_storyboard_preset_label(
            {"preset_id": "fallback_only", "display_name": "Fallback Name"}
        )
        == "Fallback Name"
    )


def test_standard_pipeline_ui_passes_storyboard_default_enabled_to_render_style_config(monkeypatch):
    captured = {}

    class _FakeColumn(_FakeContext):
        pass

    def fake_columns(_sizes):
        return [_FakeColumn(), _FakeColumn(), _FakeColumn()]

    def fake_render_style_config(pixelle_video, storyboard_default_enabled=False):
        captured["pixelle_video"] = pixelle_video
        captured["storyboard_default_enabled"] = storyboard_default_enabled
        return {"style": "ok"}

    monkeypatch.setattr(standard_pipeline.st, "columns", fake_columns)
    monkeypatch.setattr(standard_pipeline, "render_content_input", lambda: {"content": "ok"})
    monkeypatch.setattr(standard_pipeline, "render_bgm_section", lambda: {"bgm": "ok"})
    monkeypatch.setattr(standard_pipeline, "render_version_info", lambda: None)
    monkeypatch.setattr(standard_pipeline, "render_style_config", fake_render_style_config)
    monkeypatch.setattr(standard_pipeline, "render_output_preview", lambda pixelle_video, video_params: None)

    pipeline = standard_pipeline.StandardPipelineUI()
    pipeline.render(object())

    assert captured["storyboard_default_enabled"] is True


def test_build_storyboard_control_payload_includes_storyboard_fields():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="balanced_explainer",
        consistency_strength="strong",
        content_mode="concept_explainer",
        role_strategy="auto",
        role_locking_strength="strong",
        shot_strategy="strict",
        frame_overrides=[
            {
                "scene_id": "scene-1",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    )

    assert payload == {
        "world_preset_id": "neutral_knowledge_storyboard",
        "shot_preset_id": "balanced_explainer",
        "consistency_strength": "strong",
        "content_mode": "concept_explainer",
        "role_strategy": "auto",
        "role_locking_strength": "strong",
        "shot_strategy": "strict",
        "frame_overrides": [
            {
                "scene_id": "scene-1",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    }


def test_render_storyboard_planning_guide_renders_default_on_copy_and_expander(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    style_config.render_storyboard_planning_guide()

    assert ("storyboard.guide.title", False) in fake_st.expanders

    top_level_html = "\n".join(body for body, _kwargs in fake_st.top_level_markdowns)
    expander_html = "\n".join(body for body, _kwargs in fake_st.expander_markdowns)

    assert "storyboard.guide.default_on_title" in top_level_html
    assert "storyboard.guide.default_on_body" in top_level_html
    assert "storyboard.guide.when_to_turn_off.title" in top_level_html
    assert "storyboard.guide.when_to_turn_off.body" in top_level_html
    assert "storyboard.guide.quick_title" not in top_level_html
    assert "storyboard.guide.quick_body" not in top_level_html

    assert "storyboard.guide.combo.explainer.title" in expander_html
    assert "storyboard.guide.combo.theme_mapping.title" in expander_html
    assert "storyboard.guide.field.world_preset" in expander_html
    assert "storyboard.guide.override_title" in expander_html
    assert "storyboard.guide.default_on_title" not in expander_html
    assert "storyboard.guide.when_to_turn_off.title" not in expander_html
    assert any(kwargs.get("unsafe_allow_html") for _body, kwargs in fake_st.top_level_markdowns)
    assert any(kwargs.get("unsafe_allow_html") for _body, kwargs in fake_st.expander_markdowns)


def test_storyboard_planning_guide_translation_keys_exist_in_supported_locales():
    locale_dir = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"
    built_in_preset_keys = [
        *(key for preset in BUILTIN_WORLD_PRESETS for key in (preset.display_name_key, preset.description_key)),
        *(key for preset in BUILTIN_SHOT_PRESETS for key in (preset.display_name_key, preset.description_key)),
    ]
    required_keys = [
        "storyboard.guide.title",
        "storyboard.guide.default_on_title",
        "storyboard.guide.default_on_body",
        "storyboard.guide.when_to_turn_off.title",
        "storyboard.guide.when_to_turn_off.body",
        "storyboard.guide.recommended_title",
        "storyboard.guide.combo.explainer.title",
        "storyboard.guide.combo.explainer.body",
        "storyboard.guide.combo.theme_mapping.title",
        "storyboard.guide.combo.theme_mapping.body",
        "storyboard.guide.combo.iteration.title",
        "storyboard.guide.combo.iteration.body",
        "storyboard.guide.fields_title",
        "storyboard.guide.field.world_preset",
        "storyboard.guide.field.shot_preset",
        "storyboard.guide.field.consistency_strength",
        "storyboard.guide.field.content_mode",
        "storyboard.guide.field.role_strategy",
        "storyboard.guide.field.role_locking_strength",
        "storyboard.guide.field.shot_strategy",
        "storyboard.guide.override_title",
        "storyboard.guide.override_body",
    ]
    required_keys.extend(built_in_preset_keys)

    for locale_name in ("zh_CN.json", "en_US.json"):
        translations = json.loads((locale_dir / locale_name).read_text(encoding="utf-8"))["t"]
        missing_keys = [key for key in required_keys if key not in translations]
        assert missing_keys == []
