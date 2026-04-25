import pytest

from pixelle_video.models.text_overlay import (
    TextOverlayCandidate,
    TextOverlayPlan,
    TextOverlaySettings,
    TextRenderingPolicy,
    build_text_rendering_settings,
    build_text_rendering_policy,
    freeze_json_value,
    thaw_json_value,
)


def test_text_rendering_policy_rejects_native_prompt_for_programmatic_only():
    with pytest.raises(ValueError, match="native_prompt"):
        TextRenderingPolicy(
            image_text_mode="programmatic_only",
            enabled_targets=("native_prompt",),
            density="medium",
            max_items_per_frame=2,
            allow_native_text_in_image=False,
            suppress_unplanned_embedded_text=True,
        )


def test_build_text_rendering_policy_defaults_when_overlay_missing():
    policy = build_text_rendering_policy(None)

    assert policy.image_text_mode == "programmatic_only"
    assert policy.enabled_targets == ()
    assert policy.allow_native_text_in_image is False
    assert policy.suppress_unplanned_embedded_text is True


def test_build_text_rendering_policy_rejects_legacy_no_text_keyword():
    with pytest.raises(TypeError):
        build_text_rendering_policy(None, forbid_embedded_text_in_image=False)


def test_build_text_rendering_policy_defaults_when_overlay_disabled():
    policy = build_text_rendering_policy(
        TextOverlaySettings(
            enabled=False,
            mode="hybrid",
            renderer_targets=("hyperframes", "native_prompt"),
            density="high",
            max_items_per_frame=3,
        )
    )

    assert policy.image_text_mode == "programmatic_only"
    assert policy.enabled_targets == ()
    assert policy.allow_native_text_in_image is False
    assert policy.suppress_unplanned_embedded_text is True


def test_build_text_rendering_policy_uses_nested_request_and_adds_native_target():
    policy = build_text_rendering_policy(
        {
            "enabled": True,
            "mode": "hybrid",
            "renderer_targets": ["hyperframes"],
            "density": "high",
            "max_items_per_frame": 3,
        }
    )

    assert policy.image_text_mode == "hybrid"
    assert policy.enabled_targets == ("hyperframes", "native_prompt")
    assert policy.density == "high"
    assert policy.max_items_per_frame == 3
    assert policy.allow_native_text_in_image is True


def test_build_text_rendering_policy_respects_disabled_nested_request():
    policy = build_text_rendering_policy(
        {
            "enabled": False,
            "mode": "hybrid",
            "renderer_targets": ["hyperframes", "native_prompt"],
            "density": "high",
            "max_items_per_frame": 3,
        }
    )

    assert policy.image_text_mode == "programmatic_only"
    assert policy.enabled_targets == ()
    assert policy.allow_native_text_in_image is False
    assert policy.suppress_unplanned_embedded_text is True


def test_build_text_rendering_policy_normalizes_mapping_string_enabled_false():
    policy = build_text_rendering_policy(
        {"enabled": "false", "mode": "hybrid", "renderer_targets": "ass"}
    )

    assert policy.image_text_mode == "programmatic_only"
    assert policy.enabled_targets == ()


def test_build_text_rendering_policy_normalizes_mapping_scalar_renderer_target():
    policy = build_text_rendering_policy(
        {"enabled": True, "mode": "programmatic_only", "renderer_targets": "ass"}
    )

    assert policy.image_text_mode == "programmatic_only"
    assert policy.enabled_targets == ("ass",)


def test_build_text_rendering_settings_defaults_do_not_suppress_image_text():
    settings = build_text_rendering_settings(None)

    assert settings.overlay.enabled is False
    assert settings.image_text.suppress_embedded_text is False
    assert settings.image_text.positive_prompt.startswith("no visible text")


def test_build_text_rendering_settings_accepts_custom_image_text_prompt():
    settings = build_text_rendering_settings(
        {
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "avoid all written marks",
                "negative_prompt": "letters, logo",
            }
        }
    )

    assert settings.image_text.suppress_embedded_text is True
    assert settings.image_text.positive_prompt == "avoid all written marks"
    assert settings.image_text.negative_prompt == "letters, logo"


def test_build_text_rendering_settings_normalizes_string_booleans():
    settings = build_text_rendering_settings(
        {
            "overlay": {"enabled": "false"},
            "image_text": {"suppress_embedded_text": "false"},
        }
    )

    assert settings.overlay.enabled is False
    assert settings.image_text.suppress_embedded_text is False


def test_build_text_rendering_settings_normalizes_scalar_renderer_target():
    settings = build_text_rendering_settings(
        {"overlay": {"renderer_targets": "ass"}}
    )

    assert settings.overlay.renderer_targets == ("ass",)


def test_build_text_rendering_policy_uses_overlay_only():
    settings = build_text_rendering_settings(
        {
            "overlay": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["ass"],
                "density": "high",
                "max_items_per_frame": 3,
            },
            "image_text": {"suppress_embedded_text": True},
        }
    )

    policy = build_text_rendering_policy(settings.overlay)

    assert policy.image_text_mode == "programmatic_only"
    assert policy.enabled_targets == ("ass",)
    assert policy.density == "high"
    assert policy.max_items_per_frame == 3


def test_freeze_json_value_blocks_nested_mutation_and_thaws_to_plain_json():
    frozen = freeze_json_value({"layout": {"x": 10}, "items": ["a", {"b": True}]})

    with pytest.raises(TypeError):
        frozen["layout"]["x"] = 20

    assert thaw_json_value(frozen) == {"layout": {"x": 10}, "items": ["a", {"b": True}]}


def test_text_overlay_plan_round_trips_candidates_with_source_span():
    candidate = TextOverlayCandidate(
        id="candidate-1",
        text="重点词",
        role="keyword",
        suggested_slot="center",
        renderer_targets=("hyperframes",),
        importance=0.9,
        confidence=0.8,
        source={"kind": "narration", "frame_index": 0, "span": [0, 3]},
    )
    plan = TextOverlayPlan(
        candidates=(candidate,),
        source_summary={"narration_count": 1},
    )

    restored = TextOverlayPlan.from_dict(plan.to_dict())

    assert restored.version == "text_overlay_plan.v1"
    assert restored.candidates[0].text == "重点词"
    assert restored.candidates[0].renderer_targets == ("hyperframes",)
    assert restored.candidates[0].source["span"] == (0, 3)
    assert restored.to_dict()["candidates"][0]["source"]["span"] == [0, 3]
