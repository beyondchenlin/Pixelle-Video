import json
from pathlib import Path

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.reference_image import ReferenceImageAsset
from pixelle_video.models.reference_image_analysis import (
    ReferenceImageAnalysis,
    ReferenceImageAnalysisResult,
)
from pixelle_video.services.reference_image_visual_context_adapter import (
    ReferenceImageVisualContextAdapter,
)


def _asset() -> ReferenceImageAsset:
    return ReferenceImageAsset(
        source_kind="local_path",
        original_display_name="role.png",
        task_asset_path="/home/user/secret/role.png",
        task_asset_relative_path="reference_image/original_abcd1234.png",
        vision_asset_path="/home/user/secret/vision.jpg",
        vision_asset_relative_path="reference_image/vision_abcd1234.jpg",
        workflow_asset_path="/home/user/secret/workflow.jpg",
        workflow_asset_relative_path="reference_image/workflow_abcd1234.jpg",
        sha256="a" * 64,
        mime_type="image/jpeg",
        width=100,
        height=120,
        byte_size=2048,
    )


def _analysis_result() -> ReferenceImageAnalysisResult:
    return ReferenceImageAnalysisResult(
        status="success",
        analysis_mode="auto",
        image_sha256="a" * 64,
        vision_model="qwen-vl-max",
        analysis_language="zh_CN",
        analysis=ReferenceImageAnalysis(
            subject_summary="白色玩偶角色，圆脸，简单服饰",
            style_summary="柔和童话绘本风格",
            color_atmosphere="浅色暖光，低饱和 pastel",
            composition_summary="主体居中，背景简洁",
            identity_anchors=["圆脸", "白色服饰"],
            style_anchors=["柔和绘本", "暖色光照"],
            negative_constraints=["避免赛博朋克", "避免暗黑写实"],
            prompt_hint_zh="柔和童话绘本风，白色玩偶角色，暖色光照",
            prompt_hint_en="soft storybook white toy character, warm lighting",
            confidence=0.9,
        ),
    )


def _ip_profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="profile_ref",
        workspace_id="workspace",
        project_id="project",
        name="Existing Role",
        style_hint="用户明确风格",
        identity_anchors=("用户锚点",),
        negative_constraints=("避免低清晰度",),
    )


def test_adapter_builds_prompt_only_context_without_ip_profile(tmp_path):
    result = ReferenceImageVisualContextAdapter().build(
        asset=_asset(),
        analysis_result=_analysis_result(),
        ip_profile=None,
        merge_mode="supplement",
    )

    assert result.ip_profile is None
    assert result.visual_context.enabled is True
    assert "柔和童话绘本风" in result.visual_context.prompt_fallback_hint
    assert result.visual_story_context_patch["reference_image"]["identity_anchors"] == ["圆脸", "白色服饰"]

    visual_context = ReferenceImageVisualContextAdapter.write_artifact(
        tmp_path,
        result.visual_context,
    )
    artifact_text = (tmp_path / "reference_image" / "visual_context.json").read_text(encoding="utf-8")
    assert visual_context.artifact_relative_path == "reference_image/visual_context.json"
    assert "/home/user" not in artifact_text
    assert "base64," not in artifact_text


def test_adapter_supplements_ip_profile_without_overwriting_explicit_fields():
    original = _ip_profile()
    result = ReferenceImageVisualContextAdapter().build(
        asset=_asset(),
        analysis_result=_analysis_result(),
        ip_profile=original,
        merge_mode="supplement",
    )

    assert result.ip_profile is not None
    assert result.ip_profile.style_hint == "用户明确风格"
    assert "用户锚点" in result.ip_profile.identity_anchors
    assert "圆脸" in result.ip_profile.identity_anchors
    assert "柔和绘本" in result.ip_profile.style_boundary_rules
    assert "避免暗黑写实" in result.ip_profile.negative_constraints
    assert result.visual_context.merged_ip_profile is not None


def test_adapter_strict_mode_keeps_ip_profile_unchanged():
    original = _ip_profile()
    result = ReferenceImageVisualContextAdapter().build(
        asset=_asset(),
        analysis_result=_analysis_result(),
        ip_profile=original,
        merge_mode="strict",
    )

    assert result.ip_profile == original
    assert "strict merge mode" in " ".join(result.visual_context.merge_warnings)


def test_visual_context_json_is_trace_safe():
    result = ReferenceImageVisualContextAdapter().build(
        asset=_asset(),
        analysis_result=_analysis_result(),
        ip_profile=_ip_profile(),
        merge_mode="supplement",
    )

    payload = json.dumps(result.visual_context.to_trace_dict(), ensure_ascii=False)
    assert "base64," not in payload
    assert "/home/user" not in payload
    assert "reference_image/vision_abcd1234.jpg" in payload
