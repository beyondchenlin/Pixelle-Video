import json
from pathlib import Path

import web.components.style_config as style_config
from web.components.style_config import build_storyboard_control_payload


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.markdowns: list[tuple[str, dict]] = []
        self.expanders: list[tuple[str, bool]] = []

    def markdown(self, body, **kwargs):
        self.markdowns.append((body, kwargs))
        return None

    def expander(self, label, expanded=False):
        self.expanders.append((label, expanded))
        return _FakeContext()


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


def test_render_storyboard_planning_guide_renders_quick_read_and_expander(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    style_config.render_storyboard_planning_guide()

    assert ("storyboard.guide.title", False) in fake_st.expanders

    rendered_html = "\n".join(body for body, _kwargs in fake_st.markdowns)
    assert "storyboard.guide.quick_title" in rendered_html
    assert "storyboard.guide.quick_body" in rendered_html
    assert "storyboard.guide.combo.explainer.title" in rendered_html
    assert "storyboard.guide.field.world_preset" in rendered_html
    assert "storyboard.guide.override_title" in rendered_html
    assert any(kwargs.get("unsafe_allow_html") for _body, kwargs in fake_st.markdowns)


def test_storyboard_planning_guide_translation_keys_exist_in_supported_locales():
    locale_dir = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"
    required_keys = [
        "storyboard.guide.title",
        "storyboard.guide.quick_title",
        "storyboard.guide.quick_body",
        "storyboard.guide.when_to_enable.title",
        "storyboard.guide.when_to_enable.body",
        "storyboard.guide.when_to_skip.title",
        "storyboard.guide.when_to_skip.body",
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

    for locale_name in ("zh_CN.json", "en_US.json"):
        translations = json.loads((locale_dir / locale_name).read_text(encoding="utf-8"))["t"]
        missing_keys = [key for key in required_keys if key not in translations]
        assert missing_keys == []
