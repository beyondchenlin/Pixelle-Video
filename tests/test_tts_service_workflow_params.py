from types import SimpleNamespace

import pytest

from pixelle_video.services.tts_service import TTSService
from pixelle_video.tts_workflow_family import (
    infer_tts_workflow_family,
    is_omnivoice_workflow_key,
    is_tts_workflow_family,
)
from pixelle_video.tts_workflow_contract import (
    is_index_tts2_workflow_info,
    is_index_tts2_workflow_key,
    resolve_workflow_output_audio_extension,
)


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


class _FailingKit:
    async def execute(self, workflow_input, params):
        return SimpleNamespace(status="failed", msg="WebSocket connection closed")


class _FailingCore:
    def __init__(self):
        self.kit = _FailingKit()

    async def _get_or_create_comfykit(self):
        return self.kit


def test_resolve_workflow_output_audio_extension_from_save_audio_nodes():
    assert resolve_workflow_output_audio_extension(
        {"8": {"class_type": "SaveAudio", "inputs": {"audio": ["5", 0]}}}
    ) == ".flac"
    assert resolve_workflow_output_audio_extension(
        {"9": {"class_type": "SaveAudioMP3", "inputs": {"audio": ["5", 0]}}}
    ) == ".mp3"
    assert resolve_workflow_output_audio_extension(
        {"10": {"class_type": "SaveAudioOpus", "inputs": {"audio": ["5", 0]}}}
    ) == ".opus"
    assert resolve_workflow_output_audio_extension(
        {"11": {"class_type": "UnknownAudioSaver", "inputs": {"audio": ["5", 0]}}}
    ) == ".mp3"


def test_renamed_workflow_file_with_index_tts2_node_is_detected(tmp_path):
    workflow_path = tmp_path / "renamed_voice_workflow.json"
    workflow_path.write_text(
        """
        {
          "5": {
            "inputs": {"text": ["3", 0]},
            "class_type": "IndexTTS2BaseNode"
          }
        }
        """,
        encoding="utf-8",
    )

    assert is_index_tts2_workflow_key(workflow_path)


def test_regular_tts_workflow_file_is_not_detected_as_index_tts2(tmp_path):
    workflow_path = tmp_path / "regular_tts.json"
    workflow_path.write_text(
        """
        {
          "1": {
            "inputs": {"text": ["3", 0]},
            "class_type": "PixelleEdgeTTS"
          }
        }
        """,
        encoding="utf-8",
    )

    assert not is_index_tts2_workflow_key(workflow_path)


def test_regular_cache_control_node_workflow_is_not_detected_as_index_tts2(tmp_path):
    workflow_path = tmp_path / "regular_cache_control.json"
    workflow_path.write_text(
        """
        {
          "12": {
            "inputs": {"cache": true},
            "class_type": "CacheControlNode"
          }
        }
        """,
        encoding="utf-8",
    )

    assert not is_index_tts2_workflow_key(workflow_path)


def test_tts_workflow_family_detects_omnivoice_from_node_class(tmp_path):
    workflow_path = tmp_path / "custom_tts.json"
    workflow_path.write_text(
        """
        {
          "1": {
            "inputs": {"text": "hello"},
            "class_type": "OmniVoiceLongformTTS",
            "_meta": {"title": "OmniVoice Longform TTS"}
          }
        }
        """,
        encoding="utf-8",
    )

    assert infer_tts_workflow_family(workflow_path) == "omnivoice"
    assert is_tts_workflow_family(workflow_path, "omnivoice") is True
    assert is_omnivoice_workflow_key(workflow_path) is True


def test_tts_workflow_family_detects_index_tts2_from_existing_workflow():
    assert infer_tts_workflow_family("selfhost/tts_index2.json") == "indextts2"


def test_tts_workflow_family_detects_edge_from_existing_workflow():
    assert infer_tts_workflow_family("selfhost/tts_edge.json") == "edge"


def test_tts_workflow_family_falls_back_to_generic_for_unknown_workflow(tmp_path):
    workflow_path = tmp_path / "custom_tts.json"
    workflow_path.write_text(
        """
        {
          "1": {
            "inputs": {"text": "hello"},
            "class_type": "CustomTTSNode",
            "_meta": {"title": "Custom TTS"}
          }
        }
        """,
        encoding="utf-8",
    )

    assert infer_tts_workflow_family(workflow_path) == "generic"


