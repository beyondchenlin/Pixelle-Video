import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.models.reference_image_visual_context import ReferenceImageVisualContext
from pixelle_video.pipelines import linear as linear_module
from pixelle_video.pipelines.linear import (
    LinearVideoPipeline,
    PipelineContext,
    resolve_vision_llm_config,
)
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services import reference_image_workflow_binding as binding_module
from pixelle_video.services.media import MediaService
from pixelle_video.services.prompt_trace_artifacts import write_single_media_prompt_trace_context
from pixelle_video.services.reference_image_visual_context_adapter import (
    current_reference_image_visual_story_context_patch,
    reference_image_prompt_planning_snapshot,
)


class _RecordingReferenceImagePipeline(LinearVideoPipeline):
    async def setup_environment(self, ctx: PipelineContext):
        task_dir = Path(ctx.params.pop("task_dir"))
        task_dir.mkdir(parents=True, exist_ok=True)
        ctx.task_id = "task_ref"
        ctx.task_dir = str(task_dir)

    async def generate_content(self, ctx: PipelineContext):
        ctx.source_text = ctx.input_text

    async def determine_title(self, ctx: PipelineContext):
        ctx.title = "测试标题"

    async def plan_visuals(self, ctx: PipelineContext):
        patch = current_reference_image_visual_story_context_patch()
        snapshot = reference_image_prompt_planning_snapshot(patch)
        ctx.planning_snapshot = (
            {"reference_image_visual_context": snapshot}
            if snapshot
            else {}
        )
        ctx.params["plan_visuals_seen_reference_patch"] = patch

    async def initialize_storyboard(self, ctx: PipelineContext):
        return None

    async def produce_assets(self, ctx: PipelineContext):
        return None

    async def post_production(self, ctx: PipelineContext):
        return None

    async def finalize(self, ctx: PipelineContext):
        self.final_ctx = ctx
        return SimpleNamespace(status="ok", ctx=ctx)


class _MediaRequiredPipeline(_RecordingReferenceImagePipeline):
    async def produce_assets(self, ctx: PipelineContext):
        trace_context = write_single_media_prompt_trace_context(
            Path(ctx.task_dir) / "prompt_traces" / "image" / "frame_001",
            task_id=ctx.task_id or "task_ref",
            prompt="hello world",
            workflow="selfhost/image_plain.json",
            workflow_input="/tmp/fake_workflow.json",
            media_type="image",
            source="test",
            media_width=512,
            media_height=512,
            workflow_params={"prompt": "hello world", "width": 512, "height": 512},
            task_root=ctx.task_dir,
        )
        await self.core.media(
            prompt="hello world",
            workflow="selfhost/image_plain.json",
            media_type="image",
            width=512,
            height=512,
            media_prompt_trace_context=trace_context,
        )


class _FakeVisionLLMService:
    calls = []

    def __init__(self, config=None):
        self.config = dict(config or {})

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(
            {
                "subject_summary": "白色玩偶角色，圆脸，简单服饰",
                "style_summary": "柔和童话绘本风格",
                "color_atmosphere": "浅色暖光",
                "composition_summary": "主体居中",
                "identity_anchors": ["圆脸", "白色服饰"],
                "style_anchors": ["柔和绘本"],
                "negative_constraints": ["避免赛博朋克"],
                "prompt_hint_en": "soft storybook toy character",
                "prompt_hint_zh": "柔和童话绘本风，白色玩偶角色，暖色光照",
                "confidence": 0.9,
                "limitations": [],
            },
            ensure_ascii=False,
        )


class _FakeMediaService(MediaService):
    def __init__(self, config, core=None):
        super().__init__(config, core=core)
        self.captured_workflow_params = None

    def _resolve_workflow(self, *, workflow=None, workflow_domain=None):
        return {
            "key": workflow or "selfhost/image_plain.json",
            "source": "selfhost",
            "path": "/tmp/fake_workflow.json",
        }

    def _build_resolved_workflow_file_trace(self, workflow_info, workflow_input):
        return {}

    async def _execute_workflow(self, workflow_input, workflow_params, workflow_info, **kwargs):
        self.captured_workflow_params = dict(workflow_params)
        return SimpleNamespace(status="completed", images=["result.png"], videos=[], msg="")


