import json
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest
from pydantic import ValidationError

import api.schemas.video as video_schema_module
from api.routers.video import (
    build_video_generation_params,
    generate_video_async,
    generate_video_sync,
)
from api.schemas.video import (
    MediaResolutionPreset,
    VideoGenerateRequest,
    VideoResolutionPreset,
)
from api.schemas.video_internal import VideoGenerateInternalRequest
from pixelle_video.models.article_concretization import (
    CognitiveAnchorKind,
    DiagramAspectRatio,
    DiagramRenderStyle,
    ExplanationDiagramGrammar,
    SeriesVisualSignatureRole,
)
from pixelle_video.models.article_understanding import ArticleUnderstandingMode
from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
)
from pixelle_video.models.series_visual_signature_strategy import SeriesVisualSignatureStrategy
from pixelle_video.models.size_contract import (
    STANDARD_VIDEO_SIZE_PRESETS,
    VALID_MEDIA_RESOLUTION_PRESETS,
    VALID_VIDEO_RESOLUTION_PRESETS,
    GenerationSizeContract,
)
from pixelle_video.models.storyboard_limits import StoryboardGenerationLimits
from pixelle_video.models.video_generation_contract import (
    normalize_standard_video_generation_params,
    validate_standard_video_generation_params,
)
from pixelle_video.models.visual_planning_mode import VisibleTextPolicy, VisualPlanningMode
from pixelle_video.services.resource_resolver import ResolvedResource, StaticResourceResolver


def _layered_spec_payload(template_id="demo") -> dict:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id=template_id,
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(
            TemplateLayer(
                id="media",
                type="generated_media",
                name="Generated media",
                rect=RectSpec(x=64, y=320, width=952, height=952),
                z_index=10,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(
                    kind="generated_media",
                    ref="generated://primary",
                ),
                style={"object_fit": "contain"},
            ),
        ),
        metadata={},
    ).to_dict()


class _FakePixelleVideo:
    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.calls: list[dict] = []

    async def generate_video(self, **kwargs):
        self.calls.append(kwargs)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_bytes(b"video")
        return SimpleNamespace(
            video_path=str(self.output_path),
            duration=2.5,
        )


OMNIVOICE_TEST_VOICE = ResolvedResource(
    resource_id="bange",
    resolved_value="reference_audio/omnivoice/bange.wav",
    metadata={
        "tts_workflow": "selfhost/tts_omnivoice_longform_bf16.json",
        "ref_audio": "reference_audio/omnivoice/bange.wav",
        "ref_audio_text": "大家好，这是参考音频文本。",
    },
)


def _api_request_context(base_url: str = "http://testserver/"):
    return SimpleNamespace(
        base_url=base_url,
        app=SimpleNamespace(
            state=SimpleNamespace(
                resource_resolver=StaticResourceResolver(
                    voices={"bange": OMNIVOICE_TEST_VOICE}
                )
            )
        ),
    )


def _public_video_request(**kwargs) -> VideoGenerateRequest:
    return VideoGenerateRequest(voice_id="bange", **kwargs)


def test_api_video_preset_literals_match_size_contract():
    assert set(get_args(VideoResolutionPreset)) == set(VALID_VIDEO_RESOLUTION_PRESETS)


def test_api_media_preset_literals_match_size_contract():
    assert set(get_args(MediaResolutionPreset)) == set(VALID_MEDIA_RESOLUTION_PRESETS)


def test_v44_api_planning_fields_use_model_enum_fact_sources():
    assert video_schema_module.ArticleUnderstandingModeRequest is ArticleUnderstandingMode
    assert video_schema_module.VisualPlanningModeRequest is VisualPlanningMode
    assert video_schema_module.SeriesVisualSignatureStrategyRequest is SeriesVisualSignatureStrategy
    assert video_schema_module.CognitiveAnchorKindRequest is CognitiveAnchorKind
    assert video_schema_module.ExplanationDiagramGrammarRequest is ExplanationDiagramGrammar
    assert video_schema_module.SeriesVisualSignatureRoleRequest is SeriesVisualSignatureRole
    assert video_schema_module.DiagramRenderStyleRequest is DiagramRenderStyle
    assert video_schema_module.DiagramAspectRatioRequest is DiagramAspectRatio
    assert video_schema_module.VisibleTextPolicyRequest is VisibleTextPolicy
    assert VisibleTextPolicy.FREE_TEXT_ALLOWED.value == "free_text_allowed"
    assert (
        VideoGenerateRequest.model_fields["article_understanding_mode"].annotation
        is ArticleUnderstandingMode
    )
    assert (
        VideoGenerateRequest.model_fields["visual_planning_mode"].annotation
        is VisualPlanningMode
    )
    assert (
        VideoGenerateRequest.model_fields["series_visual_signature_strategy"].annotation
        is SeriesVisualSignatureStrategy
    )
    assert (
        VideoGenerateRequest.model_fields["cognitive_anchor_kind"].annotation
        is CognitiveAnchorKind
    )
    assert (
        VideoGenerateRequest.model_fields["explanation_diagram_grammar"].annotation
        is ExplanationDiagramGrammar
    )
    assert (
        VideoGenerateRequest.model_fields["series_visual_signature_role"].annotation
        is SeriesVisualSignatureRole
    )
    assert (
        VideoGenerateRequest.model_fields["diagram_render_style"].annotation
        is DiagramRenderStyle
    )
    assert (
        VideoGenerateRequest.model_fields["diagram_aspect_ratio"].annotation
        is DiagramAspectRatio
    )
    assert (
        VideoGenerateRequest.model_fields["diagram_visible_text_policy"].annotation
        is VisibleTextPolicy
    )


def test_video_generate_request_defaults_are_typed_and_serialize_without_warnings(recwarn):
    request = VideoGenerateRequest(text="demo")

    assert request.article_understanding_mode is ArticleUnderstandingMode.AUTO
    assert request.visual_planning_mode is VisualPlanningMode.AUTO
    assert request.series_visual_signature_strategy is SeriesVisualSignatureStrategy.AUTO
    assert request.cognitive_anchor_kind is CognitiveAnchorKind.AUTO
    assert request.explanation_diagram_grammar is ExplanationDiagramGrammar.AUTO
    assert request.series_visual_signature_role is SeriesVisualSignatureRole.NONE
    assert request.diagram_render_style is DiagramRenderStyle.AUTO
    assert request.diagram_aspect_ratio is DiagramAspectRatio.AUTO
    assert request.diagram_visible_text_policy is VisibleTextPolicy.NO_VISIBLE_TEXT

    request.model_dump(mode="python")

    assert not recwarn.list


def test_video_generate_request_rejects_removed_hyperframes_alias():
    with pytest.raises(ValidationError, match="hyperframes_compiled"):
        VideoGenerateRequest(
            text="demo",
            render_backend="hyperframes",
        )


