import json
from dataclasses import replace
from pathlib import Path

import pytest

import pixelle_video.pipelines.standard as standard_module
from pixelle_video.models.caption_speech_plan import CaptionSpeechPlan
from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    RenderedMediaPrompt,
)
from pixelle_video.models.media import MediaResult
from pixelle_video.models.prompt_plan import PromptPlan, PromptPlanBundle
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionService,
)
from pixelle_video.utils.template_util import get_template_orientation
from tests.support.visual_story import DeterministicFrameVisualPlanLLM


class _FakeRawPayloadStore:
    def __init__(self):
        self.payloads = []

    async def put_json(self, workspace_id, payload):
        storage_key = f"raw-payloads/{workspace_id}/{len(self.payloads) + 1}.json"
        self.payloads.append(
            {
                "workspace_id": workspace_id,
                "storage_key": storage_key,
                "payload": dict(payload),
            }
        )
        return storage_key


class _FakeTraceRepository:
    def __init__(self):
        self.llm_interactions = []

    async def append_llm_interaction(self, workspace_id, trace):
        stored = dict(trace)
        self.llm_interactions.append(
            {
                "workspace_id": workspace_id,
                "trace": stored,
            }
        )
        return stored


class _DummyCore:
    def __init__(self, config=None):
        self.config = config or {"comfyui": {"image": {}, "video": {}}}
        self.llm = DeterministicFrameVisualPlanLLM()
        self.tts = None
        self.media = object()
        self.video = None
        self.raw_payload_store = _FakeRawPayloadStore()
        self.trace_repository = _FakeTraceRepository()


class _RecordingAssetBibleRepository:
    def __init__(self):
        self.load_calls = []
        self.list_scene_cast_calls = []

    async def load_asset_bible(self, workspace_id, asset_bible_id):
        self.load_calls.append((workspace_id, asset_bible_id))
        if asset_bible_id != "bible_demo":
            return None
        return {
            "asset_bible_id": "bible_demo",
            "workspace_id": workspace_id,
            "project_id": "project_1",
            "ip_profiles": [
                {
                    "series_visual_signature_profile_id": "ip_main",
                    "workspace_id": workspace_id,
                    "project_id": "project_1",
                    "name": "正定向导兔",
                    "identity_lock": ["白色卡通兔子"],
                    "identity_anchors": ["蓝色领带"],
                }
            ],
        }

    async def list_scene_casts(self, workspace_id, project_id, asset_bible_id):
        self.list_scene_cast_calls.append((workspace_id, project_id, asset_bible_id))
        return [
            {
                "scene_cast_id": "cast_1",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "storyboard_plan_id": "other_plan",
                "frame_id": "ignored_frame",
                "asset_bible_id": asset_bible_id,
                "metadata": {"ip_presence_type": "absent"},
            },
            {
                "scene_cast_id": "cast_2",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "storyboard_plan_id": self.current_storyboard_plan_id,
                "frame_id": self.current_frame_id,
                "asset_bible_id": asset_bible_id,
                "metadata": {"ip_presence_type": "scene_integrated"},
            },
        ]


class _EmptyIPAssetBibleRepository(_RecordingAssetBibleRepository):
    async def load_asset_bible(self, workspace_id, asset_bible_id):
        payload = await super().load_asset_bible(workspace_id, asset_bible_id)
        if payload is None:
            return None
        payload["ip_profiles"][0]["identity_lock"] = []
        payload["ip_profiles"][0]["identity_anchors"] = []
        return payload


def _plan(source_text="第一句。第二句。", mode="smart"):
    return StoryboardPlan.build(
        mode=mode,
        count_mode="auto",
        requested_scene_count=None,
        source_text=source_text,
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                visual_goal="Show idea one.",
                prompt_intent="Visual metaphor one.",
                source_start=0,
                source_end=4,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="第二句。",
                visual_goal="Show idea two.",
                prompt_intent="Visual metaphor two.",
                source_start=4,
                source_end=8,
            ),
        ],
    )


def _output_gate_contract(
    frame_id: str,
    profile: VisualSignatureProfileSnapshot,
) -> dict:
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": profile.profile_id,
            "series_visual_signature_role": "auto",
        }
    )
    return SeriesVisualSignatureProjectionService().project_frame(
        frame_id=frame_id,
        base_prompt="article chart on a desk",
        frame_context={
            "frame_source_text": "The article chart shows the main relation.",
            "primary_subject": "article chart",
            "world_elements": ["desk"],
            "lighting": "soft light",
        },
        request=request,
        profile=profile,
    ).contract.to_dict()


def _output_gate_trace(
    frame_id: str,
    profile: VisualSignatureProfileSnapshot,
    *,
    positive_prompt: str = "prompt",
    negative_prompt: str = "",
) -> dict:
    contract = _output_gate_contract(frame_id, profile)
    return {
        "contract": contract,
        "final_positive_prompt": positive_prompt,
        "final_negative_prompt": negative_prompt,
        "identity_content_sha256": profile.identity_content_sha256,
        "contract_content_sha256": contract["contract_content_sha256"],
        "contract_version": contract["contract_version"],
    }


