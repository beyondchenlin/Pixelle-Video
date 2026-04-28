from typing import Final, Literal

TtsSplitMode = Literal["internal_only", "external_only"]

INTERNAL_ONLY_TTS_SPLIT_MODE: Final[TtsSplitMode] = "internal_only"
EXTERNAL_ONLY_TTS_SPLIT_MODE: Final[TtsSplitMode] = "external_only"

DEFAULT_TTS_SPLIT_MODE: Final[TtsSplitMode] = EXTERNAL_ONLY_TTS_SPLIT_MODE
SUPPORTED_TTS_SPLIT_MODES: Final[tuple[TtsSplitMode, ...]] = (
    INTERNAL_ONLY_TTS_SPLIT_MODE,
    EXTERNAL_ONLY_TTS_SPLIT_MODE,
)


def validate_tts_split_mode(value: str) -> TtsSplitMode:
    normalized = (value or DEFAULT_TTS_SPLIT_MODE).strip().lower()
    if normalized in SUPPORTED_TTS_SPLIT_MODES:
        return normalized  # type: ignore[return-value]

    supported = ", ".join(SUPPORTED_TTS_SPLIT_MODES)
    raise ValueError(f"tts_split_mode must be one of: {supported}")
