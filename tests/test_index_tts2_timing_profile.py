import pytest

from pixelle_video.models.render_package import AudioBlock
from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.timing_planner import TimingPlan


class _FakeCore:
    def __init__(self):
        self.config = {
            "render": {
                "backend": "legacy",
                "timing": {
                    "tts_batching_mode": "paragraph",
                    "tts_batch_max_sentences": 8,
                    "tts_batch_max_chars": 220,
                    "subtitle_alignment_engine": "qwen_forced_aligner",
                    "silence_trim_tool": None,
                    "silence_trim_margin_ms": 120,
                },
            }
        }
        self.llm = None
        self.tts = None
        self.media = None
        self.video = None


def _storyboard_plan_from_segments(segments: list[str]) -> StoryboardPlan:
    source_text = "".join(
        segment if segment[-1:] in ".!?。！？" else f"{segment}。"
        for segment in segments
    )
    frames = []
    cursor = 0
    for index, segment in enumerate(segments, start=1):
        frame_text = segment if segment[-1:] in ".!?。！？" else f"{segment}。"
        start = cursor
        end = start + len(frame_text)
        frames.append(
            StoryboardPlanFrame(
                index=index,
                source_text=frame_text,
                visual_goal=f"Visualize segment {index}.",
                prompt_intent=f"Prompt for segment {index}.",
                source_start=start,
                source_end=end,
            )
        )
        cursor = end
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=source_text,
        frames=frames,
    )


@pytest.mark.asyncio
async def test_standard_pipeline_uses_single_index_tts2_audio_block_without_phrase_regroup():
    pipeline = StandardPipeline(_FakeCore())
    ctx = PipelineContext(
        input_text="demo",
        params={
            "media_width": 1080,
            "media_height": 1920,
            "tts_inference_mode": "comfyui",
            "tts_workflow": "selfhost/tts_index2.json",
        },
    )
    ctx.task_id = "task-index-tts2"
    ctx.title = "demo"
    segments = [
        "先练呼吸控制",
        "再练水中漂浮",
        "保持身体平直",
        "手臂划水流畅",
        "坚持练习进步",
    ]
    ctx.storyboard_plan = _storyboard_plan_from_segments(segments)
    ctx.image_prompts = ["p1", "p2", "p3", "p4", "p5"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.timing_plan is not None
    assert [block.text for block in ctx.timing_plan.blocks] == [
        "先练呼吸控制。再练水中漂浮。保持身体平直。手臂划水流畅。坚持练习进步。",
    ]
    assert [block.source_frame_indices for block in ctx.timing_plan.blocks] == [
        [0, 1, 2, 3, 4],
    ]
    assert ctx.observability["tts_text_flow"]["audio_blocks"][0]["speech_text"] == (
        "先练呼吸控制。再练水中漂浮。保持身体平直。手臂划水流畅。坚持练习进步。"
    )
    assert ctx.observability["tts_text_flow"]["caption_punctuation_mode"] == "strip_all"


@pytest.mark.asyncio
async def test_standard_pipeline_index_tts2_respects_space_joiner_option():
    pipeline = StandardPipeline(_FakeCore())
    ctx = PipelineContext(
        input_text="demo",
        params={
            "media_width": 1080,
            "media_height": 1920,
            "tts_inference_mode": "comfyui",
            "tts_workflow": "selfhost/tts_index2.json",
            "tts_sentence_joiner_mode": "space",
        },
    )
    ctx.task_id = "task-index-tts2-space"
    ctx.title = "demo"
    ctx.storyboard_plan = _storyboard_plan_from_segments(
        ["First sentence.", "Second sentence?"]
    )
    ctx.image_prompts = ["p1", "p2"]

    await pipeline.initialize_storyboard(ctx)

    assert [block.text for block in ctx.timing_plan.blocks] == [
        "First sentence. Second sentence?",
    ]


def test_standard_pipeline_does_not_require_index_tts2_internal_split_control_params():
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_index2.json",
        tts_split_mode="external_only",
        max_chars_per_tts_segment=120,
        tts_split_overflow_policy="error",
    )
    pipeline = StandardPipeline(_FakeCore())

    params = pipeline._build_tts_params(
        config=config,
        text="第一句。第二句。",
        output_path="audio.wav",
    )

    assert params["text"] == "第一句。第二句。"
    assert "split_strategy" not in params
    assert "max_text_tokens_per_segment" not in params
    assert "interval_silence_ms" not in params
    assert "overflow_policy" not in params


