import pytest

from pixelle_video.config import config_manager
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.config.workflow_defaults import BUILTIN_DEFAULT_WORKFLOWS
from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.persistence import PersistenceService
from web.pipelines.digital_human import build_tts_generation_kwargs
from web.utils.tts_ui import resolve_configured_tts_mode

DEFAULT_TTS_WORKFLOW = "selfhost/tts_index2_8g.json"


class _FakeCore:
    def __init__(self):
        self.config = {
            "comfyui": {"tts": {"inference_mode": "comfyui"}},
            "render": {"backend": "legacy", "timing": {}},
        }
        self.llm = None
        self.tts = None
        self.media = None
        self.video = None


def _single_frame_plan() -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="测试文本。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="测试文本。",
                visual_goal="Visualize test text.",
                prompt_intent="Prompt for test text.",
            )
        ],
    )


def test_tts_defaults_to_comfyui_indextts2_workflow():
    config = PixelleVideoConfig()

    assert config.comfyui.tts.inference_mode == "comfyui"
    assert config.comfyui.tts.comfyui.default_workflow == DEFAULT_TTS_WORKFLOW
    assert config.comfyui.tts.default_workflow == DEFAULT_TTS_WORKFLOW
    assert BUILTIN_DEFAULT_WORKFLOWS["tts"] == DEFAULT_TTS_WORKFLOW


def test_comfyui_config_exposes_nested_tts_settings_for_ui(monkeypatch):
    monkeypatch.setattr(config_manager, "config", PixelleVideoConfig())

    tts_config = config_manager.get_comfyui_config()["tts"]

    assert tts_config["inference_mode"] == "comfyui"
    assert tts_config["comfyui"]["default_workflow"] == DEFAULT_TTS_WORKFLOW
    assert tts_config["default_workflow"] == DEFAULT_TTS_WORKFLOW


def test_legacy_tts_default_workflow_config_is_migrated_to_comfyui_section():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "tts": {
                    "default_workflow": "selfhost/tts_edge.json",
                }
            }
        }
    )

    assert config.comfyui.tts.comfyui.default_workflow == "selfhost/tts_edge.json"
    assert config.comfyui.tts.default_workflow == "selfhost/tts_edge.json"


def test_nested_tts_default_workflow_takes_priority_over_legacy_field():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "tts": {
                    "default_workflow": "selfhost/tts_edge.json",
                    "comfyui": {
                        "default_workflow": "selfhost/tts_index2.json",
                    },
                }
            }
        }
    )

    assert config.comfyui.tts.comfyui.default_workflow == "selfhost/tts_index2.json"
    assert config.comfyui.tts.default_workflow == "selfhost/tts_index2.json"


def test_storyboard_tts_default_matches_config_default():
    assert StoryboardConfig(media_width=1080, media_height=1920).tts_inference_mode == "comfyui"


def test_web_tts_mode_default_helper_matches_config_default():
    assert resolve_configured_tts_mode({}) == "comfyui"


def test_persistence_config_load_defaults_to_comfyui_tts_mode(tmp_path):
    service = PersistenceService(str(tmp_path))

    config = service._dict_to_config({"media_width": 1080, "media_height": 1920})

    assert config.tts_inference_mode == "comfyui"


def test_digital_human_tts_kwargs_default_to_comfyui_mode():
    kwargs = build_tts_generation_kwargs(
        {},
        text="测试文本。",
        output_path="output/narration.mp3",
    )

    assert kwargs == {
        "text": "测试文本。",
        "output_path": "output/narration.mp3",
        "inference_mode": "comfyui",
    }


@pytest.mark.asyncio
async def test_standard_pipeline_tts_mode_falls_back_to_configured_default():
    pipeline = StandardPipeline(_FakeCore())
    ctx = PipelineContext(input_text="测试文本。", params={"media_width": 1080, "media_height": 1920})
    ctx.task_id = "task-tts-default"
    ctx.title = "TTS Default"
    ctx.storyboard_plan = _single_frame_plan()
    ctx.image_prompts = ["prompt"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.config.tts_inference_mode == "comfyui"


@pytest.mark.asyncio
async def test_standard_pipeline_initializes_distinct_canvas_and_media_sizes():
    pipeline = StandardPipeline(_FakeCore())
    ctx = PipelineContext(
        input_text="test text",
        params={
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 768,
            "media_height": 768,
            "video_orientation": "landscape",
            "video_resolution_preset": "1k",
            "media_orientation": "square",
            "media_resolution_preset": "768",
            "sync_media_size_to_canvas": False,
        },
    )
    ctx.task_id = "task-size-contract"
    ctx.title = "Size Contract"
    ctx.storyboard_plan = _single_frame_plan()
    ctx.image_prompts = ["prompt"]

    await pipeline.initialize_storyboard(ctx)

    assert (ctx.config.canvas_width, ctx.config.canvas_height) == (1280, 720)
    assert (ctx.config.media_width, ctx.config.media_height) == (768, 768)
    assert ctx.config.video_orientation == "landscape"
    assert ctx.config.video_resolution_preset == "1k"
    assert ctx.config.media_orientation == "square"
    assert ctx.config.media_resolution_preset == "768"