def test_video_generate_request_accepts_text_rendering_policy():
    request = VideoGenerateRequest(
        text="hello",
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["hyperframes"],
                "density": "medium",
                "max_items_per_frame": 2,
            },
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "no letters in image",
                "negative_prompt": "letters, watermark",
            },
        },
    )

    assert request.text_rendering.overlay.enabled is True
    assert request.text_rendering.caption.enabled is True
    assert request.text_rendering.image_text.suppress_embedded_text is True
    assert request.text_rendering.image_text.positive_prompt == "no letters in image"


def test_build_video_generation_params_copies_template_display_controls():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            template_display={"show_title": True, "show_signature": True},
        ),
        request_id="req_template_display",
    )

    assert params["template_display"] == {
        "show_title": True,
        "show_signature": True,
    }


def test_video_generate_request_accepts_series_visual_signature_controls():
    request = VideoGenerateRequest(
        text="demo",
        series_visual_signature_enabled=True,
        series_visual_signature_asset_bible_id="bible_demo",
        series_visual_signature_profile_id="ip_main",
    )

    assert request.series_visual_signature_enabled is True
    assert request.series_visual_signature_asset_bible_id == "bible_demo"
    assert request.series_visual_signature_profile_id == "ip_main"
    assert request.series_visual_signature_llm_prompt_assembly_enabled is False


def test_visual_anchor_seed_is_validated_and_forwarded_only_when_enabled():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            series_visual_signature_enabled=True,
            series_visual_signature_asset_bible_id="bible_demo",
            series_visual_signature_profile_id="ip_main",
            media_seed=2026082201,
        ),
        request_id="req_visual_anchor_seed",
    )

    assert params["media_seed"] == 2026082201
    without_anchor = build_video_generation_params(
        VideoGenerateRequest(text="demo", media_seed=2026082201),
        request_id="req_without_visual_anchor",
    )
    assert "media_seed" not in without_anchor
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", media_seed=-1)


def test_video_generate_request_accepts_v44_planning_controls():
    request = VideoGenerateRequest(
        text="demo",
        article_understanding_mode="causal_mechanism",
        visual_planning_mode="process_walkthrough",
        series_visual_signature_strategy="observer_guide",
        strict_user_mode=True,
        force_v44_planning=True,
    )

    assert request.article_understanding_mode == "causal_mechanism"
    assert request.visual_planning_mode == "process_walkthrough"
    assert request.series_visual_signature_strategy == "observer_guide"
    assert request.strict_user_mode is True
    assert request.force_v44_planning is True


def test_video_generate_request_accepts_article_concretization_fields():
    request = VideoGenerateRequest(
        text="demo",
        article_concretization_enabled=True,
        cognitive_anchor_kind="causal_mechanism",
        explanation_diagram_grammar="process_flow",
        series_visual_signature_role="guide",
        diagram_render_style="editorial_diagram",
        diagram_aspect_ratio="landscape_16_9",
        diagram_visible_text_policy="free_text_allowed",
        diagram_approved_labels=["Cause", "Effect"],
        diagram_user_intent_hint="show the feedback loop",
    )

    assert request.article_concretization_enabled is True
    assert request.cognitive_anchor_kind is CognitiveAnchorKind.CAUSAL_MECHANISM
    assert request.explanation_diagram_grammar is ExplanationDiagramGrammar.PROCESS_FLOW
    assert request.series_visual_signature_role is SeriesVisualSignatureRole.GUIDE
    assert request.diagram_render_style is DiagramRenderStyle.EDITORIAL_DIAGRAM
    assert request.diagram_aspect_ratio is DiagramAspectRatio.LANDSCAPE_16_9
    assert request.diagram_visible_text_policy is VisibleTextPolicy.FREE_TEXT_ALLOWED
    assert request.diagram_approved_labels == ["Cause", "Effect"]
    assert request.diagram_user_intent_hint == "show the feedback loop"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("cognitive_anchor_kind", "unknown"),
        ("explanation_diagram_grammar", "unknown"),
        ("series_visual_signature_role", "unknown"),
        ("diagram_render_style", "unknown"),
        ("diagram_aspect_ratio", "unknown"),
        ("diagram_visible_text_policy", "unknown"),
    ],
)
def test_video_generate_request_rejects_invalid_article_concretization_values(
    field_name: str,
    value: str,
):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", **{field_name: value})


def test_video_generate_request_rejects_too_long_diagram_hint():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", diagram_user_intent_hint="x" * 501)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("article_understanding_mode", "unknown"),
        ("visual_planning_mode", "unknown"),
        ("series_visual_signature_strategy", "unknown"),
    ],
)
def test_video_generate_request_rejects_invalid_v44_literal_values(
    field_name: str,
    value: str,
):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", **{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("series_visual_signature_mode", "unknown"),
        ("series_visual_signature_consistency_mode", "unknown"),
    ],
)
def test_video_generate_request_rejects_invalid_series_visual_signature_strategy_controls(
    field_name: str,
    value: str,
):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", **{field_name: value})


def test_video_generate_request_accepts_generation_world_hint():
    request = VideoGenerateRequest(
        text="demo",
        generation_world_hint="古城漫游，清晨阳光，IP 作为陪伴式向导出现。",
    )

    assert request.generation_world_hint == "古城漫游，清晨阳光，IP 作为陪伴式向导出现。"


def test_video_generate_request_normalizes_blank_generation_world_hint():
    request = VideoGenerateRequest(
        text="demo",
        generation_world_hint="   ",
    )

    assert request.generation_world_hint is None


def test_video_generate_request_rejects_enabled_ip_without_required_ids():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", series_visual_signature_enabled=True, series_visual_signature_asset_bible_id="bible_demo")

    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", series_visual_signature_enabled=True, series_visual_signature_profile_id="ip_main")


def test_video_generate_request_rejects_raw_ip_resource_id_syntax():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            series_visual_signature_enabled=True,
            series_visual_signature_asset_bible_id="../bible_demo",
            series_visual_signature_profile_id="ip_main",
        )


def test_build_video_generation_params_copies_series_visual_signature_controls():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            series_visual_signature_enabled=True,
            series_visual_signature_asset_bible_id="bible_demo",
            series_visual_signature_profile_id="ip_main",
        ),
        request_id="req_test",
    )

    assert params["series_visual_signature_enabled"] is True
    assert params["series_visual_signature_asset_bible_id"] == "bible_demo"
    assert params["series_visual_signature_profile_id"] == "ip_main"
    assert params["series_visual_signature_llm_prompt_assembly_enabled"] is False
    assert params["series_visual_signature_expression_mode"] == "auto"
    assert params["series_visual_signature_structure_mode"] == "auto"
    assert params["series_visual_signature_participation_mode"] == "auto"
    assert params["series_visual_signature_presentation_mode"] == "auto"
    assert params["series_visual_signature_output_validation_mode"] == "off"
    assert params["series_visual_signature_output_max_attempts"] == 1


