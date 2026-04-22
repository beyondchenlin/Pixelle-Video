import pytest

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


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


@pytest.mark.asyncio
async def test_standard_pipeline_tightens_index_tts2_batches_and_adds_terminal_pauses():
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
    ctx.narrations = [
        "先练呼吸控制",
        "再练水中漂浮",
        "保持身体平直",
        "手臂划水流畅",
        "坚持练习进步",
    ]
    ctx.image_prompts = ["p1", "p2", "p3", "p4", "p5"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.timing_plan is not None
    assert [block.text for block in ctx.timing_plan.blocks] == [
        "先练呼吸控制。再练水中漂浮。保持身体平直。手臂划水流畅。",
        "坚持练习进步。",
    ]
    assert [block.source_frame_indices for block in ctx.timing_plan.blocks] == [
        [0, 1, 2, 3],
        [4],
    ]
