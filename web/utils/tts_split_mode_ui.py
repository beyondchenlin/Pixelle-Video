from typing import Any, Mapping, MutableMapping

from pixelle_video.tts_split_strategy import DEFAULT_TTS_SPLIT_MODE, SUPPORTED_TTS_SPLIT_MODES

TTS_SPLIT_SETTING_KEYS = (
    "tts_split_mode",
    "max_chars_per_tts_segment",
    "tts_split_overflow_policy",
    "tts_boundary_search_radius",
    "tts_soft_overflow_chars",
    "tts_audio_boundary_fade_ms",
    "tts_sentence_joiner_mode",
    "caption_punctuation_mode",
    "preserve_natural_punctuation",
)


def get_tts_split_mode_default(configured_mode: Any) -> str:
    if configured_mode in SUPPORTED_TTS_SPLIT_MODES:
        return str(configured_mode)
    return DEFAULT_TTS_SPLIT_MODE


def copy_tts_split_settings(source: Mapping[str, Any], target: MutableMapping[str, Any]) -> None:
    mode = source.get("tts_split_mode")
    if mode in SUPPORTED_TTS_SPLIT_MODES:
        target["tts_split_mode"] = str(mode)

    for key in TTS_SPLIT_SETTING_KEYS:
        if key == "tts_split_mode":
            continue
        value = source.get(key)
        if value is not None:
            target[key] = value
