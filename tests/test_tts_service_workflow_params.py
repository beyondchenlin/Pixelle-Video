from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routers import tts as tts_router
from api.schemas.tts import TTSSynthesizeRequest
from pixelle_video.services.tts_service import TTSService
from pixelle_video.tts_workflow_contract import (
    get_missing_required_tts_workflow_params,
    get_required_tts_workflow_params,
    is_index_tts2_workflow_info,
    is_index_tts2_workflow_key,
    resolve_workflow_output_audio_extension,
    tts_workflow_missing_required_ref_audio,
    tts_workflow_requires_ref_audio,
)
from pixelle_video.tts_workflow_family import (
    infer_tts_workflow_family,
    is_known_tts_workflow_resource,
    is_omnivoice_longform_workflow_key,
    is_omnivoice_workflow_key,
    is_tts_workflow_family,
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

    async def execute_comfykit_workflow(self, workflow_input, params, **kwargs):
        assert kwargs.get("tts_workflow_trace_context") is not None
        return await self.kit.execute(workflow_input, params)


class _FailingKit:
    async def execute(self, workflow_input, params):
        return SimpleNamespace(status="failed", msg="WebSocket connection closed")


class _FailingCore:
    def __init__(self):
        self.kit = _FailingKit()

    async def _get_or_create_comfykit(self):
        return self.kit

    async def execute_comfykit_workflow(self, workflow_input, params, **kwargs):
        assert kwargs.get("tts_workflow_trace_context") is not None
        return await self.kit.execute(workflow_input, params)


class _RecordingTtsCore:
    def __init__(self):
        self.calls = []

    async def tts(self, **params):
        self.calls.append(dict(params))
        return "generated.wav"


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


def test_tts_workflow_family_detects_omnivoice_from_ui_nodes(tmp_path):
    workflow_path = tmp_path / "custom_voice.json"
    workflow_path.write_text(
        """
        {
          "nodes": [
            {
              "id": 1,
              "type": "OmniVoiceLongformTTS",
              "inputs": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    assert infer_tts_workflow_family(workflow_path) == "omnivoice"
    assert is_known_tts_workflow_resource(workflow_path) is True


def test_tts_workflow_resource_requires_confirmed_tts_content(tmp_path):
    workflow_path = tmp_path / "OmniVoice_fake.json"
    workflow_path.write_text(
        """
        {
          "source": "selfhost"
        }
        """,
        encoding="utf-8",
    )

    assert infer_tts_workflow_family(workflow_path) == "omnivoice"
    assert is_known_tts_workflow_resource(workflow_path) is False


def test_runninghub_tts_descriptor_uses_explicit_domain_not_filename(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    workflow_path = tmp_path / "workflows" / "runninghub" / "voice_descriptor.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        """
        {
          "source": "runninghub",
          "workflow_id": "rh-voice-123",
          "workflow_domain": "tts",
          "service_domain": "tts"
        }
        """,
        encoding="utf-8",
    )

    assert is_known_tts_workflow_resource(workflow_path) is True


def test_runninghub_tts_descriptor_does_not_trust_filename_without_domain(tmp_path):
    workflow_path = tmp_path / "workflows" / "runninghub" / "tts_edge.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        """
        {
          "source": "runninghub",
          "workflow_id": "rh-voice-123"
        }
        """,
        encoding="utf-8",
    )

    assert is_known_tts_workflow_resource(workflow_path) is False


def test_tts_service_scans_runninghub_tts_descriptor_without_tts_prefix(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow_path = workflow_dir / "voice_descriptor.json"
    workflow_path.write_text(
        """
        {
          "source": "runninghub",
          "workflow_id": "rh-voice-123",
          "workflow_domain": "tts",
          "service_domain": "tts"
        }
        """,
        encoding="utf-8",
    )
    service = TTSService({"comfyui": {"tts": {}}})
    workflow_info = service._resolve_workflow("runninghub/voice_descriptor.json")

    assert workflow_info["key"] == "runninghub/voice_descriptor.json"
    assert workflow_info["workflow_domain"] == "tts"
    assert workflow_info["service_domain"] == "tts"


def test_tts_service_ignores_runninghub_tts_prefix_without_explicit_domain(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow_path = workflow_dir / "tts_edge.json"
    workflow_path.write_text(
        """
        {
          "source": "runninghub",
          "workflow_id": "rh-voice-123"
        }
        """,
        encoding="utf-8",
    )
    service = TTSService({"comfyui": {"tts": {}}})
    assert service._scan_workflows() == []


def test_tts_workflow_family_detects_omnivoice_longform_capability_from_node_class(tmp_path):
    workflow_path = tmp_path / "custom_omnivoice_fp32.json"
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

    assert is_omnivoice_longform_workflow_key(workflow_path) is True


def test_tts_workflow_family_does_not_treat_duration_clone_as_longform():
    assert (
        is_omnivoice_longform_workflow_key(
            "selfhost/tts_omnivoice_clone_duration_bf16.json"
        )
        is False
    )


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


def test_tts_workflow_required_params_are_read_from_api_workflow_metadata():
    assert get_required_tts_workflow_params(
        "selfhost/tts_omnivoice_longform_bf16.json"
    ) == frozenset({"ref_audio", "text"})
    assert tts_workflow_requires_ref_audio(
        "selfhost/tts_omnivoice_longform_bf16.json"
    )
    assert not tts_workflow_requires_ref_audio("selfhost/tts_edge.json")


def test_tts_workflow_contract_reports_missing_required_ref_audio_from_metadata():
    workflow_key = "selfhost/tts_omnivoice_longform_bf16.json"

    assert get_missing_required_tts_workflow_params(
        workflow_key,
        {"text": "narration", "ref_audio": ""},
    ) == ("ref_audio",)
    assert tts_workflow_missing_required_ref_audio(workflow_key, None) is True
    assert tts_workflow_missing_required_ref_audio(workflow_key, "voice.wav") is False
    assert tts_workflow_missing_required_ref_audio("selfhost/tts_edge.json", None) is False


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

        async def execute_comfykit_workflow(self, workflow_input, params, **kwargs):
            assert kwargs.get("tts_workflow_trace_context") is not None
            return await _LocalResultKit().execute(workflow_input, params)

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

        async def execute_comfykit_workflow(self, workflow_input, params, **kwargs):
            assert kwargs.get("tts_workflow_trace_context") is not None
            return await _OpusOutputKit().execute(workflow_input, params)

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
async def test_tts_service_rejects_core_without_provenance_execute_boundary():
    class _LegacyKit:
        async def execute(self, workflow_input, params):
            raise AssertionError("legacy kit.execute fallback must not run")

    class _LegacyCore:
        async def _get_or_create_comfykit(self):
            return _LegacyKit()

    service = TTSService({"comfyui": {"tts": {}}}, core=_LegacyCore())

    with pytest.raises(RuntimeError, match="provenance-capable"):
        await service._call_comfyui_workflow(
            {
                "key": "selfhost/tts_edge.json",
                "source": "selfhost",
                "path": "workflows/selfhost/tts_edge.json",
            },
            text="generated text",
        )


@pytest.mark.asyncio
async def test_tts_service_writes_trace_for_comfyui_workflow(tmp_path, monkeypatch):
    source_path = tmp_path / "comfyui-result.wav"
    source_path.write_bytes(b"audio-data")
    output_path = tmp_path / "requested" / "audio.wav"
    captured = {}

    async def fake_execute(
        workflow_input,
        workflow_params,
        workflow_info,
        *,
        backend_role="default",
        tts_workflow_trace_context=None,
    ):
        assert isinstance(tts_workflow_trace_context, dict)
        captured["workflow_input"] = workflow_input
        captured["workflow_params"] = dict(workflow_params)
        captured["workflow_info"] = dict(workflow_info)
        captured["backend_role"] = backend_role
        captured["trace_context"] = dict(tts_workflow_trace_context)
        return SimpleNamespace(
            status="completed",
            audios=[str(source_path)],
            files=[],
            outputs={},
        )

    service = TTSService({"comfyui": {"tts": {}}})
    monkeypatch.setattr(service, "_execute_workflow", fake_execute)
    monkeypatch.setattr(service, "_validate_required_workflow_params", lambda *_args: None)

    returned_path = await service._call_comfyui_workflow(
        {
            "key": "selfhost/tts_edge.json",
            "source": "selfhost",
            "path": "workflows/selfhost/tts_edge.json",
        },
        text="hello trace",
        voice="en-US-JennyNeural",
        speed=1.2,
        output_path=str(output_path),
    )

    artifact_path = Path(str(captured["trace_context"]["artifact_path"]))
    result_path = artifact_path.with_name("tts_service_result.md")
    artifact_text = artifact_path.read_text(encoding="utf-8")
    result_text = result_path.read_text(encoding="utf-8")

    assert returned_path == str(output_path)
    assert captured["workflow_params"]["text"] == "hello trace"
    assert captured["trace_context"]["workflow"] == "selfhost/tts_edge.json"
    assert captured["trace_context"]["workflow_input"] == "workflows/selfhost/tts_edge.json"
    assert "hello trace" in artifact_text
    assert result_path.is_file()
    assert "pixelle.tts_service_result.v1" in result_text
    assert '"status": "completed"' in result_text
    assert output_path.read_bytes() == b"audio-data"


@pytest.mark.asyncio
async def test_tts_service_does_not_duplicate_core_workflow_result_for_comfyui_failure(
    monkeypatch,
    tmp_path,
):
    output_path = tmp_path / "failed.wav"
    captured = {}

    async def fake_execute(
        workflow_input,
        workflow_params,
        workflow_info,
        *,
        backend_role="default",
        tts_workflow_trace_context=None,
    ):
        assert isinstance(tts_workflow_trace_context, dict)
        captured["trace_context"] = dict(tts_workflow_trace_context)
        return SimpleNamespace(
            status="failed",
            msg="WebSocket connection closed",
            audios=[],
            files=[],
            outputs={},
        )

    service = TTSService({"comfyui": {"tts": {}}})
    monkeypatch.setattr(service, "_execute_workflow", fake_execute)
    monkeypatch.setattr(service, "_validate_required_workflow_params", lambda *_args: None)

    with pytest.raises(Exception, match="WebSocket connection closed"):
        await service._call_comfyui_workflow(
            {
                "key": "selfhost/tts_edge.json",
                "source": "selfhost",
                "path": "workflows/selfhost/tts_edge.json",
            },
            text="failure trace",
            output_path=str(output_path),
        )

    artifact_path = Path(str(captured["trace_context"]["artifact_path"]))
    service_result_path = artifact_path.with_name("tts_service_result.md")
    service_result_text = service_result_path.read_text(encoding="utf-8")

    assert not artifact_path.with_name("tts_workflow_result.md").exists()
    assert service_result_path.is_file()
    assert '"status": "failed"' in service_result_text
    assert "WebSocket connection closed" in service_result_text


@pytest.mark.asyncio
async def test_tts_service_writes_trace_for_local_edge_tts(tmp_path, monkeypatch):
    output_path = tmp_path / "local.wav"
    calls = []

    async def fake_edge_tts(*, text, voice, rate, output_path):
        calls.append(
            {
                "text": text,
                "voice": voice,
                "rate": rate,
                "output_path": output_path,
            }
        )
        Path(output_path).write_bytes(b"local-audio")

    monkeypatch.setattr("pixelle_video.services.tts_service.edge_tts", fake_edge_tts)
    service = TTSService({"local": {"voice": "en-US-JennyNeural", "speed": 1.0}})

    returned_path = await service._call_local_tts(
        text="local trace",
        output_path=str(output_path),
    )

    artifacts = list((tmp_path / "prompt_traces" / "tts").glob("*/tts_workflow.md"))
    result_artifacts = [
        artifact.with_name("tts_workflow_result.md") for artifact in artifacts
    ]

    assert returned_path == str(output_path)
    assert calls[0]["text"] == "local trace"
    assert len(artifacts) == 1
    assert "local trace" in artifacts[0].read_text(encoding="utf-8")
    assert result_artifacts[0].is_file()


@pytest.mark.asyncio
async def test_tts_router_forwards_omnivoice_duration_and_reference_text(monkeypatch):
    core = _RecordingTtsCore()
    monkeypatch.setattr(tts_router, "get_audio_duration", lambda _path: 8.0)

    response = await tts_router.tts_synthesize(
        TTSSynthesizeRequest(
            text="short line",
            workflow="selfhost/tts_omnivoice_clone_duration_bf16.json",
            ref_audio="ref.wav",
            reference_audio_text="reference transcript",
            duration=8.0,
        ),
        core,
    )

    assert response.audio_path == "generated.wav"
    assert core.calls == [
        {
            "text": "short line",
            "workflow": "selfhost/tts_omnivoice_clone_duration_bf16.json",
            "ref_audio": "ref.wav",
            "reference_audio_text": "reference transcript",
            "duration": 8.0,
        }
    ]


def test_tts_request_rejects_duration_outside_pixelle_duration_range():
    with pytest.raises(ValidationError):
        TTSSynthesizeRequest(text="short line", duration=0.0)

    with pytest.raises(ValidationError):
        TTSSynthesizeRequest(text="short line", duration=60.5)


@pytest.mark.asyncio
async def test_tts_router_returns_422_for_missing_required_workflow_params():
    class _MissingRefAudioCore:
        async def tts(self, **_params):
            raise ValueError(
                "TTS workflow 'selfhost/tts_omnivoice_longform_bf16.json' "
                "missing required params: ref_audio"
            )

    with pytest.raises(tts_router.HTTPException) as exc_info:
        await tts_router.tts_synthesize(
            TTSSynthesizeRequest(
                text="long narration",
                workflow="selfhost/tts_omnivoice_longform_bf16.json",
            ),
            _MissingRefAudioCore(),
        )

    assert exc_info.value.status_code == 422
    assert "missing required params: ref_audio" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_tts_service_passes_omnivoice_duration_to_workflow(monkeypatch):
    captured = {}

    async def fake_execute(
        workflow_input,
        workflow_params,
        workflow_info,
        *,
        backend_role="default",
        tts_workflow_trace_context=None,
    ):
        captured["workflow_input"] = workflow_input
        captured["workflow_params"] = dict(workflow_params)
        captured["backend_role"] = backend_role
        return SimpleNamespace(status="completed", audios=["output.flac"], files=[], outputs={})

    class _Core:
        def _get_comfyui_backend_registry(self):
            class _Registry:
                def resolve_role_for_tts(self, workflow_key):
                    return "default"

            return _Registry()

    service = TTSService({"comfyui": {"tts": {}}}, core=_Core())
    monkeypatch.setattr(service, "_execute_workflow", fake_execute)
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None: {
            "key": "selfhost/tts_omnivoice_clone_duration_bf16.json",
            "path": "workflows/selfhost/tts_omnivoice_clone_duration_bf16.json",
            "source": "selfhost",
        },
    )

    await service(
        text="short line",
        workflow="selfhost/tts_omnivoice_clone_duration_bf16.json",
        ref_audio="ref.wav",
        ref_audio_text="legacy transcript",
        prompt_text="prompt transcript",
        reference_audio_text="reference transcript",
        duration=8.0,
    )

    assert captured["workflow_params"]["duration"] == 8.0
    assert captured["workflow_params"]["reference_audio_text"] == "reference transcript"
    assert "ref_audio_text" not in captured["workflow_params"]
    assert "prompt_text" not in captured["workflow_params"]
    assert captured["backend_role"] == "default"


@pytest.mark.asyncio
async def test_tts_service_maps_reference_audio_text_to_prompt_text_workflows(monkeypatch):
    captured = {}

    async def fake_execute(
        workflow_input,
        workflow_params,
        workflow_info,
        *,
        backend_role="default",
        tts_workflow_trace_context=None,
    ):
        captured["workflow_params"] = dict(workflow_params)
        captured["backend_role"] = backend_role
        return SimpleNamespace(status="completed", audios=["output.flac"], files=[], outputs={})

    service = TTSService({"comfyui": {"tts": {}}})
    monkeypatch.setattr(service, "_execute_workflow", fake_execute)
    monkeypatch.setattr(service, "_get_workflow_param_names", lambda _workflow_info: {"text", "prompt_text"})
    monkeypatch.setattr(service, "_validate_required_workflow_params", lambda *_args: None)

    await service._call_comfyui_workflow(
        {
            "key": "selfhost/custom_prompt_text.json",
            "path": "workflows/selfhost/custom_prompt_text.json",
            "source": "selfhost",
        },
        text="short line",
        reference_audio_text="reference transcript",
    )

    assert captured["workflow_params"]["prompt_text"] == "reference transcript"
    assert "reference_audio_text" not in captured["workflow_params"]
    assert captured["backend_role"] == "default"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_variant_params",
    [
        {"Text": "hidden"},
        {"Ref_Audio": "voice.wav"},
        {"Prompt_Text": "reference transcript"},
    ],
)
async def test_tts_service_rejects_case_variant_tts_workflow_params(
    monkeypatch,
    case_variant_params,
):
    service = TTSService({"comfyui": {"tts": {}}})
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None: {
            "key": "selfhost/tts_edge.json",
            "path": "workflows/selfhost/tts_edge.json",
            "source": "selfhost",
        },
    )
    monkeypatch.setattr(service, "_validate_required_workflow_params", lambda *_args: None)

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("case-variant TTS params must be rejected")

    monkeypatch.setattr(service, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="lowercase"):
        await service(
            text="hello",
            inference_mode="comfyui",
            workflow="selfhost/tts_edge.json",
            **case_variant_params,
        )


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