def test_build_video_generation_params_copies_llm_prompt_assembly_opt_out():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            series_visual_signature_enabled=True,
            series_visual_signature_asset_bible_id="bible_demo",
            series_visual_signature_profile_id="ip_main",
            series_visual_signature_llm_prompt_assembly_enabled=False,
        ),
        request_id="req_test",
    )

    assert params["series_visual_signature_llm_prompt_assembly_enabled"] is False


def test_build_video_generation_params_copies_explicit_presentation_controls():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            series_visual_signature_enabled=True,
            series_visual_signature_asset_bible_id="bible_demo",
            series_visual_signature_profile_id="ip_main",
            series_visual_signature_presentation_mode="auto",
            series_visual_signature_enforcement="strict",
            series_visual_signature_fallback_enabled=False,
            series_visual_signature_fallback_mode="disabled",
            series_visual_signature_min_visibility="clear",
        ),
        request_id="req_test",
    )

    assert params["series_visual_signature_presentation_mode"] == "auto"
    assert params["series_visual_signature_enforcement"] == "strict"
    assert params["series_visual_signature_fallback_enabled"] is False
    assert params["series_visual_signature_fallback_mode"] == "disabled"
    assert params["series_visual_signature_min_visibility"] == "clear"


def test_build_video_generation_params_copies_v44_planning_controls():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            article_understanding_mode="thesis_argument",
            visual_planning_mode="structural_explainer",
            series_visual_signature_strategy="host_explainer",
            user_intent_hint="explain the policy change",
            allow_mixed_lenses=False,
            strict_user_mode=True,
            force_v44_planning=True,
        ),
        request_id="req_v44",
    )

    assert params["article_understanding_mode"] == "thesis_argument"
    assert params["visual_planning_mode"] == "structural_explainer"
    assert params["series_visual_signature_strategy"] == "host_explainer"
    assert params["user_intent_hint"] == "explain the policy change"
    assert params["allow_mixed_lenses"] is False
    assert params["strict_user_mode"] is True
    assert params["force_v44_planning"] is True


def test_router_passes_article_concretization_fields_to_video_params():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            article_concretization_enabled=True,
            cognitive_anchor_kind="judgment",
            explanation_diagram_grammar="single_explanation_image",
            series_visual_signature_role="silent_witness",
            diagram_render_style="clean_vector",
            diagram_aspect_ratio="square_1_1",
            diagram_visible_text_policy="approved_labels_only",
            diagram_approved_labels=["Risk", "Reward"],
            diagram_user_intent_hint="compare the tradeoff",
        ),
        request_id="req_article_concretization",
    )

    assert params["article_concretization_enabled"] is True
    assert params["cognitive_anchor_kind"] == "judgment"
    assert params["explanation_diagram_grammar"] == "single_explanation_image"
    assert params["series_visual_signature_role"] == "silent_witness"
    assert params["diagram_render_style"] == "clean_vector"
    assert params["diagram_aspect_ratio"] == "square_1_1"
    assert params["diagram_visible_text_policy"] == "approved_labels_only"
    assert params["diagram_approved_labels"] == ["Risk", "Reward"]
    assert params["diagram_user_intent_hint"] == "compare the tradeoff"


def test_build_video_generation_params_copies_generation_world_hint():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            generation_world_hint="古城漫游，清晨阳光，IP 作为陪伴式向导出现。",
        ),
        request_id="req_world_hint",
    )

    assert params["generation_world_hint"] == "古城漫游，清晨阳光，IP 作为陪伴式向导出现。"


def test_standard_video_generation_contract_normalizes_generation_world_hint():
    params = normalize_standard_video_generation_params(
        {"generation_world_hint": "  古城漫游  "}
    )

    assert params["generation_world_hint"] == "古城漫游"


def test_standard_video_generation_contract_omits_blank_generation_world_hint():
    params = normalize_standard_video_generation_params(
        {"generation_world_hint": "   "}
    )

    assert "generation_world_hint" not in params


def test_standard_video_generation_contract_provides_v44_planning_defaults():
    params = normalize_standard_video_generation_params({"text": "demo"})

    assert params["article_understanding_mode"] == "auto"
    assert params["visual_planning_mode"] == "auto"
    assert params["series_visual_signature_strategy"] == "auto"
    assert params["user_intent_hint"] is None
    assert params["allow_mixed_lenses"] is True
    assert params["strict_user_mode"] is False
    assert params["force_v44_planning"] is False


def test_disabled_article_concretization_has_no_prompt_side_effects_in_generation_contract():
    params = normalize_standard_video_generation_params(
        {
            "text": "demo",
            "article_concretization_enabled": False,
            "cognitive_anchor_kind": "process",
            "explanation_diagram_grammar": "process_flow",
            "series_visual_signature_role": "none",
            "diagram_render_style": "editorial_diagram",
            "diagram_aspect_ratio": "landscape_16_9",
            "diagram_visible_text_policy": "no_visible_text",
            "diagram_approved_labels": ["Draft"],
            "diagram_user_intent_hint": "  keep this as request metadata only  ",
        }
    )

    assert params["article_concretization_enabled"] is False
    assert params["cognitive_anchor_kind"] == "process"
    assert params["explanation_diagram_grammar"] == "process_flow"
    assert params["series_visual_signature_role"] == "none"
    assert params["diagram_render_style"] == "editorial_diagram"
    assert params["diagram_aspect_ratio"] == "landscape_16_9"
    assert params["diagram_visible_text_policy"] == "no_visible_text"
    assert params["diagram_approved_labels"] == ["Draft"]
    assert params["diagram_user_intent_hint"] == "keep this as request metadata only"
    assert params["article_concretization"] == {
        "enabled": False,
        "cognitive_anchor_kind": "process",
        "explanation_diagram_grammar": "process_flow",
        "series_visual_signature_role": "none",
        "diagram_render_style": "editorial_diagram",
        "diagram_aspect_ratio": "landscape_16_9",
        "diagram_visible_text_policy": "no_visible_text",
        "diagram_approved_labels": ["Draft"],
        "diagram_user_intent_hint": "keep this as request metadata only",
    }
    for side_effect_key in (
        "article_concretization_plan",
        "article_concretization_prompt",
        "projected_prompt_parts",
    ):
        assert side_effect_key not in params


def test_standard_video_generation_contract_preserves_top_level_enabled_key():
    params = normalize_standard_video_generation_params(
        {
            "text": "demo",
            "enabled": True,
        }
    )

    assert params["enabled"] is True
    assert params["article_concretization_enabled"] is False
    assert params["article_concretization"]["enabled"] is False


