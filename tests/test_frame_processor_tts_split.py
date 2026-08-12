from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.storyboard import StoryboardConfig, StoryboardFrame
from pixelle_video.services.frame_processor import FrameProcessor


class _RecordingTts:
    def __init__(self):
        self.calls = []

    async def __call__(self, **params):
        self.calls.append(params)
        return params["output_path"]


class _FakeCore:
    def __init__(self):
        self.tts = _RecordingTts()
        self.session_events = []
        self.session_stop_options = []
        self.session_backend_roles = []

    def _get_comfyui_backend_registry(self):
        return SimpleNamespace(resolve_role_for_tts=lambda workflow_key: "tts")

    @asynccontextmanager
    async def local_comfyui_workflow_session(
        self,
        *,
        stop_after_session=False,
        backend_role="default",
    ):
        self.session_stop_options.append(stop_after_session)
        self.session_backend_roles.append(backend_role)
        self.session_events.append("enter")
        try:
            yield
        finally:
            self.session_events.append("exit")


@pytest.mark.asyncio
async def test_frame_processor_external_only_splits_index_tts2_per_frame_audio(monkeypatch):
    core = _FakeCore()
    processor = FrameProcessor(core)
    frame = StoryboardFrame(
        index=0,
        narration="她停下来，把围巾重新系紧，然后抬头看了一眼泛白的天空，像是在等什么",
        image_prompt="p1",
    )
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-per-frame-split",
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_index2.json",
        tts_split_mode="external_only",
        max_chars_per_tts_segment=24,
        tts_boundary_search_radius=12,
    )

    async def fake_duration(_audio_path):
        return 1.0

    concat_calls = []
    monkeypatch.setattr(processor, "_get_audio_duration", fake_duration)
    monkeypatch.setattr(
        processor,
        "_concat_audio_files",
        lambda paths, output, **kwargs: concat_calls.append((paths, output, kwargs)),
        raising=False,
    )

    await processor._step_generate_audio(frame, config)

    synthesized_texts = [call["text"] for call in core.tts.calls]
    assert "".join(synthesized_texts) == frame.narration
    assert len(synthesized_texts) > 1
    assert all(Path(call["output_path"]).suffix == ".flac" for call in core.tts.calls)
    assert core.session_events == ["enter", "exit"]
    assert core.session_stop_options == [True]
    assert core.session_backend_roles == ["tts"]
    assert concat_calls
    assert concat_calls[0][2]["fade_ms"] == config.tts_audio_boundary_fade_ms


@pytest.mark.asyncio
async def test_frame_processor_single_index_tts2_uses_flac_source_and_wav_frame_audio(monkeypatch):
    core = _FakeCore()
    processor = FrameProcessor(core)
    frame = StoryboardFrame(
        index=0,
        narration="short narration",
        image_prompt="p1",
    )
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-per-frame-single",
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_index2.json",
    )

    async def fake_duration(_audio_path):
        return 1.0

    normalize_calls = []
    monkeypatch.setattr(processor, "_get_audio_duration", fake_duration)
    monkeypatch.setattr(
        processor,
        "_normalize_audio_for_frame",
        lambda source, output: normalize_calls.append((source, output)) or output,
        raising=False,
    )

    await processor._step_generate_audio(frame, config)

    assert len(core.tts.calls) == 1
    assert Path(core.tts.calls[0]["output_path"]).suffix == ".flac"
    assert normalize_calls
    assert Path(normalize_calls[0][0]).suffix == ".flac"
    assert Path(normalize_calls[0][1]).suffix == ".wav"
    assert Path(frame.audio_path).suffix == ".wav"
    assert core.session_events == ["enter", "exit"]
    assert core.session_stop_options == [True]
    assert core.session_backend_roles == ["tts"]
