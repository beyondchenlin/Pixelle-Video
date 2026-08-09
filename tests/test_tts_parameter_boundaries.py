from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.tts_service import TTSService


@pytest.mark.asyncio
async def test_local_tts_maps_legacy_voice_id_explicitly() -> None:
    service = TTSService({"local": {}})
    service._call_local_tts = AsyncMock(return_value="voice.mp3")

    result = await service(
        text="hello",
        inference_mode="local",
        voice_id="en-US-JennyNeural",
    )

    assert result == "voice.mp3"
    service._call_local_tts.assert_awaited_once_with(
        text="hello",
        voice="en-US-JennyNeural",
        speed=None,
        output_path=None,
    )


@pytest.mark.asyncio
async def test_local_tts_rejects_conflicting_voice_aliases() -> None:
    service = TTSService({"local": {}})

    with pytest.raises(ValueError, match="different local voices"):
        await service(
            text="hello",
            inference_mode="local",
            voice="en-US-JennyNeural",
            voice_id="zh-CN-YunjianNeural",
        )


@pytest.mark.asyncio
async def test_local_tts_rejects_unknown_workflow_parameters() -> None:
    service = TTSService({"local": {}})

    with pytest.raises(TypeError, match="unexpected_parameter"):
        await service(
            text="hello",
            inference_mode="local",
            unexpected_parameter="silent typo",
        )


def test_frame_processor_only_sends_workflow_index_to_comfyui() -> None:
    processor = FrameProcessor(SimpleNamespace())
    local_params = processor._build_tts_params(
        text="hello",
        output_path="audio.mp3",
        config=StoryboardConfig(
            media_width=1920,
            media_height=1080,
            tts_inference_mode="local",
        ),
        index=3,
    )
    comfyui_params = processor._build_tts_params(
        text="hello",
        output_path="audio.mp3",
        config=StoryboardConfig(
            media_width=1920,
            media_height=1080,
            tts_inference_mode="comfyui",
        ),
        index=3,
    )

    assert "index" not in local_params
    assert comfyui_params["index"] == 3
