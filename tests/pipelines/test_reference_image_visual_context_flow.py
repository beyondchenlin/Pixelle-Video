from types import SimpleNamespace

import pytest

from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.reference_image import ReferenceImageAsset
from pixelle_video.models.reference_image_analysis import (
    ReferenceImageAnalysis,
    ReferenceImageAnalysisResult,
)
from pixelle_video.pipelines.linear import LinearVideoPipeline, PipelineContext
from pixelle_video.services.visual_story_prompt_context import attach_visual_story_context


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


@pytest.mark.asyncio
async def test_prepare_reference_image_visual_context_injects_generation_world_hint(tmp_path):
    pipeline = LinearVideoPipeline(
        SimpleNamespace(
            config={"reference_image": {"profile_merge_mode": "supplement"}},
            llm=None,
            tts=None,
            media=None,
            video=None,
        )
    )
    ctx = PipelineContext(
        input_text="生成一个儿童故事",
        params={"generation_world_hint": "原始世界观提示"},
        task_dir=str(tmp_path),
    )
    ctx.reference_image_asset = _asset()
    ctx.reference_image_analysis_result = _analysis_result()

    await pipeline.prepare_reference_image_visual_context(ctx)

    assert ctx.reference_image_visual_context is not None
    assert ctx.reference_image_visual_context.enabled is True
    assert "原始世界观提示" in ctx.params["generation_world_hint"]
    assert "参考图视觉一致性提示" in ctx.params["generation_world_hint"]
    assert "柔和童话绘本风" in ctx.params["generation_world_hint"]
    assert ctx.params["reference_image_prompt_fallback_hint"]
    assert ctx.params["reference_image_visual_story_context_patch"]["reference_image"]["enabled"] is True
    assert (tmp_path / "reference_image" / "visual_context.json").is_file()

    prompt_contexts = PromptContextEnvelope(
        plan_context={"plan_id": "plan"},
        frame_contexts=[{"frame_id": "frame_0", "source_text": "hello"}],
    )
    enriched = attach_visual_story_context(prompt_contexts, {})
    assert enriched.plan_context["reference_image"]["enabled"] is True
    assert enriched.frame_contexts[0]["reference_image"]["identity_anchors"] == ["圆脸", "白色服饰"]


@pytest.mark.asyncio
async def test_prepare_reference_image_visual_context_does_not_inject_when_analysis_skipped(tmp_path):
    pipeline = LinearVideoPipeline(
        SimpleNamespace(
            config={"reference_image": {"profile_merge_mode": "supplement"}},
            llm=None,
            tts=None,
            media=None,
            video=None,
        )
    )
    ctx = PipelineContext(
        input_text="生成一个儿童故事",
        params={"generation_world_hint": "原始世界观提示"},
        task_dir=str(tmp_path),
    )
    ctx.reference_image_asset = _asset()
    ctx.reference_image_analysis_result = ReferenceImageAnalysisResult(
        status="skipped",
        analysis_mode="auto",
        image_sha256="a" * 64,
        reason="vision_llm_disabled",
    )

    await pipeline.prepare_reference_image_visual_context(ctx)

    assert ctx.reference_image_visual_context is not None
    assert ctx.reference_image_visual_context.enabled is False
    assert ctx.params["generation_world_hint"] == "原始世界观提示"
    assert "reference_image_prompt_fallback_hint" not in ctx.params