def test_write_final_prompt_trace_artifact_uses_plan_frame_ids_and_media_sizes(tmp_path):
    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="Scene one. Scene two.",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="Scene one.",
                visual_goal="Show scene one.",
                prompt_intent="Prompt scene one.",
                frame_id="frame_alpha",
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="Scene two.",
                visual_goal="Show scene two.",
                prompt_intent="Prompt scene two.",
                frame_id="frame_beta",
            ),
        ],
        plan_id="plan_trace_context",
    )
    config = StoryboardConfig(
        media_width=768,
        media_height=512,
        canvas_width=1280,
        canvas_height=720,
        task_id="task_trace_context",
        media_workflow=None,
    )
    ctx = PipelineContext(
        input_text="Scene one. Scene two.",
        params={"mode": "smart", "media_workflow": None},
    )
    ctx.task_id = "task_trace_context"
    ctx.task_dir = str(tmp_path)
    ctx.storyboard_plan = plan
    ctx.config = config
    ctx.storyboard = Storyboard(
        title="Trace context",
        config=config,
        frames=[
            StoryboardFrame(index=0, narration="Scene one.", image_prompt="final prompt one"),
            StoryboardFrame(index=1, narration="Scene two.", image_prompt="final prompt two"),
        ],
    )
    ctx.media_negative_prompt = "no blur"

    class _TraceMedia:
        def resolve_workflow_key(self, *, workflow=None, media_type="image"):
            assert workflow is None
            assert media_type == "image"
            return "selfhost/image_trace_default.json"

    core = _DummyCore()
    core.media = _TraceMedia()
    StandardPipeline(core)._write_final_prompt_trace_artifact(ctx)

    content = (tmp_path / "prompt_traces" / "final_visual_prompts.md").read_text(
        encoding="utf-8"
    )
    assert "Frame ID: frame_alpha" in content
    assert "Frame ID: frame_beta" in content
    assert '"media_width": 768' in content
    assert '"media_height": 512' in content
    assert '"canvas_width": 1280' in content
    assert '"canvas_height": 720' in content
    assert '"requested_media_workflow": null' in content
    assert '"media_workflow": "selfhost/image_trace_default.json"' in content


def test_prompt_plan_resolution_prefers_stable_frame_identity_over_position() -> None:
    plan = _plan()
    target_frame_id = plan.frames[1].frame_id
    prompt_plan = PromptPlan(
        prompt_plan_id="prompt-plan-beta",
        storyboard_plan_id=plan.plan_id,
        frame_id=target_frame_id,
        image_prompt_draft_id="draft-beta",
        prompt_sections={"scene": "stable identity scene"},
        final_prompt="stable identity prompt",
    )
    ctx = PipelineContext(input_text="Scene.", params={})
    ctx.planning_snapshot = {
        "storyboard_generation": plan.to_dict(),
        "prompt_plan_bundle": {"prompt_plans": [prompt_plan.to_dict()]},
    }
    frame = StoryboardFrame(
        index=0,
        frame_id=target_frame_id,
        narration="Scene.",
        image_prompt="stable identity prompt",
    )

    storyboard_id, resolved_frame_id, resolved_plan = StandardPipeline(
        _DummyCore()
    )._resolve_frame_prompt_plan(ctx, frame)

    assert storyboard_id == plan.plan_id
    assert resolved_frame_id == target_frame_id
    assert resolved_plan == prompt_plan


def test_write_series_signature_trace_artifact_preserves_complete_v46_record(
    tmp_path,
) -> None:
    trace = {
        "contract": {
            "schema_version": "v4.6-content-bound-anchor",
            "frame_id": "frame_alpha",
            "entity_placement": {"horizontal_position": "left"},
            "scene_fusion": {"style_relation": "same render style/material"},
        },
        "final_positive_prompt": "exact positive prompt",
        "final_negative_prompt": "exact negative prompt",
        "identity_content_sha256": "a" * 64,
        "contract_content_sha256": "b" * 64,
        "contract_version": "final_visual_prompt_contract.v4_6",
    }
    ctx = PipelineContext(input_text="Scene.", params={})
    ctx.task_id = "task-v46-trace"
    ctx.task_dir = str(tmp_path)
    ctx.planning_snapshot = {
        "series_visual_signature_trace_by_frame": {"frame_alpha": trace}
    }

    StandardPipeline(_DummyCore())._write_series_visual_signature_trace_artifacts(ctx)

    artifact_path = (
        tmp_path
        / "prompt_traces"
        / "series_visual_signature"
        / "series_visual_signature_v46_contract_frame_001.json"
    )
    assert artifact_path.exists()
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == trace
    prompt_path = (
        tmp_path
        / "prompt_traces"
        / "series_visual_signature"
        / "final_integrated_prompt_frame_001.txt"
    )
    assert prompt_path.read_text(encoding="utf-8") == "exact positive prompt"


def test_standard_pipeline_uses_single_pass_without_output_inspection(
    tmp_path,
) -> None:
    plan = _plan()
    frame_id = plan.frames[0].frame_id
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        core_identity_traits=("black spots", "black sunglasses"),
    )
    ctx = PipelineContext(
        input_text="Scene.",
        params={
            "series_visual_signature_output_validation_mode": "required",
            "series_visual_signature_output_max_attempts": 1,
        },
    )
    ctx.task_id = "task-output-gate"
    ctx.task_dir = str(tmp_path)
    ctx.storyboard_plan = plan
    config = StoryboardConfig(
        task_id=ctx.task_id,
        media_width=1024,
        media_height=1024,
    )
    frame = StoryboardFrame(
        index=0,
        frame_id=frame_id,
        narration="Scene.",
        image_prompt="prompt",
    )
    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"image-bytes")
    frame.image_path = str(image_path)
    frame.media_type = "image"
    ctx.storyboard = Storyboard(title="Test", config=config, frames=[frame])
    ctx.planning_snapshot = {
        "series_visual_signature_trace_by_frame": {
            frame_id: _output_gate_trace(frame_id, profile)
        }
    }

    pipeline = StandardPipeline(_DummyCore(config={"vision_llm": {"enabled": False}}))
    pipeline._configure_series_visual_signature_single_pass_policy(
        ctx,
        media_type="image",
    )

    assert ctx.generated_media_validator is None
    assert ctx.media_generation_max_attempts == 1
    assert ctx.runtime_resources == []
    assert ctx.params["series_visual_signature_output_validation_mode"] == "off"
    assert ctx.params["series_visual_signature_output_max_attempts"] == 1
    policy = ctx.planning_snapshot["series_visual_signature_single_pass_policy"]
    assert policy["mode"] == "pre_generation_only"
    assert policy["post_generation_vision_validation_enabled"] is False
    assert policy["prompt_repair_enabled"] is False


