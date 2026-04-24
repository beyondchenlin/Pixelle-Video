from pathlib import Path
from typing import Any, Iterable

INDEX_TTS2_WORKFLOW_STEMS = frozenset({"tts_index2", "indextts2", "index_tts2"})
REF_AUDIO_TEXT_WORKFLOW_PARAMS = ("prompt_text", "reference_audio_text")


def is_index_tts2_workflow_key(workflow_key: Any) -> bool:
    workflow_stem = Path(str(workflow_key or "")).stem.lower()
    return workflow_stem in INDEX_TTS2_WORKFLOW_STEMS


def build_ref_audio_text_params(
    ref_audio_text: Any,
    workflow_param_names: Iterable[str] | None,
) -> dict[str, str]:
    text = str(ref_audio_text or "").strip()
    if not text:
        return {}

    param_names = set(workflow_param_names or ())
    if not param_names:
        return {"prompt_text": text}

    return {
        param_name: text
        for param_name in REF_AUDIO_TEXT_WORKFLOW_PARAMS
        if param_name in param_names
    }