def test_standard_video_generation_contract_accepts_nested_enabled_alias():
    params = normalize_standard_video_generation_params(
        {
            "text": "demo",
            "article_concretization": {
                "enabled": True,
            },
        }
    )

    assert params["article_concretization_enabled"] is True
    assert params["article_concretization"]["enabled"] is True


@pytest.mark.parametrize(
    ("flat_enabled", "nested_enabled", "expected_enabled"),
    [
        (False, True, True),
        (True, False, False),
    ],
)
def test_standard_video_generation_contract_nested_concretization_overrides_flat_enabled(
    flat_enabled: bool,
    nested_enabled: bool,
    expected_enabled: bool,
):
    params = normalize_standard_video_generation_params(
        {
            "text": "demo",
            "article_concretization_enabled": flat_enabled,
            "article_concretization": {
                "enabled": nested_enabled,
            },
        }
    )

    assert params["article_concretization_enabled"] is expected_enabled
    assert params["article_concretization"]["enabled"] is expected_enabled


def test_standard_video_generation_contract_normalizes_all_v44_request_fields():
    params = normalize_standard_video_generation_params(
        {
            "text": "demo",
            "user_intent_hint": "  explain policy change  ",
            "allow_mixed_lenses": "false",
        }
    )

    assert params["user_intent_hint"] == "explain policy change"
    assert params["allow_mixed_lenses"] is False


@pytest.mark.parametrize(
    "field_name",
    ["article_understanding_mode", "visual_planning_mode", "series_visual_signature_strategy"],
)
def test_standard_video_generation_contract_rejects_invalid_v44_enum_values(
    field_name: str,
):
    with pytest.raises(ValueError, match=field_name):
        normalize_standard_video_generation_params({field_name: "unknown"})


@pytest.mark.parametrize(
    "field_name",
    ["series_visual_signature_mode", "series_visual_signature_consistency_mode"],
)
def test_standard_video_generation_contract_rejects_invalid_series_visual_signature_strategy_controls(
    field_name: str,
):
    with pytest.raises(ValueError, match=field_name):
        normalize_standard_video_generation_params({field_name: "unknown"})
    with pytest.raises(ValueError, match=field_name):
        validate_standard_video_generation_params({"text": "demo", field_name: "unknown"})


@pytest.mark.parametrize(
    "field_name",
    ["allow_mixed_lenses", "strict_user_mode", "force_v44_planning"],
)
def test_standard_video_generation_contract_rejects_invalid_v44_boolean_strings(
    field_name: str,
):
    with pytest.raises(ValueError, match=field_name):
        validate_standard_video_generation_params({"text": "demo", field_name: "maybe"})


def test_standard_video_generation_contract_requires_ip_ids_when_enabled():
    with pytest.raises(ValueError, match="series_visual_signature_asset_bible_id"):
        validate_standard_video_generation_params({"series_visual_signature_enabled": True})

    with pytest.raises(ValueError, match="series_visual_signature_profile_id"):
        validate_standard_video_generation_params(
            {"series_visual_signature_enabled": True, "series_visual_signature_asset_bible_id": "bible_demo"}
        )


@pytest.mark.parametrize(
    "params",
    [
        {"image_style_id": "flat-style"},
        {"image_style_revision": "a" * 64},
        {
            "prompt_prefix": "raw style",
            "image_style_id": "flat-style",
            "image_style_revision": "a" * 64,
        },
    ],
)
def test_standard_video_generation_contract_rejects_invalid_image_style_selection(params):
    with pytest.raises(ValueError):
        validate_standard_video_generation_params(params)


def test_build_video_generation_params_normalizes_layered_template_snapshot():
    spec = _layered_spec_payload("user-demo")

    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            layered_template_spec=spec,
            selected_template_preset_id="user:demo",
        ),
        request_id="req_test",
    )

    assert params["layered_template_spec"] == spec
    assert params["selected_template_preset_id"] == "user:demo"


def test_build_video_generation_params_omits_empty_layered_template_snapshot():
    empty_spec = LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="system:1080x1920/image_default.html",
        template_name="Image Default",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=0, y=0, width=1080, height=1920),
        layers=(),
        metadata={},
    ).to_dict()

    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            layered_template_spec=empty_spec,
            selected_template_preset_id="system:1080x1920/image_default.html",
        ),
        request_id="req_test",
    )

    assert "layered_template_spec" not in params
    assert "selected_template_preset_id" not in params


def test_video_generate_request_rejects_legacy_text_fields():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="hello", text_layer={"enabled": True})

    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="hello", forbid_embedded_text_in_image=True)


@pytest.mark.parametrize(
    "text_rendering",
    [
        {"unexpected": {}},
        {"overlay": {"enabled": True, "unexpected": "x"}},
        {"image_text": {"suppress_embedded_text": True, "unexpected": "x"}},
    ],
)
def test_video_generate_request_rejects_unknown_text_rendering_keys(text_rendering: dict):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="hello", text_rendering=text_rendering)


def test_video_generate_request_accepts_tts_text_policy_controls():
    request = VideoGenerateRequest(
        text="demo",
        tts_split_mode="external_only",
        max_chars_per_tts_segment=88,
        tts_split_overflow_policy="hard_limit",
        tts_boundary_search_radius=7,
        tts_soft_overflow_chars=2,
        tts_audio_boundary_fade_ms=12,
        tts_sentence_joiner_mode="space",
        caption_punctuation_mode="preserve",
        preserve_natural_punctuation=False,
    )

    assert request.tts_split_mode == "external_only"
    assert request.max_chars_per_tts_segment == 88
    assert request.tts_sentence_joiner_mode == "space"
    assert request.caption_punctuation_mode == "preserve"
    assert request.preserve_natural_punctuation is False


def test_video_generate_request_accepts_prompt_generation_performance_controls():
    request = VideoGenerateRequest(
        text="demo",
        llm_prompt_batch_size=8,
        llm_prompt_batch_concurrent_limit=3,
    )

    assert request.llm_prompt_batch_size == 8
    assert request.llm_prompt_batch_concurrent_limit == 3


def test_video_generate_request_accepts_size_contract_controls():
    request = VideoGenerateRequest(
        text="demo",
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        video_orientation="landscape",
        video_resolution_preset="landscape_hd",
        media_orientation="square",
        media_resolution_preset="768",
        sync_media_size_to_canvas=False,
    )

    assert request.canvas_width == 1280
    assert request.canvas_height == 720
    assert request.media_width == 768
    assert request.media_height == 768
    assert request.video_orientation == "landscape"
    assert request.video_resolution_preset == "landscape_hd"
    assert request.media_orientation == "square"
    assert request.media_resolution_preset == "768"
    assert request.sync_media_size_to_canvas is False


