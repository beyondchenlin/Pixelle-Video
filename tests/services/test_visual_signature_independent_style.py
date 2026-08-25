from types import SimpleNamespace

import pytest

from pixelle_video.models.visual_anchor_two_stage import (
    CONTENT_PROMPT_PASSTHROUGH_VERSION,
    ContentStagePromptPassthrough,
    ContinuousSceneContext,
    FusionStageInput,
    TargetVisualStyle,
    VisualAnchorIdentityProfile,
)
from pixelle_video.services.visual_anchor_two_stage_service import _render_stage_prompt
from pixelle_video.services.visual_prompt_composer import (
    _visual_signature_style_contract,
)


@pytest.mark.parametrize(
    ("profile_id", "scene_style", "style_hint", "rendering_style", "palette_prompt"),
    [
        (
            "color-mascot",
            "minimalist black-and-white line-art narrative scene",
            "bright colorful flat mascot illustration",
            "flat_illustration",
            "saturated coral and cyan palette",
        ),
        (
            "metal-emblem",
            "soft transparent watercolor narrative scene",
            "polished three-dimensional metallic emblem with brushed steel and gold",
            "style_inherited",
            "brushed silver and warm gold materials",
        ),
        (
            "ink-character",
            "photorealistic cinematic narrative scene",
            "hand-drawn ink character with visible brush texture",
            "style_inherited",
            "warm black ink with a vermilion accent",
        ),
    ],
)
def test_fusion_prompt_keeps_generic_signature_style_separate_from_scene_style(
    profile_id,
    scene_style,
    style_hint,
    rendering_style,
    palette_prompt,
):
    profile = SimpleNamespace(
        series_visual_signature_profile_id=profile_id,
        style_hint=style_hint,
        rendering_style=rendering_style,
        style_scope="ip_character_only",
        style_boundary_rules=("keep this style on the visual signature only",),
        color_palette={"primary": {"prompt": palette_prompt}},
    )
    signature_style = _visual_signature_style_contract(
        ip_profile=profile,
        expected_profile_id=profile_id,
    )
    identity = VisualAnchorIdentityProfile(
        profile_id=profile_id,
        display_name="通用视觉签名",
        core_identity_traits=["稳定轮廓", "固定识别结构"],
        identity_content_sha256="b" * 64,
        identity_resource_version=f"identity:{profile_id}:" + "b" * 64,
    )
    fusion_input = FusionStageInput(
        frame_id="frame-1",
        original_storyboard_text="主体在场景中完成当前动作。",
        content_stage_output=ContentStagePromptPassthrough(
            passthrough_version=CONTENT_PROMPT_PASSTHROUGH_VERSION,
            raw_prompt="主体在清晰环境中完成当前动作",
        ),
        identity_profile=identity,
        identity_conditioning_mode="text_profile",
        workflow_identity_condition_summary="使用文字身份档案保持视觉签名身份",
        visual_signature_emphasis="standard",
        continuous_scene_context=ContinuousSceneContext(
            scene_id="independent:frame-1",
            previous_frame_summary="首镜，无前一镜",
            next_frame_summary="末镜，无后一镜",
            continuity_anchors=[],
            existing_fusion_decision="无既有融合结果",
        ),
        target_visual_style=TargetVisualStyle(description=scene_style),
        visual_signature_style=signature_style,
        negative_prompt_supported=False,
        target_image_prompt_language="中文",
    )

    rendered = _render_stage_prompt("visual_anchor_fusion_stage", fusion_input)

    assert scene_style in rendered.text
    assert style_hint in rendered.text
    assert palette_prompt in rendered.text
    assert signature_style.application_scope == "visual_signature_only"
    assert "target_visual_style 是叙事场景风格" in rendered.text
    assert "visual_signature_style 是视觉身份独立风格" in rendered.text
    assert "不得让视觉身份风格扩散到叙事人物、环境、道具和背景" in rendered.text


def test_missing_independent_signature_style_is_rejected_instead_of_inheriting_scene():
    profile = SimpleNamespace(
        series_visual_signature_profile_id="missing-style",
        style_hint=None,
        rendering_style="style_inherited",
        style_scope="ip_character_only",
        style_boundary_rules=(),
        color_palette={},
    )

    with pytest.raises(ValueError, match="no independent style data"):
        _visual_signature_style_contract(
            ip_profile=profile,
            expected_profile_id="missing-style",
        )