def test_visual_anchor_passthrough_has_no_post_generation_local_validator(
    tmp_path,
) -> None:
    frame_id = "frame-raw-passthrough"
    ctx = PipelineContext(input_text="Scene.", params={})
    ctx.task_id = "task-raw-passthrough"
    ctx.task_dir = str(tmp_path)
    config = StoryboardConfig(
        task_id=ctx.task_id,
        media_width=1024,
        media_height=1024,
    )
    ctx.storyboard = Storyboard(
        title="Test",
        config=config,
        frames=[
            StoryboardFrame(
                index=0,
                frame_id=frame_id,
                narration="Scene.",
                image_prompt="   \n",
            )
        ],
    )
    ctx.planning_snapshot = {
        "visual_anchor_two_stage": {"frames": [{"frame_id": frame_id}]}
    }

    StandardPipeline(_DummyCore())._configure_series_visual_signature_single_pass_policy(
        ctx,
        media_type="image",
    )

    assert ctx.generated_media_validator is None
    assert ctx.media_generation_max_attempts == 1
    policy = ctx.planning_snapshot["visual_anchor_two_stage_passthrough_policy"]
    assert policy["model_output_passthrough_enabled"] is True
    assert policy["post_generation_local_validation_enabled"] is False
    assert policy["vision_model_call_enabled"] is False
    assert "visual_anchor_rendered_output_policy" not in ctx.planning_snapshot


def test_output_validation_rejects_missing_runtime_frame_identity_before_media(
    tmp_path,
) -> None:
    plan = _plan()
    frame_id = plan.frames[0].frame_id
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        core_identity_traits=("black spots", "black sunglasses"),
    )
    ctx = PipelineContext(input_text="Scene.", params={})
    ctx.task_id = "task-output-gate-missing-runtime-id"
    ctx.task_dir = str(tmp_path)
    ctx.storyboard_plan = plan
    ctx.storyboard = Storyboard(
        title="Test",
        config=StoryboardConfig(
            task_id=ctx.task_id,
            media_width=1024,
            media_height=1024,
        ),
        frames=[StoryboardFrame(index=0, narration="Scene.", image_prompt="prompt")],
    )
    ctx.planning_snapshot = {
        "series_visual_signature_trace_by_frame": {
            frame_id: _output_gate_trace(frame_id, profile)
        }
    }

    with pytest.raises(ValueError, match="stable frame_id"):
        StandardPipeline(_DummyCore())._configure_series_visual_signature_single_pass_policy(
            ctx,
            media_type="image",
        )


def test_output_validation_rejects_contract_identity_mismatch_before_media(
    tmp_path,
) -> None:
    plan = _plan()
    frame_id = plan.frames[0].frame_id
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        core_identity_traits=("black spots", "black sunglasses"),
    )
    ctx = PipelineContext(input_text="Scene.", params={})
    ctx.task_id = "task-output-gate-contract-id-mismatch"
    ctx.task_dir = str(tmp_path)
    ctx.storyboard = Storyboard(
        title="Test",
        config=StoryboardConfig(
            task_id=ctx.task_id,
            media_width=1024,
            media_height=1024,
        ),
        frames=[
            StoryboardFrame(
                index=0,
                frame_id=frame_id,
                narration="Scene.",
                image_prompt="prompt",
            )
        ],
    )
    ctx.planning_snapshot = {
        "series_visual_signature_trace_by_frame": {
            frame_id: _output_gate_trace("different-frame-id", profile)
        }
    }

    with pytest.raises(ValueError, match="trace key must match contract frame_id"):
        StandardPipeline(_DummyCore())._configure_series_visual_signature_single_pass_policy(
            ctx,
            media_type="image",
        )


def test_output_validation_rejects_prompt_lineage_drift_before_media(tmp_path) -> None:
    plan = _plan()
    frame_id = plan.frames[0].frame_id
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        core_identity_traits=("black spots", "black sunglasses"),
    )
    ctx = PipelineContext(input_text="Scene.", params={})
    ctx.task_id = "task-output-gate-prompt-drift"
    ctx.task_dir = str(tmp_path)
    ctx.storyboard = Storyboard(
        title="Test",
        config=StoryboardConfig(
            task_id=ctx.task_id,
            media_width=1024,
            media_height=1024,
        ),
        frames=[
            StoryboardFrame(
                index=0,
                frame_id=frame_id,
                narration="Scene.",
                image_prompt="runtime prompt changed after trace creation",
            )
        ],
    )
    ctx.planning_snapshot = {
        "series_visual_signature_trace_by_frame": {
            frame_id: _output_gate_trace(frame_id, profile)
        }
    }

    with pytest.raises(ValueError, match="trace prompt must match"):
        StandardPipeline(_DummyCore())._configure_series_visual_signature_single_pass_policy(
            ctx,
            media_type="image",
        )


def test_strict_signature_single_pass_does_not_require_vision_model(
    tmp_path,
) -> None:
    plan = _plan()
    frame_id = plan.frames[0].frame_id
    ctx = PipelineContext(
        input_text="Scene.",
        params={"series_visual_signature_enforcement": "strict"},
    )
    ctx.task_id = "task-output-gate-strict"
    ctx.task_dir = str(tmp_path)
    ctx.storyboard_plan = plan
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        core_identity_traits=("black spots", "black sunglasses"),
    )
    ctx.storyboard = Storyboard(
        title="Test",
        config=StoryboardConfig(
            task_id=ctx.task_id,
            media_width=1024,
            media_height=1024,
        ),
        frames=[
            StoryboardFrame(
                index=0,
                frame_id=frame_id,
                narration="Scene.",
                image_prompt="prompt",
            )
        ],
    )
    ctx.planning_snapshot = {
        "series_visual_signature_trace_by_frame": {
            frame_id: _output_gate_trace(frame_id, profile)
        }
    }

    StandardPipeline(
        _DummyCore(config={"vision_llm": {"enabled": False}})
    )._configure_series_visual_signature_single_pass_policy(
        ctx,
        media_type="image",
    )

    assert ctx.generated_media_validator is None
    assert ctx.media_generation_max_attempts == 1