def test_video_generate_request_rejects_canvas_above_render_resource_budget():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            canvas_width=4098,
            canvas_height=2160,
        )


def test_video_generate_request_rejects_odd_canvas_dimensions():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            canvas_width=1279,
            canvas_height=720,
        )


def test_internal_video_request_rejects_template_canvas_orientation_mismatch():
    with pytest.raises(ValidationError, match="Template orientation"):
        VideoGenerateInternalRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            video_orientation="landscape",
            video_resolution_preset="landscape_hd",
        )


def test_video_generate_request_defaults_media_placement():
    request = VideoGenerateRequest(text="demo")

    assert request.media_placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "offset_x": 0,
        "offset_y": 0,
    }


def test_video_generate_request_accepts_media_placement():
    request = VideoGenerateRequest(
        text="demo",
        media_placement={"scale_percent": 100, "offset_x": 64, "offset_y": -32},
    )

    assert request.media_placement.scale_percent == 100
    assert request.media_placement.offset_x == 64
    assert request.media_placement.offset_y == -32


@pytest.mark.parametrize("scale_percent", [9, 101, 80.5, 80.0, "80", True])
def test_video_generate_request_rejects_invalid_media_placement_scale(scale_percent):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            media_placement={"scale_percent": scale_percent},
        )


@pytest.mark.parametrize(
    "media_placement",
    [
        {"anchor": "middle"},
        {"basis": "template"},
        {"fit": "crop"},
        {"scale_percent": 80, "offset_x": 12.5},
    ],
)
def test_video_generate_request_rejects_invalid_media_placement_values(media_placement):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", media_placement=media_placement)


@pytest.mark.parametrize("fit", ["contain", "cover", "stretch", "original_size"])
def test_video_generate_request_accepts_supported_media_fit_modes(fit):
    request = VideoGenerateRequest(text="demo", media_placement={"fit": fit})

    assert request.media_placement.fit == fit


def test_build_video_generation_params_includes_media_placement():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            media_placement={"scale_percent": 90, "offset_x": 0, "offset_y": 120},
        ),
        request_id="req_test",
    )

    assert params["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "offset_x": 0,
        "offset_y": 120,
    }


def test_video_generate_request_accepts_new_full_hd_preset():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            video_orientation="landscape",
            video_resolution_preset="landscape_full_hd",
        ),
        request_id="req_test",
    )

    assert (params["canvas_width"], params["canvas_height"]) == (1920, 1080)
    assert params["video_resolution_preset"] == "landscape_full_hd"


@pytest.mark.parametrize(
    ("orientation", "preset"),
    [
        (orientation, preset)
        for orientation, presets in STANDARD_VIDEO_SIZE_PRESETS.items()
        for preset in presets
    ],
)
def test_video_generate_request_infers_orientation_from_standard_preset(
    orientation: str,
    preset: str,
):
    request = VideoGenerateRequest(text="demo", video_resolution_preset=preset)

    assert request.video_orientation == orientation
    assert request.video_resolution_preset == preset


def test_video_generate_request_rejects_conflicting_standard_preset_orientation():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            video_orientation="landscape",
            video_resolution_preset="portrait_hd",
        )


def test_video_generate_request_rejects_non_standard_1920x720_output():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            video_resolution_preset="1920x720",
        )


def test_video_generate_request_accepts_size_contract_default_params():
    default_size = GenerationSizeContract.default()
    params = default_size.to_params()
    request = VideoGenerateRequest(text="demo", **params)

    assert request.video_resolution_preset == default_size.video_resolution_preset


def test_build_video_generation_params_preserves_legacy_media_only_canvas_size():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            media_width=1080,
            media_height=1920,
        ),
        request_id="req_test",
    )

    assert (params["canvas_width"], params["canvas_height"]) == (1080, 1920)
    assert (params["media_width"], params["media_height"]) == (1080, 1920)


def test_video_generate_request_rejects_invalid_size_contract_controls():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            media_orientation="landscape",
            media_resolution_preset="768",
        )


def test_video_generate_request_rejects_video_preset_for_media_resolution():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            media_resolution_preset="landscape_hd",
        )


def test_video_generate_request_accepts_storyboard_generation_contract_fields():
    request = VideoGenerateRequest(
        text="demo",
        mode="generate",
        storyboard_mode="smart",
        storyboard_count_mode="manual",
        storyboard_scene_count=4,
        storyboard_prompt_language="zh_CN",
        script_length_mode="custom",
        script_target_words=180,
    )

    assert request.storyboard_mode == "smart"
    assert request.storyboard_count_mode == "manual"
    assert request.storyboard_scene_count == 4
    assert request.storyboard_prompt_language == "zh_CN"
    assert request.script_length_mode == "custom"
    assert request.script_target_words == 180


def test_video_generate_request_defaults_punctuation_max_scene_count_for_punctuation_mode():
    request = VideoGenerateRequest(
        text="demo",
        storyboard_mode="punctuation",
    )

    assert request.storyboard_max_scene_count == 60


def test_video_generate_request_defaults_deterministic_max_scene_count_for_sentence_mode():
    request = VideoGenerateRequest(
        text="demo",
        storyboard_mode="sentence",
    )

    assert request.storyboard_max_scene_count == 60


def test_video_generate_request_clamps_deterministic_default_to_configured_limit(monkeypatch):
    monkeypatch.setattr(
        video_schema_module,
        "current_storyboard_generation_limits",
        lambda: StoryboardGenerationLimits(
            min_scene_count=1,
            max_scene_count=4,
            deterministic_max_scene_count_limit=40,
        ),
    )

    request = VideoGenerateRequest(
        text="demo",
        storyboard_mode="punctuation",
    )

    assert request.storyboard_max_scene_count == 40


def test_video_generate_request_defaults_storyboard_prompt_language_to_english_for_api_compatibility():
    request = VideoGenerateRequest(text="demo")

    assert request.storyboard_prompt_language == "zh_CN"
    assert request.video_orientation is None


def test_video_generate_request_accepts_plan_identity_frame_overrides():
    request = VideoGenerateRequest(
        text="demo",
        frame_overrides=[
            {
                "plan_id": "plan_abc",
                "plan_revision": 1,
                "frame_id": "frame_0001",
                "source_digest": "a" * 64,
                "locked_fields": ["visual_goal", "prompt_intent"],
                "visual_goal": "Locked visual goal.",
                "prompt_intent": "Locked prompt intent.",
            }
        ],
    )

    assert request.frame_overrides[0].frame_id == "frame_0001"
    assert request.frame_overrides[0].locked_fields == ["visual_goal", "prompt_intent"]


