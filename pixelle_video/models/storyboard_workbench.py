from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class FrameLockPolicy(str, Enum):
    UNLOCKED = "unlocked"
    LOCKED_CONTENT = "locked_content"
    LOCKED_PROMPT = "locked_prompt"
    LOCKED_ARTIFACT = "locked_artifact"
    LOCKED_ALL = "locked_all"


class FrameStaleFlag(str, Enum):
    PROMPT_PLAN = "prompt_plan"
    IMAGE_ARTIFACT = "image_artifact"
    VIDEO_SEGMENT = "video_segment"
    FINAL_VIDEO = "final_video"


@dataclass(frozen=True)
class StoryboardFrameWorkbenchState:
    frame_id: str
    prompt_plan_id: str | None = None
    selected_image_artifact_id: str | None = None
    selected_image_version_id: str | None = None
    candidate_image_version_ids: tuple[str, ...] = ()
    lock_policy: FrameLockPolicy | str = FrameLockPolicy.UNLOCKED
    stale_flags: tuple[FrameStaleFlag | str, ...] = field(default_factory=tuple)
    last_generation_job_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_reference_id("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "prompt_plan_id",
            _optional_reference_id("prompt_plan_id", self.prompt_plan_id),
        )
        object.__setattr__(
            self,
            "selected_image_artifact_id",
            _optional_reference_id(
                "selected_image_artifact_id",
                self.selected_image_artifact_id,
            ),
        )
        object.__setattr__(
            self,
            "selected_image_version_id",
            _optional_reference_id(
                "selected_image_version_id",
                self.selected_image_version_id,
            ),
        )
        object.__setattr__(
            self,
            "candidate_image_version_ids",
            _normalize_reference_tuple(
                "candidate_image_version_ids",
                self.candidate_image_version_ids,
            ),
        )
        object.__setattr__(self, "lock_policy", _normalize_lock_policy(self.lock_policy))
        object.__setattr__(self, "stale_flags", _normalize_stale_flags(self.stale_flags))
        object.__setattr__(
            self,
            "last_generation_job_id",
            _optional_reference_id("last_generation_job_id", self.last_generation_job_id),
        )

    @property
    def is_image_artifact_locked(self) -> bool:
        return self.lock_policy in {
            FrameLockPolicy.LOCKED_ARTIFACT,
            FrameLockPolicy.LOCKED_ALL,
        }

    @property
    def can_auto_replace_selected_image(self) -> bool:
        return not self.is_image_artifact_locked

    def with_stale_flags(
        self,
        flags: tuple[FrameStaleFlag | str, ...] | list[FrameStaleFlag | str],
    ) -> "StoryboardFrameWorkbenchState":
        return replace(
            self,
            stale_flags=_merge_stale_flags(self.stale_flags, flags),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "prompt_plan_id": self.prompt_plan_id,
            "selected_image_artifact_id": self.selected_image_artifact_id,
            "selected_image_version_id": self.selected_image_version_id,
            "candidate_image_version_ids": list(self.candidate_image_version_ids),
            "lock_policy": self.lock_policy.value,
            "stale_flags": [flag.value for flag in self.stale_flags],
            "last_generation_job_id": self.last_generation_job_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StoryboardFrameWorkbenchState":
        if not isinstance(payload, Mapping):
            raise ValueError("StoryboardFrameWorkbenchState payload must be a mapping")
        candidate_image_version_ids = payload.get("candidate_image_version_ids")
        if candidate_image_version_ids is None:
            candidate_image_version_ids = ()
        return cls(
            frame_id=payload.get("frame_id", ""),
            prompt_plan_id=payload.get("prompt_plan_id"),
            selected_image_artifact_id=payload.get("selected_image_artifact_id"),
            selected_image_version_id=payload.get("selected_image_version_id"),
            candidate_image_version_ids=candidate_image_version_ids,
            lock_policy=payload.get("lock_policy", FrameLockPolicy.UNLOCKED),
            stale_flags=tuple(payload.get("stale_flags") or ()),
            last_generation_job_id=payload.get("last_generation_job_id"),
        )


def mark_frame_stale_after_prompt_plan_change(
    state: StoryboardFrameWorkbenchState,
) -> StoryboardFrameWorkbenchState:
    return state.with_stale_flags(
        [
            FrameStaleFlag.IMAGE_ARTIFACT,
            FrameStaleFlag.VIDEO_SEGMENT,
            FrameStaleFlag.FINAL_VIDEO,
        ]
    )


def mark_frame_stale_after_selected_image_change(
    state: StoryboardFrameWorkbenchState,
) -> StoryboardFrameWorkbenchState:
    return state.with_stale_flags(
        [
            FrameStaleFlag.VIDEO_SEGMENT,
            FrameStaleFlag.FINAL_VIDEO,
        ]
    )


def _require_reference_id(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    normalized = value.strip()
    if _looks_like_path(normalized):
        raise ValueError(f"{field_name} must be a domain ID, not a local path")
    return normalized


def _optional_reference_id(field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        return None
    return _require_reference_id(field_name, stripped)


def _looks_like_path(value: str) -> bool:
    return (
        "\\" in value
        or "/" in value
        or ":" in value
        or value in {".", ".."}
        or value.startswith("~")
    )


def _normalize_reference_tuple(field_name: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(_require_reference_id(field_name, item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _normalize_lock_policy(value: FrameLockPolicy | str) -> FrameLockPolicy:
    if isinstance(value, FrameLockPolicy):
        return value
    aliases = {
        "none": FrameLockPolicy.UNLOCKED,
        "lock_text": FrameLockPolicy.LOCKED_CONTENT,
        "lock_prompt": FrameLockPolicy.LOCKED_PROMPT,
        "lock_image": FrameLockPolicy.LOCKED_ARTIFACT,
        "lock_all": FrameLockPolicy.LOCKED_ALL,
    }
    normalized = aliases.get(str(value), value)
    return FrameLockPolicy(normalized)


def _normalize_stale_flags(value: Any) -> tuple[FrameStaleFlag, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("stale_flags must be a list or tuple")
    return _merge_stale_flags((), value)


def _merge_stale_flags(
    existing: tuple[FrameStaleFlag, ...],
    incoming: tuple[FrameStaleFlag | str, ...] | list[FrameStaleFlag | str],
) -> tuple[FrameStaleFlag, ...]:
    normalized = list(existing)
    for item in incoming:
        flag = _normalize_stale_flag(item)
        if flag not in normalized:
            normalized.append(flag)
    return tuple(normalized)


def _normalize_stale_flag(value: FrameStaleFlag | str) -> FrameStaleFlag:
    if isinstance(value, FrameStaleFlag):
        return value
    aliases = {"image": FrameStaleFlag.IMAGE_ARTIFACT}
    normalized = aliases.get(str(value), value)
    return FrameStaleFlag(normalized)


__all__ = [
    "FrameLockPolicy",
    "FrameStaleFlag",
    "StoryboardFrameWorkbenchState",
    "mark_frame_stale_after_prompt_plan_change",
    "mark_frame_stale_after_selected_image_change",
]