@pytest.mark.asyncio
async def test_generate_content_fixed_defaults_to_smart_storyboard(monkeypatch):
    captured = {}
    plan = _plan()

    async def fake_storyboard_generate(self, **kwargs):
        captured.update(kwargs)
        await kwargs["trace_recorder"].record_interaction(
            context=replace(kwargs["trace_context"], stage="smart_storyboard_generation"),
            provider="fake",
            model="fake-model",
            request_payload={"prompt": "storyboard"},
            response_payload={"frames": []},
            status="success",
        )
        return plan

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService.generate",
        fake_storyboard_generate,
    )

    ctx = PipelineContext(input_text="第一句。第二句。", params={"mode": "fixed"})
    ctx.task_id = "task-fixed-smart-storyboard"
    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.source_text == "第一句。第二句。"
    assert ctx.storyboard_plan is plan
    assert isinstance(ctx.caption_speech_plan, CaptionSpeechPlan)
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "第一句。",
        "第二句。",
    ]
    assert captured["source_text"] == "第一句。第二句。"
    assert captured["storyboard_mode"] == "smart"
    assert captured["storyboard_count_mode"] == "auto"
    assert captured["storyboard_scene_count"] is None
    assert ctx.llm_trace_refs[0]["stage"] == "smart_storyboard_generation"


@pytest.mark.asyncio
async def test_generate_content_fixed_punctuation_uses_storyboard_generation_service():
    ctx = PipelineContext(
        input_text="第一段，继续；结束。",
        params={"mode": "fixed", "storyboard_mode": "punctuation"},
    )

    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.source_text == "第一段，继续；结束。"
    assert ctx.storyboard_plan.mode.value == "punctuation"
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "第一段，",
        "继续；",
        "结束。",
    ]


@pytest.mark.asyncio
async def test_generate_content_deterministic_modes_default_to_request_level_max_scene_count():
    ctx = PipelineContext(
        input_text="first, second.",
        params={"mode": "fixed", "storyboard_mode": "punctuation"},
    )
    core = _DummyCore(
        {
            "storyboard": {"min_scene_count": 1, "max_scene_count": 1},
            "comfyui": {"image": {}, "video": {}},
        }
    )

    await StandardPipeline(core).generate_content(ctx)

    assert ctx.storyboard_plan.mode.value == "punctuation"
    assert [frame.source_text for frame in ctx.storyboard_plan.frames] == [
        "first,",
        "second.",
    ]


@pytest.mark.asyncio
async def test_generate_content_respects_explicit_deterministic_max_scene_count():
    ctx = PipelineContext(
        input_text="first, second.",
        params={
            "mode": "fixed",
            "storyboard_mode": "punctuation",
            "storyboard_max_scene_count": 1,
        },
    )

    with pytest.raises(ValueError, match="too many storyboard frames"):
        await StandardPipeline(_DummyCore()).generate_content(ctx)


@pytest.mark.asyncio
async def test_generate_content_fixed_sentence_uses_storyboard_generation_service():
    ctx = PipelineContext(
        input_text="第一句。第二句！",
        params={"mode": "fixed", "storyboard_mode": "sentence"},
    )

    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.storyboard_plan.mode.value == "sentence"
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "第一句。",
        "第二句！",
    ]


@pytest.mark.asyncio
async def test_generate_content_generate_mode_uses_complete_source_text(monkeypatch):
    captured = {}
    plan = _plan(source_text="第一句。第二句。")

    async def fake_script_generate(self, **kwargs):
        captured["script"] = kwargs
        return "第一句。第二句。"

    async def fake_storyboard_generate(self, **kwargs):
        captured["storyboard"] = kwargs
        return plan

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ScriptGenerationService.generate",
        fake_script_generate,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService.generate",
        fake_storyboard_generate,
    )

    ctx = PipelineContext(
        input_text="自律主题",
        params={"mode": "generate", "script_length_mode": "custom", "script_target_words": 180},
    )
    ctx.task_id = "task-generate-complete-source"
    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.source_text == "第一句。第二句。"
    assert ctx.storyboard_plan is plan
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "第一句。",
        "第二句。",
    ]
    assert captured["script"]["topic"] == "自律主题"
    assert captured["script"]["script_length_mode"] == "custom"
    assert captured["script"]["script_target_words"] == 180
    assert captured["storyboard"]["source_text"] == "第一句。第二句。"


@pytest.mark.asyncio
async def test_plan_visuals_uses_image_prompt_composer(monkeypatch):
    captured = {}

    async def fake_compose(self, **kwargs):
        captured.update(kwargs)
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt="bad anatomy",
            resolved_style=None,
            planning_snapshot={"storyboard_generation": kwargs["storyboard_plan"].to_dict()},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.task_id = "task-1"
    ctx.storyboard_plan = _plan()
    ctx.llm_trace_refs = [
        {"trace_id": "trace_smart_storyboard", "stage": "smart_storyboard_generation"}
    ]

    await StandardPipeline(_DummyCore()).plan_visuals(ctx)

    assert captured["storyboard_plan"] is ctx.storyboard_plan
    assert captured["upstream_llm_trace_refs"] == ctx.llm_trace_refs
    assert ctx.image_prompts == ["prompt one", "prompt two"]
    assert ctx.media_negative_prompt == "bad anatomy"
    assert ctx.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 2


