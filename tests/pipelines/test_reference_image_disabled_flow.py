from types import SimpleNamespace

import pytest
from PIL import Image

from pixelle_video.pipelines.linear import LinearVideoPipeline, PipelineContext


@pytest.mark.asyncio
async def test_reference_image_disabled_clears_ref_image_without_assetization(tmp_path):
    source_path = tmp_path / "reference.png"
    Image.new("RGB", (32, 32), (255, 255, 255)).save(source_path)

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    core = SimpleNamespace(
        config={"reference_image": {"enabled": False}},
        llm=None,
        tts=None,
        media=None,
        video=None,
    )
    pipeline = LinearVideoPipeline(core)
    ctx = PipelineContext(
        input_text="生成一个儿童故事",
        params={
            "ref_image": str(source_path),
            "ref_image_asset": {"stale": True},
        },
        task_dir=str(task_dir),
    )

    await pipeline.prepare_reference_image(ctx)

    assert ctx.reference_image_asset is None
    assert "ref_image" not in ctx.params
    assert "ref_image_asset" not in ctx.params
    assert not (task_dir / "reference_image").exists()
    assert ctx.observability["reference_image"]["status"] == "disabled"