def _core(config):
    return SimpleNamespace(
        config=config,
        llm=None,
        tts=None,
        media=None,
        video=None,
    )


def _write_reference_image(path: Path):
    Image.new("RGB", (32, 32), (255, 255, 255)).save(path)
    return path


def test_vision_llm_config_inherits_blank_provider_credentials_from_main_llm():
    resolved = resolve_vision_llm_config(
        PixelleVideoConfig(
            llm={
                "api_key": "main-provider-key",
                "base_url": "https://provider.example/v1",
                "model": "text-model",
            },
            vision_llm={
                "enabled": True,
                "api_key": "",
                "base_url": "",
                "model": "vision-model",
            },
        )
    )

    assert resolved["api_key"] == "main-provider-key"
    assert resolved["base_url"] == "https://provider.example/v1"
    assert resolved["model"] == "vision-model"


def test_vision_llm_config_keeps_explicit_provider_credentials():
    resolved = resolve_vision_llm_config(
        {
            "llm": {
                "api_key": "main-provider-key",
                "base_url": "https://main.example/v1",
            },
            "vision_llm": {
                "enabled": True,
                "api_key": "vision-provider-key",
                "base_url": "https://vision.example/v1",
                "model": "vision-model",
            },
        }
    )

    assert resolved["api_key"] == "vision-provider-key"
    assert resolved["base_url"] == "https://vision.example/v1"


@pytest.mark.asyncio
async def test_reference_image_absent_keeps_pipeline_on_legacy_path(tmp_path, monkeypatch):
    _FakeVisionLLMService.calls = []
    monkeypatch.setattr(linear_module, "VisionLLMService", _FakeVisionLLMService)
    task_dir = tmp_path / "task"
    pipeline = _RecordingReferenceImagePipeline(
        _core({"reference_image": {"enabled": True}, "vision_llm": {"enabled": True, "model": "qwen-vl-max"}})
    )

    result = await pipeline("生成一个儿童故事", task_dir=str(task_dir))

    assert result.status == "ok"
    assert result.ctx.reference_image_asset is None
    assert not (task_dir / "reference_image").exists()
    assert _FakeVisionLLMService.calls == []
    assert result.ctx.params["plan_visuals_seen_reference_patch"] == {}


@pytest.mark.asyncio
async def test_reference_image_disabled_ignores_ref_image_and_continues(tmp_path):
    source_path = _write_reference_image(tmp_path / "reference.png")
    task_dir = tmp_path / "task"
    pipeline = _RecordingReferenceImagePipeline(
        _core({"reference_image": {"enabled": False}, "vision_llm": {"enabled": True, "model": "qwen-vl-max"}})
    )

    result = await pipeline(
        "生成一个儿童故事",
        task_dir=str(task_dir),
        ref_image=str(source_path),
    )

    assert result.status == "ok"
    assert result.ctx.reference_image_asset is None
    assert "ref_image" not in result.ctx.params
    assert not (task_dir / "reference_image").exists()
    assert result.ctx.observability["reference_image"]["status"] == "disabled"


@pytest.mark.asyncio
async def test_reference_image_auto_analysis_skips_when_vision_disabled(tmp_path):
    source_path = _write_reference_image(tmp_path / "reference.png")
    task_dir = tmp_path / "task"
    pipeline = _RecordingReferenceImagePipeline(
        _core(
            {
                "reference_image": {"enabled": True, "analysis_mode": "auto"},
                "vision_llm": {"enabled": False},
            }
        )
    )

    result = await pipeline(
        "生成一个儿童故事",
        task_dir=str(task_dir),
        ref_image=str(source_path),
    )

    assert result.status == "ok"
    assert result.ctx.reference_image_asset is not None
    assert result.ctx.reference_image_analysis_result.status == "skipped"
    assert result.ctx.reference_image_analysis_result.reason == "vision_llm_disabled"
    assert (task_dir / "reference_image" / "asset.json").is_file()
    assert (task_dir / "reference_image" / "analysis.json").is_file()
    assert (task_dir / "reference_image" / "visual_context.json").is_file()
    assert result.ctx.params["plan_visuals_seen_reference_patch"] == {}


