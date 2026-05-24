from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TTS_WORKFLOW_PARAM_KEYS = frozenset(
    {
        "audio",
        "duration",
        "emotion",
        "input_audio",
        "lang",
        "language",
        "output_path",
        "pitch",
        "prompt",
        "prompt_text",
        "rate",
        "ref_audio",
        "ref_audio_text",
        "reference_audio",
        "reference_audio_text",
        "seed",
        "speaker",
        "speaker_id",
        "speed",
        "style",
        "text",
        "voice",
        "voice_id",
        "volume",
    }
)
TTS_WORKFLOW_PARAM_SUFFIXES = ("audio",)


def is_tts_workflow_param_name(name: str) -> bool:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return False
    return normalized in TTS_WORKFLOW_PARAM_KEYS or normalized.endswith(
        TTS_WORKFLOW_PARAM_SUFFIXES
    )


def workflow_params_look_like_tts_generation(
    workflow_params: Mapping[str, Any],
) -> bool:
    for key, value in workflow_params.items():
        name = str(key or "").strip()
        if not name or value in (None, "", [], {}):
            continue
        if not is_tts_workflow_param_name(name):
            return False
    return True


def workflow_params_have_case_variant_tts_key(
    workflow_params: Mapping[str, Any],
) -> bool:
    for key, value in workflow_params.items():
        name = str(key or "").strip()
        if not name or value in (None, "", [], {}):
            continue
        if name != name.lower() and is_tts_workflow_param_name(name):
            return True
    return False


def reject_case_variant_tts_workflow_params(
    workflow_params: Mapping[str, Any],
) -> None:
    if workflow_params_have_case_variant_tts_key(workflow_params):
        raise ValueError("TTS workflow params must use exact lowercase keys")