def test_video_generate_request_accepts_mandatory_anchor_frame_overrides():
    request = VideoGenerateRequest(
        text="demo",
        frame_overrides=[
            {
                "plan_id": "plan_abc",
                "plan_revision": 1,
                "frame_id": "frame_0001",
                "source_digest": "a" * 64,
                "locked_fields": [
                    "mandatory_anchor_area_ratio",
                    "mandatory_anchor_horizontal_position",
                    "mandatory_anchor_depth_position",
                    "mandatory_anchor_visible_extent",
                    "mandatory_anchor_action_verb",
                    "mandatory_anchor_interaction_target",
                ],
                "mandatory_anchor_area_ratio": 0.8,
                "mandatory_anchor_horizontal_position": "cross_frame",
                "mandatory_anchor_depth_position": "full_frame",
                "mandatory_anchor_visible_extent": "headshot",
                "mandatory_anchor_action_verb": "holds",
                "mandatory_anchor_interaction_target": "safety barrier",
            }
        ],
    )

    override = request.frame_overrides[0]
    assert override.mandatory_anchor_area_ratio == 0.8
    assert override.mandatory_anchor_horizontal_position == "cross_frame"
    assert override.mandatory_anchor_depth_position == "full_frame"
    assert override.mandatory_anchor_visible_extent == "headshot"
    assert override.mandatory_anchor_action_verb == "holds"
    assert override.mandatory_anchor_interaction_target == "safety barrier"


@pytest.mark.parametrize("ratio", [0, 1.1])
def test_video_generate_request_rejects_invalid_mandatory_anchor_area_ratio(
    ratio,
):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["mandatory_anchor_area_ratio"],
                    "mandatory_anchor_area_ratio": ratio,
                }
            ],
        )


def test_video_generate_request_rejects_removed_narration_text_frame_override():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["narration_text"],
                    "narration_text": "This old field must not be accepted.",
                }
            ],
        )


def test_video_generate_request_schema_describes_source_text_contract_not_narration_generation():
    schema_text = json.dumps(VideoGenerateRequest.model_json_schema())

    assert "AI generates narrations" not in schema_text
    assert "narration generation" not in schema_text
    assert "complete source_text" in schema_text


def test_video_generate_request_rejects_non_sha256_frame_override_source_digest():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "z" * 64,
                    "locked_fields": ["visual_goal"],
                    "visual_goal": "Locked visual goal.",
                }
            ],
        )


@pytest.mark.parametrize(
    "legacy_payload",
    [
        {"n_scenes": 5},
        {"split_mode": "sentence"},
    ],
)
def test_video_generate_request_rejects_legacy_storyboard_fields(legacy_payload):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            **legacy_payload,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"storyboard_mode": "smart", "storyboard_count_mode": "auto", "storyboard_scene_count": 4},
        {"storyboard_mode": "smart", "storyboard_count_mode": "manual"},
        {"storyboard_mode": "smart", "storyboard_max_scene_count": 60},
        {"storyboard_mode": "sentence", "storyboard_count_mode": "manual", "storyboard_scene_count": 2},
        {"storyboard_mode": "punctuation", "storyboard_count_mode": "auto", "storyboard_scene_count": 2},
        {"storyboard_mode": "punctuation", "storyboard_max_scene_count": 201},
        {"storyboard_mode": "sentence", "storyboard_max_scene_count": 201},
        {"mode": "fixed", "script_length_mode": "short"},
        {"mode": "fixed", "script_target_words": 120},
        {"mode": "generate", "script_length_mode": "custom"},
        {"mode": "generate", "script_length_mode": "auto", "script_target_words": 120},
    ],
)
def test_video_generate_request_rejects_invalid_storyboard_contract_combinations(payload):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            **payload,
        )


def test_video_generate_request_rejects_deterministic_scene_limit_above_configured_cap(monkeypatch):
    monkeypatch.setattr(
        video_schema_module,
        "current_storyboard_generation_limits",
        lambda: StoryboardGenerationLimits(
            min_scene_count=1,
            max_scene_count=4,
            deterministic_max_scene_count_limit=40,
        ),
    )

    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            storyboard_mode="sentence",
            storyboard_max_scene_count=41,
        )


def test_video_generate_request_rejects_scene_count_above_configured_limit(monkeypatch):
    monkeypatch.setattr(
        video_schema_module,
        "current_storyboard_generation_limits",
        lambda: StoryboardGenerationLimits(min_scene_count=1, max_scene_count=4),
    )

    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            storyboard_count_mode="manual",
            storyboard_scene_count=5,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("llm_prompt_batch_size", 0),
        ("llm_prompt_batch_size", 51),
        ("llm_prompt_batch_concurrent_limit", 0),
        ("llm_prompt_batch_concurrent_limit", 11),
    ],
)
def test_video_generate_request_rejects_invalid_prompt_generation_performance_controls(
    field_name: str,
    value: int,
):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            **{field_name: value},
        )


@pytest.mark.asyncio
async def test_generate_video_sync_passes_tts_text_policy_controls_to_video_core(monkeypatch, tmp_path):
    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    output_path = tmp_path / "task-tts-policy" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    await generate_video_sync(
        _public_video_request(
            text="demo",
            tts_split_mode="external_only",
            max_chars_per_tts_segment=88,
            tts_split_overflow_policy="hard_limit",
            tts_boundary_search_radius=7,
            tts_soft_overflow_chars=2,
            tts_audio_boundary_fade_ms=12,
            tts_sentence_joiner_mode="space",
            caption_punctuation_mode="preserve",
            preserve_natural_punctuation=False,
        ),
        fake_pixelle_video,
        _api_request_context(),
    )

    call = fake_pixelle_video.calls[0]
    assert call["tts_split_mode"] == "external_only"
    assert call["max_chars_per_tts_segment"] == 88
    assert call["tts_split_overflow_policy"] == "hard_limit"
    assert call["tts_boundary_search_radius"] == 7
    assert call["tts_soft_overflow_chars"] == 2
    assert call["tts_audio_boundary_fade_ms"] == 12
    assert call["tts_sentence_joiner_mode"] == "space"
    assert call["caption_punctuation_mode"] == "preserve"
    assert call["preserve_natural_punctuation"] is False


@pytest.mark.asyncio
async def test_generate_video_sync_passes_prompt_generation_performance_controls_to_video_core(
    monkeypatch,
    tmp_path,
):
    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    output_path = tmp_path / "task-prompt-performance" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    await generate_video_sync(
        _public_video_request(
            text="demo",
            llm_prompt_batch_size=8,
            llm_prompt_batch_concurrent_limit=3,
            article_understanding_mode="cognitive_state",
            visual_planning_mode="cognitive_illustration",
            series_visual_signature_strategy="signature_presence",
            strict_user_mode=True,
            force_v44_planning=True,
        ),
        fake_pixelle_video,
        _api_request_context(),
    )

    call = fake_pixelle_video.calls[0]
    assert call["llm_prompt_batch_size"] == 8
    assert call["llm_prompt_batch_concurrent_limit"] == 3
    assert call["article_understanding_mode"] == "cognitive_state"
    assert call["visual_planning_mode"] == "cognitive_illustration"
    assert call["series_visual_signature_strategy"] == "signature_presence"
    assert call["strict_user_mode"] is True
    assert call["force_v44_planning"] is True


