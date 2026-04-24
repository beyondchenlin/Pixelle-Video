from types import SimpleNamespace

import pytest

from pixelle_video.services.tts_service import TTSService


class _RecordingKit:
    def __init__(self):
        self.calls = []

    async def execute(self, workflow_input, params):
        self.calls.append((workflow_input, params))
        return SimpleNamespace(status="completed", audios=["generated.wav"])


class _FakeCore:
    def __init__(self):
        self.kit = _RecordingKit()

    async def _get_or_create_comfykit(self):
        return self.kit


@pytest.mark.asyncio
async def test_tts_service_maps_ref_audio_text_to_longcat_prompt_text():
    core = _FakeCore()
    service = TTSService({"comfyui": {"tts": {}}}, core=core)

    await service._call_comfyui_workflow(
        {
            "key": "selfhost/tts_longcat_clone.json",
            "source": "selfhost",
            "path": "workflows/selfhost/tts_longcat_clone.json",
        },
        text="generated text",
        ref_audio_text="reference transcript",
    )

    _, params = core.kit.calls[0]
    assert params["prompt_text"] == "reference transcript"
    assert "ref_audio_text" not in params
    assert "reference_audio_text" not in params


@pytest.mark.asyncio
async def test_tts_service_maps_ref_audio_text_to_runninghub_voxcpm_reference_audio_text():
    core = _FakeCore()
    service = TTSService({"comfyui": {"tts": {}}}, core=core)

    await service._call_comfyui_workflow(
        {
            "key": "selfhost/tts_voxcpm2_rh_clone.json",
            "source": "selfhost",
            "path": "workflows/selfhost/tts_voxcpm2_rh_clone.json",
        },
        text="generated text",
        ref_audio_text="reference transcript",
    )

    _, params = core.kit.calls[0]
    assert params["reference_audio_text"] == "reference transcript"
    assert "ref_audio_text" not in params
    assert "prompt_text" not in params
