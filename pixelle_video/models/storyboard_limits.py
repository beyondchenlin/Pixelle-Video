from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN = 1
DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_DEFAULT = 60
DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX = 200


@dataclass(frozen=True)
class StoryboardGenerationLimits:
    min_scene_count: int = 1
    max_scene_count: int = 30
    deterministic_max_scene_count_limit: int = (
        DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX
    )

    def __post_init__(self) -> None:
        _require_positive_int("min_scene_count", self.min_scene_count)
        _require_positive_int("max_scene_count", self.max_scene_count)
        _require_positive_int(
            "deterministic_max_scene_count_limit",
            self.deterministic_max_scene_count_limit,
        )
        if self.min_scene_count > self.max_scene_count:
            raise ValueError("min_scene_count must not exceed max_scene_count")
        if (
            self.deterministic_max_scene_count_limit
            > DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX
        ):
            raise ValueError(
                "deterministic_max_scene_count_limit must not exceed "
                f"{DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX}"
            )

    @property
    def default_deterministic_max_scene_count(self) -> int:
        return min(
            DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_DEFAULT,
            self.deterministic_max_scene_count_limit,
        )


def storyboard_generation_limits_from_config(config: Any = None) -> StoryboardGenerationLimits:
    if config is None:
        return DEFAULT_STORYBOARD_GENERATION_LIMITS
    if isinstance(config, Mapping) and isinstance(config.get("storyboard"), Mapping):
        config = config["storyboard"]
    elif hasattr(config, "storyboard"):
        config = getattr(config, "storyboard")
    return StoryboardGenerationLimits(
        min_scene_count=_read_config_value(
            config,
            "min_scene_count",
            DEFAULT_STORYBOARD_GENERATION_LIMITS.min_scene_count,
        ),
        max_scene_count=_read_config_value(
            config,
            "max_scene_count",
            DEFAULT_STORYBOARD_GENERATION_LIMITS.max_scene_count,
        ),
        deterministic_max_scene_count_limit=_read_config_value(
            config,
            "deterministic_max_scene_count_limit",
            DEFAULT_STORYBOARD_GENERATION_LIMITS.deterministic_max_scene_count_limit,
        ),
    )


def current_storyboard_generation_limits() -> StoryboardGenerationLimits:
    from pixelle_video.config import config_manager

    return storyboard_generation_limits_from_config(config_manager.config)


def _read_config_value(config: Any, key: str, default: int) -> int:
    if isinstance(config, Mapping):
        value = config.get(key, default)
    else:
        value = getattr(config, key, default)
    _require_positive_int(key, value)
    return value


def _require_positive_int(field_name: str, value: Any) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


__all__ = [
    "DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_DEFAULT",
    "DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX",
    "DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN",
    "DEFAULT_STORYBOARD_GENERATION_LIMITS",
    "StoryboardGenerationLimits",
    "current_storyboard_generation_limits",
    "storyboard_generation_limits_from_config",
]


DEFAULT_STORYBOARD_GENERATION_LIMITS = StoryboardGenerationLimits()
