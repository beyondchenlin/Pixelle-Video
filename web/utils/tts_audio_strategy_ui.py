from typing import Any, Mapping, MutableMapping

from pixelle_video.tts_audio_strategy import (
    DEFAULT_TTS_AUDIO_STRATEGY,
    SUPPORTED_TTS_AUDIO_STRATEGIES,
)


def get_tts_audio_strategy_default(configured_strategy: Any) -> str:
    """Return a safe UI default for TTS audio strategy selection."""
    if configured_strategy in SUPPORTED_TTS_AUDIO_STRATEGIES:
        return str(configured_strategy)
    return DEFAULT_TTS_AUDIO_STRATEGY


def copy_tts_audio_strategy(source: Mapping[str, Any], target: MutableMapping[str, Any]) -> None:
    """Copy a supported TTS audio strategy from one param dict to another."""
    strategy = source.get("tts_audio_strategy")
    if strategy in SUPPORTED_TTS_AUDIO_STRATEGIES:
        target["tts_audio_strategy"] = str(strategy)
