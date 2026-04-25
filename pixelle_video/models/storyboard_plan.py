from __future__ import annotations

import hashlib
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StoryboardGenerationMode(str, Enum):
    SMART = "smart"
    PUNCTUATION = "punctuation"
    SENTENCE = "sentence"


class StoryboardCountMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class ScriptLengthMode(str, Enum):
    AUTO = "auto"
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    CUSTOM = "custom"


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int
    text: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "reason": self.reason,
        }


@dataclass
class StoryboardPlanFrame:
    index: int
    source_text: str
    narration_text: str
    visual_goal: str
    prompt_intent: str
    frame_id: str = ""
    shot_type: str | None = None
    shot_purpose: str | None = None
    primary_subject: str | None = None
    secondary_subjects: list[str] = field(default_factory=list)
    continuity_anchors: list[str] = field(default_factory=list)
    world_elements: list[str] = field(default_factory=list)
    source_start: int | None = None
    source_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "index": self.index,
            "source_text": self.source_text,
            "narration_text": self.narration_text,
            "visual_goal": self.visual_goal,
            "prompt_intent": self.prompt_intent,
            "shot_type": self.shot_type,
            "shot_purpose": self.shot_purpose,
            "primary_subject": self.primary_subject,
            "secondary_subjects": deepcopy(self.secondary_subjects),
            "continuity_anchors": deepcopy(self.continuity_anchors),
            "world_elements": deepcopy(self.world_elements),
            "source_start": self.source_start,
            "source_end": self.source_end,
            "metadata": deepcopy(self.metadata),
        }


@dataclass
class StoryboardPlan:
    plan_id: str
    revision: int
    mode: StoryboardGenerationMode
    count_mode: StoryboardCountMode
    requested_scene_count: int | None
    resolved_scene_count: int
    source_text: str
    source_digest: str
    frames: tuple[StoryboardPlanFrame, ...]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        mode: StoryboardGenerationMode | str,
        count_mode: StoryboardCountMode | str,
        requested_scene_count: int | None,
        source_text: str,
        frames: list[StoryboardPlanFrame],
        diagnostics: dict[str, Any] | None = None,
        plan_id: str | None = None,
        revision: int = 1,
    ) -> "StoryboardPlan":
        normalized_source = source_text.strip()
        if not normalized_source:
            raise ValueError("source_text must not be empty")
        if not frames:
            raise ValueError("StoryboardPlan requires at least one frame")
        if revision < 1:
            raise ValueError("revision must be at least 1")

        mode_value = StoryboardGenerationMode(mode)
        count_mode_value = StoryboardCountMode(count_mode)
        is_smart_manual = (
            mode_value == StoryboardGenerationMode.SMART
            and count_mode_value == StoryboardCountMode.MANUAL
        )
        if count_mode_value == StoryboardCountMode.MANUAL and mode_value != StoryboardGenerationMode.SMART:
            raise ValueError("manual count mode is only valid for smart mode")
        if is_smart_manual:
            if requested_scene_count != len(frames):
                raise ValueError("requested_scene_count must match frame count")
        elif requested_scene_count is not None:
            raise ValueError("requested_scene_count is only valid for smart manual mode")

        expected_indexes = list(range(1, len(frames) + 1))
        actual_indexes = [frame.index for frame in frames]
        if actual_indexes != expected_indexes:
            raise ValueError("frame indexes must start at 1 and be contiguous")

        digest = hashlib.sha256(normalized_source.encode("utf-8")).hexdigest()
        stable_plan_id = plan_id or f"plan_{uuid.uuid4().hex}"
        owned_frames: list[StoryboardPlanFrame] = []
        frame_ids: set[str] = set()
        for frame in frames:
            if not frame.narration_text.strip():
                raise ValueError("frame narration_text must not be empty")
            if frame.source_start is not None or frame.source_end is not None:
                if frame.source_start is None or frame.source_end is None:
                    raise ValueError("source_start and source_end must be set together")
                if not 0 <= frame.source_start <= frame.source_end <= len(normalized_source):
                    raise ValueError("frame source range must index StoryboardPlan.source_text")
            _validate_source_spans(frame.metadata, normalized_source)
            frame_id = frame.frame_id or f"frame_{frame.index:04d}_{uuid.uuid4().hex[:8]}"
            if frame_id in frame_ids:
                raise ValueError("frame_id must be unique")
            frame_ids.add(frame_id)
            owned_frames.append(
                StoryboardPlanFrame(
                    index=frame.index,
                    source_text=frame.source_text,
                    narration_text=frame.narration_text,
                    visual_goal=frame.visual_goal,
                    prompt_intent=frame.prompt_intent,
                    frame_id=frame_id,
                    shot_type=frame.shot_type,
                    shot_purpose=frame.shot_purpose,
                    primary_subject=frame.primary_subject,
                    secondary_subjects=deepcopy(frame.secondary_subjects),
                    continuity_anchors=deepcopy(frame.continuity_anchors),
                    world_elements=deepcopy(frame.world_elements),
                    source_start=frame.source_start,
                    source_end=frame.source_end,
                    metadata=deepcopy(frame.metadata),
                )
            )

        return cls(
            plan_id=stable_plan_id,
            revision=revision,
            mode=mode_value,
            count_mode=count_mode_value,
            requested_scene_count=requested_scene_count,
            resolved_scene_count=len(owned_frames),
            source_text=normalized_source,
            source_digest=digest,
            frames=tuple(owned_frames),
            diagnostics=deepcopy(diagnostics or {}),
        )

    def narration_texts(self) -> list[str]:
        return [frame.narration_text for frame in self.frames]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "revision": self.revision,
            "mode": self.mode.value,
            "count_mode": self.count_mode.value,
            "requested_scene_count": self.requested_scene_count,
            "resolved_scene_count": self.resolved_scene_count,
            "source_text": self.source_text,
            "source_digest": self.source_digest,
            "frames": [frame.to_dict() for frame in self.frames],
            "diagnostics": deepcopy(self.diagnostics),
        }


def _validate_source_spans(metadata: dict[str, Any], source_text: str) -> None:
    source_spans = metadata.get("source_spans")
    if source_spans is None:
        return
    if not isinstance(source_spans, list):
        raise ValueError("source_spans must be a list")

    previous_start = -1
    previous_end = -1
    for span in source_spans:
        if isinstance(span, SourceSpan):
            start = span.start
            end = span.end
            text = span.text
            reason = span.reason
        elif isinstance(span, dict):
            start = span.get("start")
            end = span.get("end")
            text = span.get("text")
            reason = span.get("reason", "")
        else:
            raise ValueError("source_spans entries must be SourceSpan or dict")

        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError("source_spans start and end must be integers")
        if start < previous_start:
            raise ValueError("source_spans must be sorted by start")
        if not 0 <= start <= end <= len(source_text):
            raise ValueError("source_spans range must index StoryboardPlan.source_text")
        if not isinstance(text, str) or text != source_text[start:end]:
            raise ValueError("source_spans text must match source_text slice")
        if start < previous_end and not str(reason).strip():
            raise ValueError("overlapping source_spans must include a reason")

        previous_start = start
        previous_end = max(previous_end, end)