@pytest.mark.asyncio
async def test_generate_video_sync_passes_explicit_size_contract_without_template_lookup(
    monkeypatch,
    tmp_path,
):
    output_path = tmp_path / "task-size-contract" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    def fail_template_size_lookup(*args, **kwargs):
        raise AssertionError("API must not derive size from frame_template")

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        fail_template_size_lookup,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    await generate_video_sync(
        _public_video_request(
            text="demo",
            canvas_width=1280,
            canvas_height=720,
            media_width=768,
            media_height=768,
            video_orientation="landscape",
            video_resolution_preset="1k",
            media_orientation="square",
            media_resolution_preset="768",
            sync_media_size_to_canvas=False,
        ),
        fake_pixelle_video,
        _api_request_context(),
    )

    call = fake_pixelle_video.calls[0]
    assert (call["canvas_width"], call["canvas_height"]) == (1280, 720)
    assert (call["media_width"], call["media_height"]) == (768, 768)
    assert call["video_orientation"] == "landscape"
    assert call["video_resolution_preset"] == "1k"
    assert call["media_orientation"] == "square"
    assert call["media_resolution_preset"] == "768"
    assert call["sync_media_size_to_canvas"] is False


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("content_mode", "bogus"),
        ("role_strategy", "bogus"),
        ("consistency_strength", "bogus"),
        ("role_locking_strength", "bogus"),
        ("shot_strategy", "bogus"),
    ],
)
def test_video_generate_request_rejects_invalid_storyboard_controls(field_name: str, value: str):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            **{field_name: value},
        )


@pytest.mark.parametrize(
    "frame_overrides",
    [
        [{"scene_id": "1"}],
        [
            {
                "scene_id": "1",
                "snapshot_identity": "snapshot:demo",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
                "unexpected": "value",
            }
        ],
    ],
)
def test_video_generate_request_rejects_malformed_frame_overrides(frame_overrides: list[dict[str, str]]):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_overrides=frame_overrides,
        )


def test_video_generate_request_rejects_legacy_scene_identity_frame_override():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_overrides=[
                {
                    "scene_id": "scene-1",
                    "snapshot_identity": "snapshot:scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        )


def test_video_generate_request_rejects_narration_text_frame_override():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["narration_text"],
                    "narration_text": "legacy narration",
                }
            ],
        )


@pytest.mark.parametrize("tts_audio_strategy", ["per_frame", "bogus"])
def test_video_generate_request_rejects_unsupported_tts_audio_strategy(tts_audio_strategy):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            tts_audio_strategy=tts_audio_strategy,
        )


