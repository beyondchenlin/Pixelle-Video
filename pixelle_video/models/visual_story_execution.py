from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]

DEFAULT_VISUAL_STORY_BATCH_SIZE = 4
DEFAULT_VISUAL_STORY_CONTEXT_BUDGET = 9000
VISUAL_STORY_EXECUTION_PLAN_VERSION = "v5_loop_plan"


class VisualStoryBatchTask(str, Enum):
    FRAME_VISUAL_PLAN = "frame_visual_plan"
    FRAME_IP_FUSION_PLAN = "frame_ip_fusion_plan"
    IMAGE_PROMPT_GENERATION = "image_prompt_generation"
    VISUAL_ANCHOR_INTEGRATION = "visual_anchor_integration"
    QUALITY_GATE = "quality_gate"


class VisualStoryBatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FALLBACK_USED = "fallback_used"
    FAILED = "failed"


@dataclass(frozen=True)
class VisualStoryFrameRef:
    frame_id: str
    frame_index: int
    source_text: str = ""
    visual_goal: str = ""
    prompt_intent: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _required_text(self.frame_id, "frame_id"))
        object.__setattr__(
            self, "frame_index", _int_value(self.frame_index, "frame_index", minimum=0)
        )
        object.__setattr__(self, "source_text", _optional_text(self.source_text))
        object.__setattr__(self, "visual_goal", _optional_text(self.visual_goal))
        object.__setattr__(self, "prompt_intent", _optional_text(self.prompt_intent))

    @classmethod
    def from_storyboard_frame(cls, frame: Any, index: int) -> "VisualStoryFrameRef":
        return cls(
            frame_id=str(getattr(frame, "frame_id", "") or f"frame-{index + 1}"),
            frame_index=int(getattr(frame, "index", index) or index),
            source_text=str(getattr(frame, "source_text", "") or ""),
            visual_goal=str(getattr(frame, "visual_goal", "") or ""),
            prompt_intent=str(getattr(frame, "prompt_intent", "") or ""),
        )

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "VisualStoryFrameRef":
        return cls(
            frame_id=source.get("frame_id") or source.get("id") or "",
            frame_index=source.get("frame_index", source.get("index", 0)),
            source_text=source.get("source_text") or source.get("frame_source_text") or "",
            visual_goal=source.get("visual_goal") or "",
            prompt_intent=source.get("prompt_intent") or "",
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "frame_id": self.frame_id,
            "frame_index": self.frame_index,
            "source_text": self.source_text,
            "visual_goal": self.visual_goal,
            "prompt_intent": self.prompt_intent,
        }