@pytest.mark.asyncio
async def test_plan_visuals_passes_ip_controls_to_image_prompt_composer(monkeypatch):
    captured = {}

    async def fake_compose(self, **kwargs):
        captured.update(kwargs)
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={"storyboard_generation": kwargs["storyboard_plan"].to_dict()},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    plan = _plan()
    repository = _RecordingAssetBibleRepository()
    repository.current_storyboard_plan_id = plan.plan_id
    repository.current_frame_id = plan.frames[0].frame_id
    core = _DummyCore()
    core.asset_bible_repository = repository
    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "media_workflow": "selfhost/image_custom.json",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-ip-controls"
    ctx.storyboard_plan = plan

    await StandardPipeline(core).plan_visuals(ctx)

    assert repository.load_calls == [("workspace_1", "bible_demo")]
    assert repository.list_scene_cast_calls == [("workspace_1", "project_1", "bible_demo")]
    assert captured["series_visual_signature_enabled"] is True
    assert captured["ip_profile"].series_visual_signature_profile_id == "ip_main"
    scene_casts_by_frame = captured["scene_casts_by_frame"]
    assert list(scene_casts_by_frame) == [plan.frames[0].frame_id]
    assert scene_casts_by_frame[plan.frames[0].frame_id]["metadata"]["ip_presence_type"] == "scene_integrated"
    assert ctx.observability["visual_anchor_visual_planning"] == {
        "schema_version": "visual_anchor_visual_planning.v5",
        "route_model_call_count": 0,
        "frame_planning_model_call_count": 0,
        "prompt_chain": "content_raw_response_then_fusion_raw_response",
        "minimum_prompt_model_calls_per_frame": 2,
        "image_generation_attempts_per_frame": 1,
        "model_output_passthrough_enabled": True,
        "post_generation_local_validation_enabled": False,
        "post_generation_local_content_validation_enabled": False,
    }


@pytest.mark.asyncio
async def test_visual_anchor_preflight_finishes_before_storyboard_generation() -> None:
    repository = _RecordingAssetBibleRepository()
    core = _DummyCore()
    core.asset_bible_repository = repository
    ctx = PipelineContext(
        input_text="topic",
        params={
            "frame_template": "1080x1920/image_default.html",
            "media_workflow": "selfhost/image_custom.json",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
            "series_visual_signature_output_max_attempts": 3,
        },
    )

    pipeline = StandardPipeline(core)
    await pipeline.prepare_reference_image(ctx)
    await pipeline._preflight_series_visual_signature(ctx)

    assert ctx.storyboard_plan is None
    assert repository.load_calls == [("workspace_1", "bible_demo")]
    assert ctx.params["series_visual_signature_output_max_attempts"] == 1
    assert ctx.params["series_visual_signature_output_validation_mode"] == "off"
    assert ctx.observability["visual_anchor_preflight"]["model_call_count"] == 0


@pytest.mark.asyncio
async def test_reference_conditioned_frame_uses_registered_seed_without_retry_request(
    monkeypatch,
    tmp_path,
) -> None:
    captured = {}

    class MediaCore:
        async def media(self, **kwargs):
            captured.update(kwargs)
            return MediaResult(
                media_type="image",
                url="https://example.com/frame.png",
            )

    processor = FrameProcessor(MediaCore())

    async def fake_download_media(*_args, **_kwargs):
        return str(tmp_path / "frame.png")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)
    frame = StoryboardFrame(
        index=0,
        frame_id="frame-seeded",
        narration="scene",
        image_prompt="prompt",
        generation_seed=123456,
    )
    config = StoryboardConfig(
        task_id="task-seeded",
        media_width=1024,
        media_height=1024,
        media_workflow="selfhost/image_reference.json",
        frame_template="1080x1920/image_default.html",
        reference_image_workflow_injection_mode="required",
    )

    await processor._step_generate_media(frame, config)

    assert captured["seed"] == 123456
    assert captured["reference_image_workflow_injection_mode"] == "required"
    assert "visual_anchor_generation_request" not in captured


@pytest.mark.asyncio
async def test_default_z_image_visual_anchor_keeps_text_workflow_without_reference(
    monkeypatch,
):
    captured = {}

    async def fake_compose(self, **kwargs):
        captured.update(kwargs)
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={
                "storyboard_generation": kwargs["storyboard_plan"].to_dict()
            },
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )
    monkeypatch.setattr(
        standard_module,
        "_validate_single_pass_z_image_signature_batch",
        lambda batch: batch,
    )

    workflow_key = "selfhost/image_z_image_turbo_gguf.json"

    class WorkflowMedia:
        def _resolve_workflow(self, *, workflow, workflow_domain):
            assert workflow_domain == "image"
            assert workflow == workflow_key
            return {
                "key": workflow_key,
                "source": "selfhost",
                "path": str(
                    Path("workflows/selfhost/image_z_image_turbo_gguf.json").resolve()
                ),
            }

    plan = _plan()
    repository = _RecordingAssetBibleRepository()
    repository.current_storyboard_plan_id = plan.plan_id
    repository.current_frame_id = plan.frames[0].frame_id
    core = _DummyCore()
    core.media = WorkflowMedia()
    core.asset_bible_repository = repository
    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "media_workflow": workflow_key,
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-z-image-text-anchor"
    ctx.storyboard_plan = plan

    await StandardPipeline(core).plan_visuals(ctx)

    assert captured["visual_anchor_reference_conditioning_enabled"] is False
    assert captured["ip_profile"].series_visual_signature_profile_id == "ip_main"
    assert ctx.params["media_workflow"] == workflow_key
    assert "reference_image_workflow_injection_mode" not in ctx.params