@pytest.mark.asyncio
async def test_generate_video_sync_passes_storyboard_controls_to_video_core(monkeypatch, tmp_path):
    expected_size = GenerationSizeContract.from_params({"video_orientation": "portrait"}).to_params()

    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    output_path = tmp_path / "task-1" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    await generate_video_sync(
        VideoGenerateInternalRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            tts_workflow="selfhost/tts_edge.json",
            render_backend="hyperframes_compiled",
            tts_audio_strategy="master_track",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=4,
            storyboard_prompt_language="zh_CN",
            script_length_mode="custom",
            script_target_words=180,
            world_preset_id="neutral_knowledge_storyboard",
            generation_world_hint="古城漫游，IP 是陪伴式向导。",
            shot_preset_id="balanced_explainer",
            consistency_strength="strong",
            content_mode="concept_explainer",
            role_strategy="auto",
            role_locking_strength="strong",
            shot_strategy="strict",
            text_rendering={
                "overlay": {
                    "enabled": True,
                    "mode": "programmatic_only",
                    "renderer_targets": ["ass"],
                },
                "image_text": {
                    "suppress_embedded_text": True,
                    "positive_prompt": "no letters in image",
                    "negative_prompt": "letters, watermark",
                },
            },
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["visual_goal", "prompt_intent"],
                    "visual_goal": "Locked visual goal.",
                    "prompt_intent": "Locked prompt intent.",
                }
            ],
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    assert fake_pixelle_video.calls == [
        {
            "text": "demo",
            "mode": "generate",
            "title": None,
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 4,
            "storyboard_max_scene_count": None,
            "storyboard_prompt_language": "zh_CN",
            "script_length_mode": "custom",
            "script_target_words": 180,
            "min_image_prompt_words": 30,
            "max_image_prompt_words": 60,
            **expected_size,
            "media_placement": {
                "basis": "canvas",
                "fit": "contain",
                "scale_percent": 100,
                "offset_x": 0,
                "offset_y": 0,
            },
            "media_workflow": None,
            "tts_workflow": "selfhost/tts_edge.json",
            "video_fps": 30,
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": None,
            "image_style_id": None,
            "image_style_revision": None,
            "bgm_path": None,
            "bgm_volume": 0.3,
            "request_id": "req_test",
            "template_display": {"show_title": False, "show_signature": False},
            "render_backend": "hyperframes_compiled",
            "tts_audio_strategy": "master_track",
            "world_preset_id": "neutral_knowledge_storyboard",
            "generation_world_hint": "古城漫游，IP 是陪伴式向导。",
            "shot_preset_id": "balanced_explainer",
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "series_visual_signature_enabled": False,
            "series_visual_signature_asset_bible_id": None,
            "series_visual_signature_profile_id": None,
            "article_understanding_mode": "auto",
            "visual_planning_mode": "auto",
            "series_visual_signature_strategy": "auto",
            "user_intent_hint": None,
            "allow_mixed_lenses": True,
            "strict_user_mode": False,
            "force_v44_planning": False,
            "article_concretization_enabled": False,
            "cognitive_anchor_kind": "auto",
            "explanation_diagram_grammar": "auto",
            "series_visual_signature_role": "none",
            "diagram_render_style": "auto",
            "diagram_aspect_ratio": "auto",
            "diagram_visible_text_policy": "no_visible_text",
            "diagram_approved_labels": [],
            "diagram_user_intent_hint": None,
            "text_rendering": {
                "caption": {"enabled": True},
                "overlay": {
                    "enabled": True,
                    "mode": "programmatic_only",
                    "renderer_targets": ["ass"],
                    "density": "medium",
                    "max_items_per_frame": 2,
                },
                "image_text": {
                    "suppress_embedded_text": True,
                    "positive_prompt": "no letters in image",
                    "negative_prompt": "letters, watermark",
                },
            },
            "frame_overrides": [
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["visual_goal", "prompt_intent"],
                    "visual_goal": "Locked visual goal.",
                    "prompt_intent": "Locked prompt intent.",
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_generate_video_async_reuses_active_duplicate_task(monkeypatch, tmp_path):
    output_path = tmp_path / "task-async" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    class _ExistingTask:
        task_id = "existing-task"

    class _FakeTaskManager:
        execution_mode = "embedded"

        async def reserve_or_reuse_generation_task(
            self,
            *,
            task_type,
            generation_fingerprint,
            request_params,
        ):
            assert task_type.value == "video_generation"
            assert generation_fingerprint
            assert request_params["generation_fingerprint"] == generation_fingerprint
            return SimpleNamespace(
                task=_ExistingTask(),
                created=False,
                reused_reason="active",
            )

        async def execute_task(self, **_kwargs):
            raise AssertionError("duplicate async request should not start execution")

    monkeypatch.setattr("api.routers.video.task_manager", _FakeTaskManager())
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    response = await generate_video_async(
        _public_video_request(
            text="demo",
        ),
        fake_pixelle_video,
        _api_request_context(),
    )

    assert response.task_id == "existing-task"
    assert response.message == "Task already running"
    assert fake_pixelle_video.calls == []


@pytest.mark.asyncio
async def test_generate_video_async_passes_text_rendering_to_video_core(monkeypatch, tmp_path):
    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    output_path = tmp_path / "task-async" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    class _FakeTaskManager:
        execution_mode = "embedded"

        def __init__(self) -> None:
            self.reserve_calls = []

        async def reserve_or_reuse_generation_task(
            self,
            *,
            task_type,
            generation_fingerprint,
            request_params,
        ):
            assert task_type.value == "video_generation"
            assert generation_fingerprint
            assert request_params["generation_fingerprint"] == generation_fingerprint
            self.reserve_calls.append(
                {
                    "task_type": task_type,
                    "generation_fingerprint": generation_fingerprint,
                    "request_params": request_params,
                }
            )
            return SimpleNamespace(
                task=SimpleNamespace(task_id="task-1"),
                created=True,
                reused_reason=None,
            )

        async def execute_task(self, **_kwargs):
            raise AssertionError("async video route should submit but not execute tasks")

    fake_task_manager = _FakeTaskManager()
    monkeypatch.setattr("api.routers.video.task_manager", fake_task_manager)

    response = await generate_video_async(
        _public_video_request(
            text="demo",
            text_rendering={
                "overlay": {
                    "enabled": True,
                    "mode": "hybrid",
                    "renderer_targets": ["hyperframes"],
                },
                "image_text": {
                    "suppress_embedded_text": True,
                    "negative_prompt": "letters",
                },
            },
        ),
        fake_pixelle_video,
        _api_request_context(),
    )

    assert response.task_id == "task-1"
    request_params = fake_task_manager.reserve_calls[0]["request_params"]
    assert request_params["request_id"] == "req_test"
    assert "api_task_id" not in request_params
    text_rendering = request_params["text_rendering"]
    assert text_rendering["overlay"] == {
        "enabled": True,
        "mode": "hybrid",
        "renderer_targets": ["hyperframes"],
        "density": "medium",
        "max_items_per_frame": 2,
    }
    assert text_rendering["image_text"]["suppress_embedded_text"] is True
    assert "no visible text" in text_rendering["image_text"]["positive_prompt"]
    assert "no watermark" in text_rendering["image_text"]["positive_prompt"]
    assert text_rendering["image_text"]["negative_prompt"] == "letters"
    assert text_rendering["caption"] == {"enabled": True}
    assert "caption_style" not in text_rendering
    assert "overlay_style" not in text_rendering
    assert fake_pixelle_video.calls == []


@pytest.mark.asyncio
async def test_generate_video_async_submits_new_task_without_router_execution(
    monkeypatch, tmp_path
):
    output_path = tmp_path / "task-async" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        lambda template_path: SimpleNamespace(get_media_size=lambda: (1080, 1920)),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    class _FakeTaskManager:
        execution_mode = "embedded"

        def __init__(self) -> None:
            self.reserve_calls = []

        async def reserve_or_reuse_generation_task(self, **kwargs):
            self.reserve_calls.append(kwargs)
            return SimpleNamespace(
                task=SimpleNamespace(task_id="task-1"),
                created=True,
                reused_reason=None,
            )

        async def execute_task(self, **_kwargs):
            raise AssertionError("async video route should submit but not execute tasks")

    fake_task_manager = _FakeTaskManager()
    monkeypatch.setattr("api.routers.video.task_manager", fake_task_manager)

    response = await generate_video_async(
        _public_video_request(text="demo"),
        fake_pixelle_video,
        _api_request_context(),
    )

    assert response.task_id == "task-1"
    assert fake_task_manager.reserve_calls[0]["task_type"].value == "video_generation"
    assert fake_task_manager.reserve_calls[0]["request_params"]["request_id"] == "req_test"
    assert fake_pixelle_video.calls == []


@pytest.mark.asyncio
async def test_generate_video_async_preserves_explicit_text_styles(monkeypatch, tmp_path):
    output_path = tmp_path / "task-async" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        lambda template_path: SimpleNamespace(get_media_size=lambda: (1080, 1920)),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    class _FakeTaskManager:
        def __init__(self) -> None:
            self.reserve_calls = []

        async def reserve_or_reuse_generation_task(self, **kwargs):
            self.reserve_calls.append(kwargs)
            return SimpleNamespace(
                created=True,
                task=SimpleNamespace(task_id="task-1"),
            )

        async def execute_task(self, **_kwargs):
            raise AssertionError("async video route should submit but not execute tasks")

    fake_task_manager = _FakeTaskManager()
    monkeypatch.setattr("api.routers.video.task_manager", fake_task_manager)

    await generate_video_async(
        _public_video_request(
            text="demo",
            text_rendering={
                "caption_style": {
                    "font_size": 72,
                    "primary_color": "#FFFF00",
                },
                "overlay_style": {
                    "font_size": 88,
                    "position": "center",
                },
            },
        ),
        fake_pixelle_video,
        _api_request_context(),
    )

    text_rendering = fake_task_manager.reserve_calls[0]["request_params"]["text_rendering"]
    assert text_rendering["caption_style"]["font_size"] == 72
    assert text_rendering["caption_style"]["primary_color"] == "#FFFF00"
    assert text_rendering["overlay_style"]["font_size"] == 88
    assert text_rendering["overlay_style"]["position"] == "center"
    assert fake_pixelle_video.calls == []
