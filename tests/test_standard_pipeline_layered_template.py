import pytest

from pixelle_video.models.layered_template import LayeredTemplateSpec, RectSpec
from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.timing_planner import TimingPlan


class _DummyCore:
    def __init__(self):
        self.config = {"comfyui": {"image": {}, "video": {}}}
        self.llm = object()
        self.tts = None
        self.media = object()
        self.video = None


def _spec_payload() -> dict:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(),
        metadata={},
    ).to_dict()


def test_storyboard_config_accepts_layered_template_snapshot():
    spec = _spec_payload()

    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        layered_template_spec=spec,
        selected_template_preset_id="user:demo",
    )

    assert config.layered_template_spec == spec
    assert config.selected_template_preset_id == "user:demo"


def _plan() -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="first. second.",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="first.",
                visual_goal="Show the first idea.",
                prompt_intent="Visualize first idea.",
                source_start=0,
                source_end=6,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="second.",
                visual_goal="Show the second idea.",
                prompt_intent="Visualize second idea.",
                source_start=7,
                source_end=14,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_initialize_storyboard_copies_layered_template_snapshot_to_config():
    spec = _spec_payload()
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "frame_template": "1080x1920/image_default.html",
            "layered_template_spec": spec,
            "selected_template_preset_id": "user:demo",
        },
    )
    ctx.task_id = "task-layered-config"
    ctx.title = "Layered config"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert ctx.config.layered_template_spec == spec
    assert ctx.config.selected_template_preset_id == "user:demo"


def test_build_render_manifest_copies_layered_template_snapshot(tmp_path, monkeypatch):
    spec = _spec_payload()
    task_dir = tmp_path / "task-layered-manifest"
    audio_dir = task_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    master_audio = audio_dir / "master_audio.wav"
    master_audio.write_bytes(b"audio")
    frame_path = task_dir / "frame_0.png"
    frame_path.write_bytes(b"png")

    pipeline = StandardPipeline(_DummyCore())
    monkeypatch.setattr(
        pipeline,
        "_caption_renderer_enabled",
        lambda *_args, **_kwargs: False,
    )

    ctx = PipelineContext(input_text="topic", params={})
    ctx.task_id = "task-layered-manifest"
    ctx.task_dir = str(task_dir)
    ctx.config = StoryboardConfig(
        task_id="task-layered-manifest",
        media_width=1080,
        media_height=1920,
        frame_template="1080x1920/image_default.html",
        video_fps=30,
        layered_template_spec=spec,
        selected_template_preset_id="user:demo",
    )
    ctx.storyboard = type("StoryboardStub", (), {})()
    ctx.storyboard.title = "Layered manifest"
    ctx.storyboard.frames = [
        type(
            "FrameStub",
            (),
            {
                "index": 0,
                "duration": 1.0,
                "composed_image_path": str(frame_path),
                "image_path": None,
                "video_path": None,
                "element_motion_video_path": None,
                "element_animation_manifest_path": None,
            },
        )()
    ]
    ctx.master_audio_path = str(master_audio)
    ctx.master_audio_duration = 1.0
    ctx.timing_plan = TimingPlan(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="first.",
                frame_indices=[0],
                block_id="block-1",
                source_start=0.0,
                source_end=1.0,
            )
        ],
        blocks=[
            AudioBlock(
                id="block-1",
                text="first.",
                source_frame_indices=[0],
                start=0.0,
                end=1.0,
            )
        ],
    )

    manifest = pipeline._build_render_manifest_for_current_timeline(ctx)

    assert manifest.layered_template_spec == spec
