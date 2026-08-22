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


@pytest.mark.asyncio
async def test_visual_anchor_forces_real_reference_image_assetization(tmp_path):
    source_path = tmp_path / "dog.png"
    Image.new("RGB", (32, 32), (24, 24, 24)).save(source_path)

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    pipeline = LinearVideoPipeline(
        SimpleNamespace(
            config={"reference_image": {"enabled": False}},
            llm=None,
            tts=None,
            media=None,
            video=None,
        )
    )
    ctx = PipelineContext(
        input_text="生成一个人物故事",
        params={
            "series_visual_signature_enabled": True,
            "ref_image": str(source_path),
        },
        task_dir=str(task_dir),
    )

    await pipeline.prepare_reference_image(ctx)

    assert ctx.reference_image_asset is not None
    assert ctx.params["ref_image"] == ctx.reference_image_asset.workflow_asset_path
    assert ctx.params["ref_image_asset"]["workflow_sha256"]
    assert (task_dir / "reference_image" / "asset.json").is_file()


@pytest.mark.asyncio
async def test_visual_anchor_rejects_missing_reference_before_content_generation(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    pipeline = LinearVideoPipeline(
        SimpleNamespace(
            config={"reference_image": {"enabled": False}},
            llm=None,
            tts=None,
            media=None,
            video=None,
        )
    )
    ctx = PipelineContext(
        input_text="生成一个人物故事",
        params={"series_visual_signature_enabled": True},
        task_dir=str(task_dir),
    )

    with pytest.raises(ValueError, match="real reference image"):
        await pipeline.prepare_reference_image(ctx)
