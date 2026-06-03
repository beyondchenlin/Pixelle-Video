import pytest

from pixelle_video.models.render_package import CaptionCue, TextCue, TextTrack
from pixelle_video.models.text_layout import TextLayoutPlan
from pixelle_video.models.text_render_package import (
    CaptionRenderingSettings,
    TextRenderPackage,
)
from pixelle_video.models.text_style import TextStyleProfile


def test_caption_settings_separate_caption_overlay_and_image_text():
    settings = CaptionRenderingSettings(
        enabled=True,
        source="narration_timing",
        style_profile="caption-default",
        punctuation_mode="strip_all",
        renderer_targets=("hyperframes", "ass"),
    )

    assert settings.enabled is True
    assert settings.style_profile == "caption-default"
    assert settings.renderer_targets == ("hyperframes", "ass")


def test_caption_settings_default_to_enabled():
    settings = CaptionRenderingSettings()

    assert settings.enabled is True


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"source": ""}, "source"),
        ({"style_profile": ""}, "style_profile"),
        ({"punctuation_mode": "drop_everything"}, "punctuation"),
        ({"renderer_targets": ("native_prompt",)}, "renderer"),
    ],
)
def test_caption_settings_rejects_invalid_contract_values(kwargs, message):
    with pytest.raises(ValueError, match=message):
        CaptionRenderingSettings(**kwargs)


def test_caption_settings_from_dict_coerces_string_enabled_false():
    settings = CaptionRenderingSettings.from_dict({"enabled": "false"})

    assert settings.enabled is False


def test_caption_settings_from_dict_coerces_scalar_renderer_target():
    settings = CaptionRenderingSettings.from_dict({"renderer_targets": "ass"})

    assert settings.renderer_targets == ("ass",)


def test_caption_settings_constructor_coerces_json_like_values():
    settings = CaptionRenderingSettings(enabled="false", renderer_targets="ass")

    assert settings.enabled is False
    assert settings.renderer_targets == ("ass",)


def test_text_layout_plan_round_trips_with_immutable_diagnostics():
    plan = TextLayoutPlan(
        safe_areas=({"id": "caption-safe", "slot": "bottom"},),
        wrapped_lines=({"cue_id": "caption-1", "lines": ["First", "Second"]},),
        collisions=({"cue_id": "overlay-1", "with": "caption-safe"},),
        diagnostics={"planner": {"status": "skipped"}},
    )

    restored = TextLayoutPlan.from_dict(plan.to_dict())

    assert restored.version == "text_layout_plan.v1"
    assert restored.safe_areas[0]["id"] == "caption-safe"
    assert restored.wrapped_lines[0]["lines"] == ("First", "Second")
    assert restored.to_dict()["wrapped_lines"][0]["lines"] == ["First", "Second"]
    with pytest.raises(TypeError):
        restored.diagnostics["planner"] = "changed"


def test_text_render_package_round_trips_with_version():
    package = TextRenderPackage(
        version="text_render_package.v1",
        task_id="task-1",
        caption_settings=CaptionRenderingSettings(),
        text_style_profiles=(
            TextStyleProfile(id="caption-default", name="Caption Default"),
        ),
        caption_cues=(
            CaptionCue(
                id="caption-1",
                text="Sentence 1.",
                start=0.0,
                end=1.5,
                frame_indices=[0],
                style_profile="caption-default",
            ),
        ),
        text_tracks=(
            TextTrack(
                id="track-overlay",
                kind="overlay",
                name="Overlay",
                renderer_targets=("hyperframes",),
                style_profile="overlay-default",
            ),
        ),
        text_cues=(
            TextCue(
                id="cue-1",
                track_id="track-overlay",
                text="Key point",
                start=0.2,
                end=1.4,
                role="keyword",
                slot="center",
                source={"kind": "text_overlay_plan"},
            ),
        ),
        layout_plan=TextLayoutPlan(safe_areas=({"id": "caption-safe"},)),
        diagnostics={"disabled_reasons": []},
    )

    restored = TextRenderPackage.from_dict(package.to_dict())

    assert restored.version == "text_render_package.v1"
    assert restored.caption_settings.style_profile == "caption-default"
    assert restored.text_style_profiles[0].id == "caption-default"
    assert restored.caption_cues[0].text == "Sentence 1."
    assert restored.text_tracks[0].renderer_targets == ("hyperframes",)
    assert restored.text_cues[0].source["kind"] == "text_overlay_plan"
    assert restored.layout_plan.safe_areas[0]["id"] == "caption-safe"
    assert restored.to_dict()["diagnostics"] == {"disabled_reasons": []}


def test_text_render_package_direct_constructor_coerces_collection_dicts():
    package = TextRenderPackage(
        task_id="task-dicts",
        text_style_profiles=(
            {
                "id": "caption-default",
                "name": "Caption Default",
                "primary_color": "#ffff00",
            },
        ),
        caption_cues=(
            {
                "id": "caption-1",
                "text": "Caption",
                "start": 0.0,
                "end": 1.0,
                "frame_indices": [0],
                "style_profile": "caption-default",
            },
        ),
        text_tracks=(
            {
                "id": "track-overlay",
                "kind": "overlay",
                "name": "Overlay",
                "renderer_targets": ["hyperframes"],
                "style_profile": "caption-default",
            },
        ),
        text_cues=(
            {
                "id": "cue-1",
                "track_id": "track-overlay",
                "text": "Overlay",
                "start": 0.0,
                "end": 1.0,
                "role": "keyword",
                "source": {"kind": "test"},
            },
        ),
    )

    assert isinstance(package.text_style_profiles[0], TextStyleProfile)
    assert isinstance(package.caption_cues[0], CaptionCue)
    assert isinstance(package.text_tracks[0], TextTrack)
    assert isinstance(package.text_cues[0], TextCue)
    assert package.to_dict()["text_style_profiles"][0]["primary_color"] == "#FFFF00"
    assert package.to_dict()["text_cues"][0]["source"] == {"kind": "test"}


def test_text_render_package_from_legacy_payload_applies_defaults_and_diagnostic():
    restored = TextRenderPackage.from_dict(
        {
            "task_id": "legacy-task",
            "caption_cues": [
                {
                    "id": "caption-1",
                    "text": "Legacy caption",
                    "start": 0.0,
                    "end": 1.0,
                }
            ],
        }
    )

    assert restored.version == "text_render_package.v1"
    assert restored.caption_settings.style_profile == "caption-default"
    assert restored.text_style_profiles[0].id == "caption-default"
    assert restored.layout_plan.version == "text_layout_plan.v1"
    assert "compatibility" in restored.diagnostics
    assert restored.caption_cues[0].style_profile is None


def test_text_render_package_preserves_non_mapping_legacy_compatibility_diagnostic():
    restored = TextRenderPackage.from_dict(
        {
            "task_id": "legacy-task",
            "diagnostics": {"compatibility": "legacy-note"},
        }
    ).to_dict()

    assert restored["diagnostics"]["compatibility"]["legacy_value"] == "legacy-note"
    assert "caption_settings" in restored["diagnostics"]["compatibility"][
        "applied_defaults"
    ]


def test_text_render_package_requires_task_id():
    with pytest.raises(ValueError, match="task_id"):
        TextRenderPackage(task_id="")