def test_selfhost_workflow_info_uses_path_content_for_index_tts2_detection(tmp_path):
    workflow_path = tmp_path / "custom_voice.json"
    workflow_path.write_text(
        """
        {
          "13": {
            "inputs": {"keep_models_cached": true},
            "class_type": "IndexTTS2CacheControlNode"
          }
        }
        """,
        encoding="utf-8",
    )

    assert is_index_tts2_workflow_info(
        {
            "key": "selfhost/custom_voice.json",
            "source": "selfhost",
            "path": workflow_path,
        }
    )


def test_non_selfhost_workflow_info_uses_key_fallback_for_index_tts2_detection(tmp_path):
    workflow_path = tmp_path / "remote_wrapper.json"
    workflow_path.write_text(
        """
        {
          "5": {
            "inputs": {"text": ["3", 0]},
            "class_type": "IndexTTS2BaseNode"
          }
        }
        """,
        encoding="utf-8",
    )

    assert not is_index_tts2_workflow_info(
        {
            "key": "runninghub/custom_voice.json",
            "source": "runninghub",
            "path": workflow_path,
        }
    )


@pytest.mark.asyncio
async def test_tts_service_copies_local_comfyui_result_to_output_path(tmp_path):
    source_path = tmp_path / "comfyui-result.flac"
    source_path.write_bytes(b"flac-data")
    output_path = tmp_path / "requested" / "audio.flac"
    output_path.parent.mkdir()
    output_path.write_bytes(b"old-data")

    class _LocalResultKit:
        async def execute(self, workflow_input, params):
            return SimpleNamespace(status="completed", audios=[str(source_path)])

    class _LocalResultCore:
        async def _get_or_create_comfykit(self):
            return _LocalResultKit()

    service = TTSService({"comfyui": {"tts": {}}}, core=_LocalResultCore())

    returned_path = await service._call_comfyui_workflow(
        {
            "key": "selfhost/tts_edge.json",
            "source": "selfhost",
            "path": "workflows/selfhost/tts_edge.json",
        },
        text="generated text",
        output_path=str(output_path),
    )

    assert returned_path == str(output_path)
    assert output_path.read_bytes() == b"flac-data"
    assert source_path.read_bytes() == b"flac-data"


@pytest.mark.asyncio
async def test_tts_service_accepts_opus_audio_from_outputs(tmp_path):
    source_path = tmp_path / "comfyui-result.opus"
    source_path.write_bytes(b"opus-data")

    class _OpusOutputKit:
        async def execute(self, workflow_input, params):
            return SimpleNamespace(status="completed", outputs={"audio": str(source_path)})

    class _OpusOutputCore:
        async def _get_or_create_comfykit(self):
            return _OpusOutputKit()

    service = TTSService({"comfyui": {"tts": {}}}, core=_OpusOutputCore())

    returned_path = await service._call_comfyui_workflow(
        {
            "key": "selfhost/tts_opus.json",
            "source": "selfhost",
            "path": "workflows/selfhost/tts_opus.json",
        },
        text="generated text",
    )

    assert returned_path == str(source_path)


@pytest.mark.asyncio
async def test_tts_service_rejects_missing_required_ref_audio_before_execution():
    core = _FakeCore()
    service = TTSService({"comfyui": {"tts": {}}}, core=core)

    with pytest.raises(
        ValueError,
        match="TTS workflow 'selfhost/tts_index2.json' missing required params: ref_audio",
    ):
        await service._call_comfyui_workflow(
            {
                "key": "selfhost/tts_index2.json",
                "source": "selfhost",
                "path": "workflows/selfhost/tts_index2.json",
            },
            text="generated text",
        )

    assert core.kit.calls == []


@pytest.mark.asyncio
async def test_tts_service_includes_workflow_key_in_execution_failures():
    core = _FailingCore()
    service = TTSService({"comfyui": {"tts": {}}}, core=core)

    with pytest.raises(
        Exception,
        match="TTS workflow 'selfhost/tts_index2.json' failed: WebSocket connection closed",
    ):
        await service._call_comfyui_workflow(
            {
                "key": "selfhost/tts_index2.json",
                "source": "selfhost",
                "path": "workflows/selfhost/tts_index2.json",
            },
            text="generated text",
            ref_audio="data/reference_audio/indextts2/sample.wav",
        )