@pytest.mark.asyncio
async def test_reference_image_fake_vision_success_reaches_visual_planning_snapshot(tmp_path, monkeypatch):
    _FakeVisionLLMService.calls = []
    monkeypatch.setattr(linear_module, "VisionLLMService", _FakeVisionLLMService)
    source_path = _write_reference_image(tmp_path / "reference.png")
    task_dir = tmp_path / "task"
    pipeline = _RecordingReferenceImagePipeline(
        _core(
            {
                "reference_image": {"enabled": True, "analysis_mode": "auto"},
                "vision_llm": {"enabled": True, "model": "qwen-vl-max"},
            }
        )
    )

    result = await pipeline(
        "生成一个儿童故事",
        task_dir=str(task_dir),
        ref_image=str(source_path),
    )

    assert result.status == "ok"
    assert _FakeVisionLLMService.calls
    assert result.ctx.reference_image_analysis_result.status == "success"
    assert (task_dir / "reference_image" / "analysis.json").is_file()
    assert (task_dir / "reference_image" / "visual_context.json").is_file()
    reference_snapshot = result.ctx.planning_snapshot["reference_image_visual_context"]
    assert reference_snapshot["visual_story_context_patch"]["reference_image"]["enabled"] is True
    assert reference_snapshot["visual_story_context_patch"]["reference_image"]["identity_anchors"] == ["圆脸", "白色服饰"]


@pytest.mark.asyncio
async def test_reference_image_required_workflow_injection_fails_before_media_execution(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        binding_module,
        "get_workflow_capabilities",
        lambda workflow_info: SimpleNamespace(reference_image_param_names=()),
    )
    source_path = _write_reference_image(tmp_path / "reference.png")
    task_dir = tmp_path / "task"
    config = PixelleVideoConfig(
        reference_image={
            "enabled": True,
            "analysis_mode": "off",
            "workflow_injection_mode": "required",
        }
    )
    core = _core(config)
    core.media = _FakeMediaService(config.to_dict(), core=core)
    pipeline = _MediaRequiredPipeline(core)

    with pytest.raises(ValueError, match="reference image workflow injection failed"):
        await pipeline(
            "生成一个儿童故事",
            task_dir=str(task_dir),
            ref_image=str(source_path),
        )

    assert core.media.captured_workflow_params is None


def test_standard_pipeline_syncs_final_reference_visual_context_artifact(tmp_path):
    pipeline = StandardPipeline(_core({"reference_image": {"enabled": True}}))
    ctx = PipelineContext(
        input_text="生成一个儿童故事",
        params={},
        task_dir=str(tmp_path),
    )
    ctx.reference_image_visual_context = ReferenceImageVisualContext(
        enabled=True,
        asset={"sha256": "a" * 64},
        analysis={"status": "success"},
        supplemental_visual_story_context={"reference_image": {"enabled": True}},
    )
    ctx.planning_snapshot = {
        "reference_image_visual_context": {
            "visual_story_context_patch": {
                "reference_image": {
                    "enabled": True,
                    "identity_anchors": ["圆脸", "白色服饰"],
                }
            },
            "merged_ip_profile": {
                "identity_anchors": ["用户锚点", "圆脸", "白色服饰"],
            },
        }
    }

    pipeline._sync_reference_image_visual_context_artifact(ctx)

    artifact = json.loads((tmp_path / "reference_image" / "visual_context.json").read_text(encoding="utf-8"))
    assert artifact["merged_ip_profile"]["identity_anchors"] == ["用户锚点", "圆脸", "白色服饰"]
    assert artifact["supplemental_visual_story_context"]["reference_image"]["identity_anchors"] == ["圆脸", "白色服饰"]
    assert ctx.params["reference_image_visual_context"]["merged_ip_profile"]["identity_anchors"] == [
        "用户锚点",
        "圆脸",
        "白色服饰",
    ]
