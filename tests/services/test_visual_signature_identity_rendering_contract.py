from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.models.visual_anchor_two_stage import (
    CONTENT_PROMPT_PASSTHROUGH_VERSION,
    ContentStagePromptPassthrough,
    ContinuousSceneContext,
    FusionStageInput,
    TargetVisualStyle,
    VisibleTextPolicy,
    VisualSignatureStyleContract,
)
from pixelle_video.prompt_language import CHINESE_PROMPT_LANGUAGE
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
)
from pixelle_video.services.visual_anchor_two_stage_service import (
    _render_stage_prompt,
    identity_profile_from_snapshot,
)
from pixelle_video.services.visual_prompt_composer import _visible_text_policy


def _snapshot(*, authorized_texts: tuple[str, ...] = ("PIXELLE",)):
    profile = IPProfile(
        series_visual_signature_profile_id="pixelle-mark",
        workspace_id="workspace-1",
        project_id="project-1",
        name="小皮",
        identity_lock=("圆形白色脸", "两只短耳保持对称布局"),
        minimal_traits=("左耳蓝色、右耳橙色",),
        identity_anchors=("橙色围巾",),
        forbidden_elements=("改变脸部轮廓",),
        negative_constraints=("增加第三只耳朵",),
        semantic_boundary=("不得替代剧情主体",),
        identity_suppression_rules=("不得隐藏围巾",),
        color_palette={
            "face": {"prompt": "脸部保持纯白"},
            "ears": {"prompt": "左耳鲜蓝、右耳鲜橙"},
        },
        image_text_palette=(
            {"wordmark": {"prompt": "窄体无衬线白色字标"}}
            if authorized_texts
            else {}
        ),
        visible_text_whitelist=authorized_texts,
        style_hint="独立彩色扁平吉祥物风格",
    )
    return SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=SeriesVisualSignatureRequest(
            enabled=True,
            profile_id="pixelle-mark",
            asset_bible_id="asset-1",
        ),
        ip_profile=profile,
    )


def _fusion_input(*, scene_style: str = "真实电影感") -> FusionStageInput:
    identity = identity_profile_from_snapshot(_snapshot())
    return FusionStageInput(
        frame_id="frame-1",
        original_storyboard_text="工程师在工作台检查电路板。",
        content_stage_output=ContentStagePromptPassthrough(
            passthrough_version=CONTENT_PROMPT_PASSTHROUGH_VERSION,
            raw_prompt="工程师在工作台检查电路板",
        ),
        identity_profile=identity,
        identity_conditioning_mode="text_profile",
        workflow_identity_condition_summary="使用固定身份档案保持视觉身份",
        visual_signature_emphasis="standard",
        continuous_scene_context=ContinuousSceneContext(
            scene_id="independent:frame-1",
            previous_frame_summary="首镜，无前一镜",
            next_frame_summary="末镜，无后一镜",
            continuity_anchors=[],
            existing_fusion_decision="无既有融合结果",
        ),
        series_final_prompt_history=[],
        target_visual_style=TargetVisualStyle(description=scene_style),
        visible_text_policy=VisibleTextPolicy(
            authorized_visible_texts=["PIXELLE"]
        ),
        negative_prompt_supported=False,
        target_image_prompt_language="中文",
    )


def test_snapshot_freezes_identity_color_text_and_forbidden_facts() -> None:
    snapshot = _snapshot()

    assert snapshot.core_identity_traits == (
        "圆形白色脸",
        "两只短耳保持对称布局",
        "左耳蓝色、右耳橙色",
    )
    assert snapshot.supporting_identity_traits == ("橙色围巾",)
    assert snapshot.fixed_color_traits == (
        "脸部保持纯白",
        "左耳鲜蓝、右耳鲜橙",
    )
    assert snapshot.authorized_visible_texts == ("PIXELLE",)
    assert snapshot.authorized_text_style_traits == ("窄体无衬线白色字标",)
    assert snapshot.forbidden_traits == (
        "改变脸部轮廓",
        "增加第三只耳朵",
        "不得替代剧情主体",
        "不得隐藏围巾",
    )


def test_current_prompt_keeps_identity_facts_but_follows_scene_rendering() -> None:
    fusion_input = _fusion_input(scene_style="柔和透明水彩场景")

    rendered = _render_stage_prompt("visual_anchor_fusion_stage", fusion_input)

    assert "柔和透明水彩场景" in rendered.text
    assert "脸部保持纯白" in rendered.text
    assert "左耳鲜蓝、右耳鲜橙" in rendered.text
    assert "PIXELLE" in rendered.text
    assert "独立彩色扁平吉祥物风格" not in rendered.text
    assert '"visual_signature_style"' not in rendered.text
    assert "display_name 只是身份元数据" in rendered.text
    assert "authorized_visible_texts 是整幅画唯一允许出现的可读文字" in (
        rendered.text
    )
    assert '"series_final_prompt_history": []' in rendered.text
    assert '"series_fusion_history"' not in rendered.text


def test_authorized_text_is_allowed_without_blanket_text_ban() -> None:
    policy = _visible_text_policy(
        {"image_text": {"suppress_embedded_text": True}},
        prompt_language=CHINESE_PROMPT_LANGUAGE,
        authorized_visible_texts=("PIXELLE", "长乐门"),
    )

    assert policy.authorized_visible_texts == ["PIXELLE", "长乐门"]
    assert "已授权文字“PIXELLE”、“长乐门”" in (
        policy.required_positive_prompt_fragment
    )
    assert "未经授权文字" in policy.required_negative_prompt_fragment
    assert policy.required_negative_prompt_fragment != "文字，水印，标题，乱码"


def test_empty_authorized_text_list_makes_the_image_text_free() -> None:
    policy = _visible_text_policy(
        {"image_text": {"suppress_embedded_text": True}},
        prompt_language=CHINESE_PROMPT_LANGUAGE,
    )

    assert policy.authorized_visible_texts == []
    assert policy.required_positive_prompt_fragment == (
        "画面中禁止出现任何可见文字、标题、水印或乱码"
    )


def test_current_contract_rejects_the_removed_independent_style_layer() -> None:
    payload = _fusion_input().model_dump(mode="json")
    payload["visual_signature_style"] = VisualSignatureStyleContract(
        profile_id="pixelle-mark",
        style_fragments=["独立彩色扁平吉祥物风格"],
        rendering_style="flat_illustration",
        source_style_scope="ip_character_only",
    ).model_dump(mode="json")

    with pytest.raises(ValidationError, match="immutable signature facts"):
        FusionStageInput.model_validate(payload)


def test_tampering_with_a_fixed_color_invalidates_the_identity_digest() -> None:
    snapshot = _snapshot()

    with pytest.raises(ValueError, match="identity_content_sha256"):
        replace(
            snapshot,
            fixed_color_traits=("脸部改成黑色",),
            canonical_identity_clause="",
        )
