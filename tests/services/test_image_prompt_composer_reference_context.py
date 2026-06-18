import json

import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.reference_image import ReferenceImageAsset
from pixelle_video.models.reference_image_analysis import (
    ReferenceImageAnalysis,
    ReferenceImageAnalysisResult,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.services import image_prompt_composer as composer_module
from pixelle_video.services.image_prompt_composer import ImagePromptComposer
from pixelle_video.services.reference_image_visual_context_adapter import (
    ReferenceImageVisualContextAdapter,
    reset_reference_image_visual_story_context_patch,
    set_reference_image_visual_story_context_patch,
)


def _storyboard_plan() -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="小玩偶在森林里找朋友。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="小玩偶在森林里找朋友。",
                visual_goal="小玩偶走在森林小路上",
                prompt_intent="表现温暖和好奇",
                frame_id="frame_0",
            )
        ],
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
            color_atmosphere="浅色暖光",
            composition_summary="主体居中",
            identity_anchors=["圆脸", "白色服饰"],
            style_anchors=["柔和绘本"],
            negative_constraints=["避免赛博朋克"],
            prompt_hint_zh="柔和童话绘本风，白色玩偶角色，暖色光照",
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
        metadata={
            "debug_path": "/home/user/private/ref.png",
            "raw": "data:image/png;base64,AAAA",
        },
    )


async def _compose_with_captured_batch(monkeypatch, **compose_kwargs):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return StyledImagePromptBatch(
            prompts=["reference-aware prompt"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={},
        )

    monkeypatch.setattr(
        composer_module,
        "generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )
    result = await ImagePromptComposer().compose(
        llm_service=None,
        storyboard_plan=_storyboard_plan(),
        image_config={},
        **compose_kwargs,
    )
    return result, captured


@pytest.mark.asyncio
async def test_image_prompt_composer_applies_runtime_reference_context(monkeypatch):
    build_result = ReferenceImageVisualContextAdapter().build(
        asset=_asset(),
        analysis_result=_analysis_result(),
        ip_profile=None,
        merge_mode="supplement",
    )
    token = set_reference_image_visual_story_context_patch(
        build_result.visual_story_context_patch
    )

    try:
        result, captured = await _compose_with_captured_batch(
            monkeypatch,
            ip_profile=_ip_profile(),
            visual_story_context={},
        )
    finally:
        reset_reference_image_visual_story_context_patch(token)

    passed_profile = captured["ip_profile"]
    assert "圆脸" in passed_profile.identity_anchors
    assert "柔和绘本" in passed_profile.style_boundary_rules
    assert captured["prompt_contexts"].plan_context["reference_image"]["enabled"] is True
    assert captured["prompt_contexts"].frame_contexts[0]["reference_image"]["identity_anchors"] == ["圆脸", "白色服饰"]

    snapshot = result.planning_snapshot["reference_image_visual_context"]
    payload = json.dumps(snapshot, ensure_ascii=False)
    assert snapshot["visual_story_context_patch"]["reference_image"]["enabled"] is True
    assert "merged_ip_profile" in snapshot
    assert "/home/user" not in payload
    assert "data:image" not in payload
    assert "base64," not in payload


@pytest.mark.asyncio
async def test_no_reference_patch_keeps_image_prompt_composer_unchanged(monkeypatch):
    token = set_reference_image_visual_story_context_patch({})
    profile = _ip_profile()
    try:
        result, captured = await _compose_with_captured_batch(
            monkeypatch,
            ip_profile=profile,
            visual_story_context={},
        )
    finally:
        reset_reference_image_visual_story_context_patch(token)

    assert captured["ip_profile"] == profile
    assert "reference_image" not in captured["prompt_contexts"].plan_context
    assert "reference_image" not in captured["prompt_contexts"].frame_contexts[0]
    assert "reference_image_visual_context" not in result.planning_snapshot