@pytest.mark.asyncio
async def test_explicit_reference_workflow_requires_reference_asset_before_compose(
    monkeypatch,
):
    async def fake_compose(self, **_kwargs):
        raise AssertionError("reference asset validation must run before prompt compose")

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )
    workflow_key = "selfhost/image_z_image_turbo_gguf_reference.json"

    class WorkflowMedia:
        def _resolve_workflow(self, *, workflow, workflow_domain):
            assert workflow_domain == "image"
            assert workflow == workflow_key
            return {
                "key": workflow_key,
                "source": "selfhost",
                "path": str(
                    Path(
                        "workflows/selfhost/image_z_image_turbo_gguf_reference.json"
                    ).resolve()
                ),
            }

    plan = _plan()
    repository = _RecordingAssetBibleRepository()
    repository.current_storyboard_plan_id = plan.plan_id
    repository.current_frame_id = plan.frames[0].frame_id
    core = _DummyCore()
    core.media = WorkflowMedia()
    core.asset_bible_repository = repository
    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "media_workflow": workflow_key,
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-z-image-reference-anchor"
    ctx.storyboard_plan = plan

    with pytest.raises(ValueError, match="selected reference-image workflow"):
        await StandardPipeline(core).plan_visuals(ctx)


@pytest.mark.asyncio
async def test_standard_z_image_request_matches_prompt_plan_and_v46_trace(
    monkeypatch,
    tmp_path,
) -> None:
    adapter_calls = []
    original_adapter = standard_module.project_z_image_prompt_bundle

    def recording_adapter(**kwargs):
        result = original_adapter(**kwargs)
        adapter_calls.append(result)
        return result

    async def fake_compose(self, **kwargs):
        plan = kwargs["storyboard_plan"]
        rendered = []
        traces = {}
        prompts = []
        for index, frame in enumerate(plan.frames, start=1):
            negative = f"final V4.6 negative for {frame.frame_id}"
            sections = {
                "main_content": f"main {index}",
                "identity": "fixed identity",
                "participation": "guide operates the content subject",
                "instance_control": "single anchor instance",
                "placement": "left midground small beside target",
                "scene_fusion": "shared perspective light shadow style",
                "style": "editorial diagram",
            }
            prompt = ". ".join(sections.values())
            contract = FinalVisualPromptContract(
                scene=sections["main_content"],
                composition=sections["placement"],
                style_assignment=sections["style"],
                character_layer_style=sections["identity"],
                world_layer_style=sections["scene_fusion"],
                    integration_priority=sections["participation"],
            )
            rendered.append(
                RenderedMediaPrompt(
                    prompt=prompt,
                    negative_prompt=negative,
                    prompt_contract=contract,
                    renderer_id="final_visual_prompt_compiler",
                    renderer_version="v4.6",
                    metadata={
                        "series_visual_signature_v46": {
                            "prompt_sections": sections,
                            "identity_content_sha256": "a" * 64,
                            "contract_content_sha256": "b" * 64,
                            "contract_version": "final_visual_prompt_contract.v4_6",
                        }
                    },
                )
            )
            prompts.append(prompt)
            traces[frame.frame_id] = {
                "contract": {
                    "contract_version": "final_visual_prompt_contract.v4_6",
                    "contract_content_sha256": "b" * 64,
                    "series_visual_signature": {
                        "profile": {"identity_content_sha256": "a" * 64}
                    },
                },
                "final_positive_prompt": prompt,
                "final_negative_prompt": negative,
                "identity_content_sha256": "a" * 64,
                "contract_content_sha256": "b" * 64,
                "contract_version": "final_visual_prompt_contract.v4_6",
            }
        prompt_plan_bundle = build_prompt_plan_bundle(
            storyboard_plan=plan,
            rendered_prompts=rendered,
        )
        return StyledImagePromptBatch(
            prompts=prompts,
            negative_prompt=", ".join(item.negative_prompt for item in rendered),
            resolved_style=None,
            planning_snapshot={
                "storyboard_generation": plan.to_dict(),
                "series_visual_signature_trace_by_frame": traces,
            },
            prompt_plan_bundle=prompt_plan_bundle,
            rendered_prompts=rendered,
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )
    monkeypatch.setattr(
        standard_module,
        "project_z_image_prompt_bundle",
        recording_adapter,
    )

    plan = _plan()
    repository = _RecordingAssetBibleRepository()
    repository.current_storyboard_plan_id = plan.plan_id
    repository.current_frame_id = plan.frames[0].frame_id
    core = _DummyCore()
    core.asset_bible_repository = repository
    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "media_workflow": "selfhost/image_z.json",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-z-image-v46"
    ctx.title = "Z-Image V4.6 integration"
    ctx.storyboard_plan = plan

    pipeline = StandardPipeline(core)
    await pipeline.plan_visuals(ctx)
    await pipeline.initialize_storyboard(ctx)

    assert len(adapter_calls) == 2
    assert all(call["render_config"] == {} for call in adapter_calls)
    prompt_plan = ctx.prompt_plan_bundle.prompt_plans[0]
    trace = ctx.planning_snapshot["series_visual_signature_trace_by_frame"][
        prompt_plan.frame_id
    ]
    assert trace["adapter"] == {
        "provider": "z_image",
        "validated": True,
        "capabilities": ["positive_prompt", "negative_prompt"],
    }

    captured_request = {}

    class _MediaCore:
        async def media(self, **kwargs):
            captured_request.update(kwargs)
            return MediaResult(
                media_type="image",
                url="https://example.com/frame.png",
            )

    processor = FrameProcessor(_MediaCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.png")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)
    ctx.config.media_prompt_trace_context = {
        "artifact_path": str(tmp_path / "prompt_traces" / "final_visual_prompts.md"),
        "task_root": str(tmp_path),
        "task_id": ctx.task_id,
        "workflow": ctx.config.media_workflow,
        "workflow_input": ctx.config.media_workflow,
        "requested_workflow": ctx.config.media_workflow,
        "media_type": "image",
        "frame_ids_by_index": {"0": prompt_plan.frame_id},
    }
    ctx.config.media_prompt_trace_context["frame_ids_by_index"]["0"] = (
        "legacy-positional-id-must-not-win"
    )
    await processor._step_generate_media(ctx.storyboard.frames[0], ctx.config)

    assert captured_request["prompt"] == prompt_plan.final_prompt
    assert captured_request["prompt"] == trace["final_positive_prompt"]
    assert captured_request["negative_prompt"] == prompt_plan.final_negative_prompt
    assert captured_request["negative_prompt"] == trace["final_negative_prompt"]
    assert (
        captured_request["media_prompt_trace_context"]["frame_id"]
        == ctx.storyboard.frames[0].frame_id
        == prompt_plan.frame_id
    )
    for unsupported in ("bbox", "mask", "depth", "pose"):
        assert unsupported not in captured_request


@pytest.mark.asyncio
async def test_plan_visuals_rejects_enabled_ip_without_identity_anchors(monkeypatch):
    async def fake_compose(self, **_kwargs):
        raise AssertionError("IP readiness must be checked before prompt compose")

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    plan = _plan()
    repository = _EmptyIPAssetBibleRepository()
    repository.current_storyboard_plan_id = plan.plan_id
    repository.current_frame_id = plan.frames[0].frame_id
    core = _DummyCore()
    core.asset_bible_repository = repository
    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-ip-empty-anchors"
    ctx.storyboard_plan = plan

    with pytest.raises(ValueError, match="身份锚点|identity anchors"):
        await StandardPipeline(core).plan_visuals(ctx)


@pytest.mark.asyncio
async def test_plan_visuals_rejects_enabled_ip_without_asset_repository(monkeypatch):
    async def fake_compose(self, **_kwargs):
        raise AssertionError("IP resource loading must happen before prompt compose")

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-ip-missing-repository"
    ctx.storyboard_plan = _plan()

    with pytest.raises(ValueError, match="asset_bible_repository"):
        await StandardPipeline(_DummyCore()).plan_visuals(ctx)


@pytest.mark.asyncio
async def test_plan_visuals_persists_prompt_plan_bundle_to_repository(monkeypatch):
    class RecordingPromptPlanRepository:
        def __init__(self):
            self.saved_bundles = []

        async def save_prompt_plan_bundle(self, workspace_id, bundle):
            self.saved_bundles.append((workspace_id, dict(bundle)))
            return dict(bundle)

        async def load_prompt_plans_by_storyboard(self, workspace_id, storyboard_id):
            return []

        async def mark_prompt_plan_stale(self, workspace_id, prompt_plan_id, reason=None):
            return {"prompt_plan_id": prompt_plan_id}

    async def fake_compose(self, **kwargs):
        plan = kwargs["storyboard_plan"]
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={
                "storyboard_generation": plan.to_dict(),
                "prompt_plan_bundle_ref": {
                    "storyboard_plan_id": plan.plan_id,
                    "prompt_plan_count": 2,
                    "image_prompt_draft_count": 2,
                },
            },
            prompt_plan_bundle=PromptPlanBundle.from_dict(
                {
                    "storyboard_plan_id": plan.plan_id,
                    "image_prompt_drafts": [
                        {
                            "image_prompt_draft_id": "draft_frame_1",
                            "storyboard_plan_id": plan.plan_id,
                            "frame_id": plan.frames[0].frame_id,
                            "prompt_text": "prompt one",
                            "source_trace_id": None,
                            "metadata": {"frame_index": 1},
                        },
                        {
                            "image_prompt_draft_id": "draft_frame_2",
                            "storyboard_plan_id": plan.plan_id,
                            "frame_id": plan.frames[1].frame_id,
                            "prompt_text": "prompt two",
                            "source_trace_id": None,
                            "metadata": {"frame_index": 2},
                        },
                    ],
                    "prompt_plans": [
                        {
                            "prompt_plan_id": "prompt_plan_frame_1",
                            "storyboard_plan_id": plan.plan_id,
                            "frame_id": plan.frames[0].frame_id,
                            "image_prompt_draft_id": "draft_frame_1",
                            "prompt_sections": {"generated_prompt": "prompt one"},
                            "final_prompt": "prompt one",
                            "source_trace_id": None,
                            "character_ids": [],
                            "scene_id": None,
                            "prop_ids": [],
                            "style_id": None,
                            "metadata": {"frame_index": 1},
                        },
                        {
                            "prompt_plan_id": "prompt_plan_frame_2",
                            "storyboard_plan_id": plan.plan_id,
                            "frame_id": plan.frames[1].frame_id,
                            "image_prompt_draft_id": "draft_frame_2",
                            "prompt_sections": {"generated_prompt": "prompt two"},
                            "final_prompt": "prompt two",
                            "source_trace_id": None,
                            "character_ids": [],
                            "scene_id": None,
                            "prop_ids": [],
                            "style_id": None,
                            "metadata": {"frame_index": 2},
                        },
                    ],
                    "source_trace_id": None,
                    "metadata": {},
                }
            ),
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    prompt_repository = RecordingPromptPlanRepository()
    core = _DummyCore()
    core.prompt_plan_repository = prompt_repository
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "frame_template": "1080x1920/image_default.html",
            "workspace_id": "workspace_demo",
        },
    )
    ctx.task_id = "task-persist-prompt-plan"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(core).plan_visuals(ctx)

    assert len(prompt_repository.saved_bundles) == 1
    workspace_id, saved_bundle = prompt_repository.saved_bundles[0]
    assert workspace_id == "workspace_demo"
    assert saved_bundle == ctx.prompt_plan_bundle.to_dict()
    assert saved_bundle["prompt_plans"][0]["frame_id"] == ctx.storyboard_plan.frames[0].frame_id
    assert "prompt_plan_bundle" not in ctx.planning_snapshot
    assert ctx.planning_snapshot["prompt_plan_bundle_ref"] == {
        "storyboard_plan_id": ctx.storyboard_plan.plan_id,
        "prompt_plan_count": 2,
        "image_prompt_draft_count": 2,
    }


