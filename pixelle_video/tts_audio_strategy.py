from typing import Final, Literal, cast


TTSAudioStrategy = Literal["auto", "per_frame", "master_track"]

AUTO_TTS_AUDIO_STRATEGY: Final[TTSAudioStrategy] = "auto"
PER_FRAME_TTS_AUDIO_STRATEGY: Final[TTSAudioStrategy] = "per_frame"
MASTER_TRACK_TTS_AUDIO_STRATEGY: Final[TTSAudioStrategy] = "master_track"
DEFAULT_TTS_AUDIO_STRATEGY: Final[TTSAudioStrategy] = AUTO_TTS_AUDIO_STRATEGY
SUPPORTED_TTS_AUDIO_STRATEGIES: Final[tuple[TTSAudioStrategy, ...]] = (
    AUTO_TTS_AUDIO_STRATEGY,
    PER_FRAME_TTS_AUDIO_STRATEGY,
    MASTER_TRACK_TTS_AUDIO_STRATEGY,
)


def validate_tts_audio_strategy(value: str) -> TTSAudioStrategy:
    if value not in SUPPORTED_TTS_AUDIO_STRATEGIES:
        supported = ", ".join(SUPPORTED_TTS_AUDIO_STRATEGIES)
        raise ValueError(f"tts_audio_strategy must be one of: {supported}")
    return cast(TTSAudioStrategy, value)