@dataclass(frozen=True)
class VisualStoryExecutionBatch:
    batch_id: str
    batch_index: int
    frame_refs: Sequence[VisualStoryFrameRef | Mapping[str, Any]]
    tasks: Sequence[VisualStoryBatchTask | str] = (
        VisualStoryBatchTask.FRAME_VISUAL_PLAN,
        VisualStoryBatchTask.FRAME_IP_FUSION_PLAN,
        VisualStoryBatchTask.IMAGE_PROMPT_GENERATION,
        VisualStoryBatchTask.VISUAL_ANCHOR_INTEGRATION,
        VisualStoryBatchTask.QUALITY_GATE,
    )
    max_context_chars: int = DEFAULT_VISUAL_STORY_CONTEXT_BUDGET
    requires_previous_continuity_digest: bool = False
    status: VisualStoryBatchStatus | str = VisualStoryBatchStatus.PENDING
    fallback_used: bool = False
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "batch_id", _required_text(self.batch_id, "batch_id"))
        object.__setattr__(
            self, "batch_index", _int_value(self.batch_index, "batch_index", minimum=0)
        )
        refs = tuple(
            ref if isinstance(ref, VisualStoryFrameRef) else VisualStoryFrameRef.from_mapping(ref)
            for ref in self.frame_refs
        )
        if not refs:
            raise ValueError("frame_refs must not be empty")
        object.__setattr__(self, "frame_refs", refs)
        object.__setattr__(
            self,
            "tasks",
            tuple(_enum_value(task, VisualStoryBatchTask, "tasks") for task in self.tasks),
        )
        object.__setattr__(
            self,
            "max_context_chars",
            _int_value(self.max_context_chars, "max_context_chars", minimum=1200),
        )
        object.__setattr__(
            self,
            "requires_previous_continuity_digest",
            bool(self.requires_previous_continuity_digest),
        )
        object.__setattr__(
            self, "status", _enum_value(self.status, VisualStoryBatchStatus, "status")
        )
        object.__setattr__(self, "fallback_used", bool(self.fallback_used))
        object.__setattr__(self, "fallback_reason", _optional_text(self.fallback_reason) or None)

    @property
    def frame_ids(self) -> tuple[str, ...]:
        return tuple(ref.frame_id for ref in self.frame_refs)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "batch_id": self.batch_id,
            "batch_index": self.batch_index,
            "frame_refs": [ref.to_dict() for ref in self.frame_refs],
            "frame_ids": list(self.frame_ids),
            "tasks": [task.value for task in self.tasks],
            "max_context_chars": self.max_context_chars,
            "requires_previous_continuity_digest": self.requires_previous_continuity_digest,
            "status": self.status.value,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class ContinuityLedger:
    route_digest: str = ""
    ip_identity_digest: str = ""
    style_digest: str = ""
    previous_batch_digest: str = ""
    recurring_symbols: Sequence[Any] = ()
    warnings: Sequence[Any] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_digest", _optional_text(self.route_digest))
        object.__setattr__(self, "ip_identity_digest", _optional_text(self.ip_identity_digest))
        object.__setattr__(self, "style_digest", _optional_text(self.style_digest))
        object.__setattr__(
            self, "previous_batch_digest", _optional_text(self.previous_batch_digest)
        )
        object.__setattr__(self, "recurring_symbols", _text_tuple(self.recurring_symbols))
        object.__setattr__(self, "warnings", _text_tuple(self.warnings))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None) -> "ContinuityLedger":
        data = dict(source or {})
        return cls(
            route_digest=data.get("route_digest", ""),
            ip_identity_digest=data.get("ip_identity_digest", ""),
            style_digest=data.get("style_digest", ""),
            previous_batch_digest=data.get("previous_batch_digest", ""),
            recurring_symbols=data.get("recurring_symbols", ()),
            warnings=data.get("warnings", ()),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "route_digest": self.route_digest,
            "ip_identity_digest": self.ip_identity_digest,
            "style_digest": self.style_digest,
            "previous_batch_digest": self.previous_batch_digest,
            "recurring_symbols": list(self.recurring_symbols),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class VisualStoryExecutionPlan:
    execution_plan_id: str
    source_text_digest: str
    selected_route_id: str
    batches: Sequence[VisualStoryExecutionBatch | Mapping[str, Any]]
    batch_size: int = DEFAULT_VISUAL_STORY_BATCH_SIZE
    max_context_chars: int = DEFAULT_VISUAL_STORY_CONTEXT_BUDGET
    continuity_ledger: ContinuityLedger | Mapping[str, Any] = field(
        default_factory=ContinuityLedger
    )
    version: str = VISUAL_STORY_EXECUTION_PLAN_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "execution_plan_id", _required_text(self.execution_plan_id, "execution_plan_id")
        )
        object.__setattr__(
            self,
            "source_text_digest",
            _required_text(self.source_text_digest, "source_text_digest"),
        )
        object.__setattr__(
            self, "selected_route_id", _required_text(self.selected_route_id, "selected_route_id")
        )
        object.__setattr__(self, "batch_size", _int_value(self.batch_size, "batch_size", minimum=1))
        object.__setattr__(
            self,
            "max_context_chars",
            _int_value(self.max_context_chars, "max_context_chars", minimum=1200),
        )
        batches = tuple(
            batch
            if isinstance(batch, VisualStoryExecutionBatch)
            else VisualStoryExecutionBatch(**dict(batch))
            for batch in self.batches
        )
        if not batches:
            raise ValueError("batches must not be empty")
        batch_ids = tuple(batch.batch_id for batch in batches)
        duplicate_batch_ids = _duplicates(batch_ids)
        if duplicate_batch_ids:
            raise ValueError(f"batch_id values must be unique: {duplicate_batch_ids!r}")
        batch_indexes = tuple(batch.batch_index for batch in batches)
        if batch_indexes != tuple(range(len(batches))):
            raise ValueError("batch_index values must be contiguous and ordered from zero")
        frame_ids = tuple(frame_id for batch in batches for frame_id in batch.frame_ids)
        duplicate_frame_ids = _duplicates(frame_ids)
        if duplicate_frame_ids:
            raise ValueError(
                f"frame_id values must be unique across batches: {duplicate_frame_ids!r}"
            )
        if any(len(batch.frame_refs) > self.batch_size for batch in batches):
            raise ValueError("batch frame count must not exceed batch_size")
        object.__setattr__(self, "batches", batches)
        if not isinstance(self.continuity_ledger, ContinuityLedger):
            object.__setattr__(
                self, "continuity_ledger", ContinuityLedger.from_mapping(self.continuity_ledger)
            )
        object.__setattr__(
            self, "version", _optional_text(self.version) or VISUAL_STORY_EXECUTION_PLAN_VERSION
        )

    @property
    def frame_count(self) -> int:
        return sum(len(batch.frame_refs) for batch in self.batches)

    @property
    def frame_ids(self) -> tuple[str, ...]:
        return tuple(frame_id for batch in self.batches for frame_id in batch.frame_ids)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "execution_plan_id": self.execution_plan_id,
            "source_text_digest": self.source_text_digest,
            "selected_route_id": self.selected_route_id,
            "batch_size": self.batch_size,
            "max_context_chars": self.max_context_chars,
            "frame_count": self.frame_count,
            "batches": [batch.to_dict() for batch in self.batches],
            "continuity_ledger": self.continuity_ledger.to_dict(),
            "version": self.version,
        }