@pytest.mark.asyncio
async def test_plan_visuals_defaults_template_to_canvas_orientation(monkeypatch):
    captured_resolver = {}

    def fake_resolve_template(template_type, orientation):
        captured_resolver.update(
            {
                "template_type": template_type,
                "orientation": orientation,
            }
        )
        return "1920x1080/image_landscape_minimal.html"

    async def fake_compose(self, **kwargs):
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={"storyboard_generation": kwargs["storyboard_plan"].to_dict()},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.resolve_default_template_for_type_and_orientation",
        fake_resolve_template,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
        },
    )
    ctx.task_id = "task-plan-visuals-default-template"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(_DummyCore()).plan_visuals(ctx)

    assert captured_resolver == {
        "template_type": "image",
        "orientation": "landscape",
    }
    assert ctx.image_prompts == ["prompt one", "prompt two"]


@pytest.mark.asyncio
async def test_plan_visuals_builds_article_concretization_plans_for_prompt_composer(
    monkeypatch,
):
    captured = {}

    async def fake_compose(self, **kwargs):
        captured.update(kwargs)
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={"storyboard_generation": kwargs["storyboard_plan"].to_dict()},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "article_concretization_enabled": True,
            "cognitive_anchor_kind": "causal_mechanism",
            "explanation_diagram_grammar": "process_flow",
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["Cause", "Effect"],
            "diagram_user_intent_hint": "make the feedback loop visible",
        },
    )
    ctx.task_id = "task-article-concretization-plan-visuals"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(_DummyCore()).plan_visuals(ctx)

    article_plans = captured["article_concretization_plans"]
    assert len(article_plans) == 2
    assert article_plans[0].request.enabled is True
    assert article_plans[0].diagram.visible_text.allowed_visible_text == (
        "Cause",
        "Effect",
    )
    assert any(
        "make the feedback loop visible" in rule
        for rule in article_plans[0].diagram.composition_rules
    )


