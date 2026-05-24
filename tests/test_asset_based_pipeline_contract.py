import json

import pytest

from pixelle_video.models.asset_script import (
    AssetCatalogEntry,
    AssetScriptResponse,
    AssetScriptSceneResponse,
)
from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.prompts.asset_script_generation import build_asset_script_prompt


def test_build_asset_script_prompt_embeds_asset_schema_and_ids():
    prompt = json.loads(
        build_asset_script_prompt(
            intent="Promote the spring sale",
            duration=30,
            assets=[
                AssetCatalogEntry(
                    asset_id="asset_001",
                    asset_path="C:/assets/cat.png",
                    asset_type="image",
                    asset_name="cat.png",
                    description="A smiling cat in front of the shop",
                )
            ],
            title="Spring Sale",
        )
    )

    assert prompt["task"] == "plan_asset_video_script"
    assert prompt["required_output"] == AssetScriptResponse.model_json_schema()
    assert prompt["available_assets"][0]["asset_id"] == "asset_001"
    assert "asset_path" not in prompt["available_assets"][0]
    assert any("asset_id" in instruction and "Never invent" in instruction for instruction in prompt["instructions"])


@pytest.mark.asyncio
async def test_asset_based_generate_content_resolves_asset_id_to_path():
    captured = {}

    class FakeCore:
        config = {}
        tts = object()
        media = object()
        video = object()
        frame_processor = object()
        persistence = object()
        trace_repository = object()
        raw_payload_store = object()

        async def llm(self, *, prompt, **kwargs):
            captured["prompt"] = prompt
            captured["response_type"] = kwargs.get("response_type")
            return AssetScriptResponse(
                scenes=[
                    AssetScriptSceneResponse(
                        scene_number=1,
                        asset_id="asset_001",
                        narrations=["Welcome to our spring sale."],
                        duration=8,
                    )
                ]
            )

    pipeline = AssetBasedPipeline(FakeCore())
    pipeline.asset_index = {
        "asset_001": {
            "asset_id": "asset_001",
            "path": "C:/assets/cat.png",
            "type": "image",
            "name": "cat.png",
            "description": "A smiling cat in front of the shop",
        }
    }

    ctx = PipelineContext(input_text="Promote the spring sale", params={"duration": 30, "intent": "Promote the spring sale"})
    ctx.request = ctx.params
    ctx.title = "Spring Sale"
    ctx.task_id = "task-asset-script-001"

    await pipeline.generate_content(ctx)

    assert captured["response_type"] is AssetScriptResponse
    assert '"asset_id": "asset_001"' in captured["prompt"]
    assert ctx.script == [
        {
            "scene_number": 1,
            "asset_id": "asset_001",
            "narrations": ["Welcome to our spring sale."],
            "duration": 8,
            "asset_path": "C:/assets/cat.png",
            "asset_name": "cat.png",
            "asset_type": "image",
        }
    ]


@pytest.mark.asyncio
async def test_asset_based_generate_content_rejects_unknown_asset_id():
    class FakeCore:
        config = {}
        tts = object()
        media = object()
        video = object()
        frame_processor = object()
        persistence = object()
        trace_repository = object()
        raw_payload_store = object()

        async def llm(self, *, prompt, **kwargs):
            return AssetScriptResponse(
                scenes=[
                    AssetScriptSceneResponse(
                        scene_number=1,
                        asset_id="asset_missing",
                        narrations=["Welcome to our spring sale."],
                        duration=8,
                    )
                ]
            )

    pipeline = AssetBasedPipeline(FakeCore())
    pipeline.asset_index = {
        "asset_001": {
            "asset_id": "asset_001",
            "path": "C:/assets/cat.png",
            "type": "image",
            "name": "cat.png",
            "description": "A smiling cat in front of the shop",
        }
    }

    ctx = PipelineContext(input_text="Promote the spring sale", params={"duration": 30, "intent": "Promote the spring sale"})
    ctx.request = ctx.params
    ctx.title = "Spring Sale"
    ctx.task_id = "task-asset-script-002"

    with pytest.raises(ValueError, match="unknown asset_id"):
        await pipeline.generate_content(ctx)