@dataclass(frozen=True)
class VisualStoryLoopResult:
    execution_plan: VisualStoryExecutionPlan
    frame_visual_plans: Sequence[Mapping[str, Any]]
    frame_ip_fusion_plans: Sequence[Mapping[str, Any]]
    prompt_context: Mapping[str, Any]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "execution_plan": self.execution_plan.to_dict(),
            "frame_visual_plans": [dict(item) for item in self.frame_visual_plans],
            "frame_ip_fusion_plans": [dict(item) for item in self.frame_ip_fusion_plans],
            "prompt_context": dict(self.prompt_context),
            "diagnostics": dict(self.diagnostics),
        }


def _required_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        value = value.value
    return str(value).strip()


def _text_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    elif not isinstance(values, Sequence):
        values = (values,)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _optional_text(value)
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return tuple(result)


def _int_value(value: Any, field_name: str, *, minimum: int = 0) -> int:
    try:
        if isinstance(value, bool):
            raise TypeError
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if result < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return result


def _enum_value(value: Any, enum_cls: type[Enum], field_name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = _optional_text(value)
    for item in enum_cls:
        if text == item.value or text.lower() == item.name.lower():
            return item
    raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")


def _digest(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def _duplicates(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return tuple(duplicates)


__all__ = [
    "DEFAULT_VISUAL_STORY_BATCH_SIZE",
    "DEFAULT_VISUAL_STORY_CONTEXT_BUDGET",
    "VISUAL_STORY_EXECUTION_PLAN_VERSION",
    "VisualStoryBatchStatus",
    "VisualStoryBatchTask",
    "VisualStoryExecutionBatch",
    "VisualStoryExecutionPlan",
    "VisualStoryFrameRef",
    "VisualStoryLoopResult",
    "ContinuityLedger",
]