@pytest.mark.asyncio
async def test_static_template_skips_media_but_keeps_storyboard_plan(monkeypatch):
    monkeypatch.setattr("pixelle_video.pipelines.standard.get_template_type", lambda template_name: "static")

    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={"frame_template": "1080x1920/default.html"},
    )
    ctx.task_id = "task-static"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(_DummyCore()).plan_visuals(ctx)

    assert ctx.image_prompts == [None, None]
    assert ctx.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 2


@pytest.mark.asyncio
async def test_generate_content_builds_caption_speech_plan_from_source_not_storyboard_frames(monkeypatch):
    source_text = "Original wording, untouched."
    storyboard_plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text=source_text,
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text=source_text,
                visual_goal="Show the original idea.",
                prompt_intent="Visualize the unchanged script.",
                source_start=0,
                source_end=len(source_text),
            )
        ],
    )

    async def fake_script_generate(self, **kwargs):
        return source_text

    async def fake_storyboard_generate(self, **kwargs):
        return storyboard_plan

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ScriptGenerationService.generate",
        fake_script_generate,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService.generate",
        fake_storyboard_generate,
    )

    ctx = PipelineContext(input_text="topic", params={"mode": "generate"})
    ctx.task_id = "task-caption-source"
    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.caption_speech_plan.source_text == source_text
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "Original wording,",
        "untouched.",
    ]
    assert not hasattr(ctx.storyboard_plan.frames[0], "narration_text")


@pytest.mark.asyncio
async def test_initialize_storyboard_defaults_template_to_canvas_orientation():
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
        },
    )
    ctx.task_id = "task-size-default-template"
    ctx.title = "Size default template"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert (ctx.config.canvas_width, ctx.config.canvas_height) == (1280, 720)
    assert ctx.config.video_orientation == "landscape"
    assert get_template_orientation(ctx.config.frame_template) == "landscape"
    assert [frame.index for frame in ctx.storyboard.frames] == [0, 1]
    assert [frame.frame_id for frame in ctx.storyboard.frames] == [
        plan_frame.frame_id for plan_frame in ctx.storyboard_plan.frames
    ]


@pytest.mark.asyncio
async def test_initialize_storyboard_defaults_template_to_explicit_canvas_orientation():
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 768,
            "media_height": 768,
        },
    )
    ctx.task_id = "task-explicit-canvas-default-template"
    ctx.title = "Explicit canvas default template"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert (ctx.config.canvas_width, ctx.config.canvas_height) == (1080, 1920)
    assert get_template_orientation(ctx.config.frame_template) == "portrait"


@pytest.mark.asyncio
async def test_initialize_storyboard_uses_explicit_template_orientation_when_size_unset():
    ctx = PipelineContext(
        input_text="first. second.",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.task_id = "task-template-derived-size"
    ctx.title = "Template derived size"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert ctx.config.video_orientation == "portrait"
    assert (ctx.config.canvas_width, ctx.config.canvas_height) == (1080, 1920)
    assert ctx.config.frame_template == "1080x1920/image_default.html"


@pytest.mark.asyncio
async def test_initialize_storyboard_preserves_compatible_explicit_template():
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "frame_template": "1920x1080/image_landscape_minimal.html",
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
        },
    )
    ctx.task_id = "task-explicit-template"
    ctx.title = "Explicit template"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert ctx.config.frame_template == "1920x1080/image_landscape_minimal.html"


@pytest.mark.asyncio
async def test_initialize_storyboard_rejects_template_canvas_orientation_mismatch():
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "frame_template": "1080x1920/image_default.html",
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
        },
    )
    ctx.task_id = "task-mismatched-explicit-template"
    ctx.title = "Mismatched explicit template"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    with pytest.raises(ValueError, match="Template orientation"):
        await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)
