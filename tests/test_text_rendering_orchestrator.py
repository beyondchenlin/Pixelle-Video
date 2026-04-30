import pytest

from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    DEFAULT_TITLE_STYLE_ID,
)
from pixelle_video.services.text_rendering_orchestrator import (
    TextRenderingOrchestrator,
)


def test_orchestrator_builds_caption_style_when_overlay_disabled_and_preserves_image_policy():
    result = TextRenderingOrchestrator().build(
        text_rendering={
            "overlay": {"enabled": False},
            "caption_style": {"font_size": 72, "primary_color": "#ffff00"},
            "overlay_style": {"font_size": 90},
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "avoid visible writing",
            },
        },
        narrations=["first narration"],
        task_id="task-caption-only",
    )

    assert result.caption_style.id == DEFAULT_CAPTION_STYLE_ID
    assert result.caption_style.font_size == 72
    assert result.caption_style.primary_color == "#FFFF00"
    assert result.overlay_style.id == DEFAULT_OVERLAY_STYLE_ID
    assert result.overlay_style.font_size == 90
    assert result.caption_settings.enabled is True
    assert result.settings.overlay.enabled is False
    assert result.overlay_policy.enabled_targets == ()
    assert result.overlay_plan.candidates == ()
    assert result.image_text_policy.suppress_embedded_text is True
    assert result.image_text_policy.positive_prompt == "avoid visible writing"


def test_orchestrator_builds_overlay_plan_only_when_enabled_with_programmatic_targets():
    orchestrator = TextRenderingOrchestrator()

    native_only = orchestrator.build(
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "native_hint",
                "renderer_targets": ["native_prompt"],
            },
        },
        narrations=["Pixelle title"],
        task_id="task-native-only",
    )
    programmatic = orchestrator.build(
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["hyperframes"],
                "max_items_per_frame": 1,
            },
        },
        narrations=["Pixelle title"],
        task_id="task-programmatic",
    )

    assert native_only.overlay_policy.enabled_targets == ("native_prompt",)
    assert native_only.overlay_plan.candidates == ()
    assert programmatic.overlay_policy.enabled_targets == ("hyperframes",)
    assert len(programmatic.overlay_plan.candidates) == 1
    assert programmatic.overlay_plan.candidates[0].renderer_targets == ("hyperframes",)


def test_orchestrator_builds_title_style_from_template_preset_and_user_override():
    result = TextRenderingOrchestrator().build(
        text_rendering={
            "title_style": {
                "font_size": 92,
                "background_color": "#123456",
                "background_opacity": 0.5,
            }
        },
        template_id="image_landscape_minimal",
        canvas_width=1920,
        canvas_height=1080,
    )

    assert result.title_style.id == DEFAULT_TITLE_STYLE_ID
    assert result.title_style.position == "top_left"
    assert result.title_style.font_size == 92
    assert result.title_style.background_color == "#123456"
    assert result.title_style.background_opacity == 0.5
    assert result.title_style.scale_basis_width == 1920
    assert result.title_style.scale_basis_height == 1080
    assert [profile.id for profile in result.text_style_profiles] == [
        DEFAULT_CAPTION_STYLE_ID,
        DEFAULT_TITLE_STYLE_ID,
        DEFAULT_OVERLAY_STYLE_ID,
    ]


def test_orchestrator_uses_generic_title_default_for_templates_without_title_region():
    result = TextRenderingOrchestrator().build(
        text_rendering={},
        template_id="static_plain",
    )

    assert result.title_style.id == DEFAULT_TITLE_STYLE_ID
    assert result.title_style.name == "Title Default"


def test_orchestrator_package_has_task_id_styles_caption_settings_and_diagnostics():
    result = TextRenderingOrchestrator().build(
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["hyperframes"],
                "max_items_per_frame": 1,
            },
            "caption_style": {"stroke_width": 4},
            "overlay_style": {"position": "top"},
        },
        narrations=["important title"],
    )

    package = result.text_render_package
    payload = package.to_dict()

    assert package.task_id == "text-rendering-preview"
    assert package.caption_settings.style_profile == DEFAULT_CAPTION_STYLE_ID
    assert [profile.id for profile in package.text_style_profiles] == [
        DEFAULT_CAPTION_STYLE_ID,
        DEFAULT_TITLE_STYLE_ID,
        DEFAULT_OVERLAY_STYLE_ID,
    ]
    assert result.caption_settings.style_profile == DEFAULT_CAPTION_STYLE_ID
    assert result.diagnostics["task_id"] == "text-rendering-preview"
    assert "overlay_plan" in result.diagnostics
    assert payload["diagnostics"]["overlay_plan"]["candidate_count"] == 1
    assert "force_style" not in str(payload).lower()
    assert "fontsdir" not in str(payload).lower()
    assert "ffmpeg" not in str(payload).lower()
    assert "css" not in str(payload).lower()


def test_orchestrator_result_diagnostics_are_immutable_and_match_package():
    result = TextRenderingOrchestrator().build(
        text_rendering={"overlay": {"enabled": False}},
        narrations=["caption only"],
        task_id="task-diagnostics",
    )

    assert result.diagnostics is result.text_render_package.diagnostics
    assert result.diagnostics == result.text_render_package.diagnostics
    with pytest.raises(TypeError):
        result.diagnostics["task_id"] = "changed"