def test_standard_pipeline_passes_ref_audio_text_as_semantic_param():
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_longcat_clone.json",
        ref_audio="temp/ref.wav",
        ref_audio_text="hello from the reference clip",
    )
    pipeline = StandardPipeline(_FakeCore())

    params = pipeline._build_tts_params(
        config=config,
        text="hello from the generated clip",
        output_path="audio.wav",
    )

    assert params["ref_audio"] == "temp/ref.wav"
    assert params["ref_audio_text"] == "hello from the reference clip"
    assert "prompt_text" not in params


@pytest.mark.asyncio
async def test_standard_pipeline_external_only_synthesizes_deterministic_segments(monkeypatch, tmp_path):
    class RecordingTts:
        def __init__(self):
            self.calls = []

        async def __call__(self, **params):
            self.calls.append(params)
            return params["output_path"]

    core = _FakeCore()
    core.tts = RecordingTts()
    pipeline = StandardPipeline(core)
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-index-tts2",
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_index2.json",
        tts_split_mode="external_only",
        max_chars_per_tts_segment=24,
        tts_boundary_search_radius=12,
    )
    ctx = PipelineContext(input_text="demo", params={})
    ctx.task_id = config.task_id
    ctx.task_dir = str(tmp_path)
    ctx.config = config
    ctx.timing_plan = TimingPlan(
        blocks=[
            AudioBlock(
                id="block-1",
                text="她停下来，把围巾重新系紧，然后抬头看了一眼泛白的天空，像是在等什么",
                source_frame_indices=[0],
            )
        ]
    )

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", lambda source, output: output)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda path: 1.0)
    concat_calls = []
    monkeypatch.setattr(
        pipeline,
        "_concat_audio_files",
        lambda paths, output, **kwargs: concat_calls.append((paths, output, kwargs)),
    )

    await pipeline._synthesize_hyperframes_audio(ctx)

    synthesized_texts = [call["text"] for call in core.tts.calls]
    assert "".join(synthesized_texts) == ctx.timing_plan.blocks[0].text
    assert len(synthesized_texts) > 1
    assert all("。" not in text for text in synthesized_texts)
    assert all("split_strategy" not in call for call in core.tts.calls)
    assert [call["workflow_params_text"] for call in ctx.observability["tts_synthesis"]["calls"]] == synthesized_texts
    plans = ctx.observability["tts_segmentation"]["plans"]
    assert plans[0]["source_unit_id"] == "block-1"
    assert len(plans[0]["segments"]) == len(synthesized_texts)
    assert plans[0]["segments"][0]["synthesis_mode"] == "external_pre_split"


@pytest.mark.asyncio
async def test_standard_pipeline_master_concat_uses_boundary_fade(monkeypatch, tmp_path):
    class RecordingTts:
        async def __call__(self, **params):
            return params["output_path"]

    core = _FakeCore()
    core.tts = RecordingTts()
    pipeline = StandardPipeline(core)
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-master-fade",
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_edge.json",
        tts_audio_boundary_fade_ms=12,
    )
    ctx = PipelineContext(input_text="demo", params={})
    ctx.task_id = config.task_id
    ctx.task_dir = str(tmp_path)
    ctx.config = config
    ctx.timing_plan = TimingPlan(
        blocks=[
            AudioBlock(id="block-1", text="第一段。", source_frame_indices=[0]),
            AudioBlock(id="block-2", text="第二段。", source_frame_indices=[1]),
        ]
    )

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", lambda source, output: output)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda path: 1.0)
    concat_calls = []
    monkeypatch.setattr(
        pipeline,
        "_concat_audio_files",
        lambda paths, output, **kwargs: concat_calls.append((paths, output, kwargs)),
    )

    await pipeline._synthesize_hyperframes_audio(ctx)

    assert concat_calls[-1][1].endswith("master_audio.wav")
    assert concat_calls[-1][2]["fade_ms"] == 12
