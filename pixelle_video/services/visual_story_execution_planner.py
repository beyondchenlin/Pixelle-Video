from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_story_execution import (
    DEFAULT_VISUAL_STORY_BATCH_SIZE,
    DEFAULT_VISUAL_STORY_CONTEXT_BUDGET,
    ContinuityLedger,
    VisualStoryExecutionBatch,
    VisualStoryExecutionPlan,
    VisualStoryFrameRef,
)


@dataclass(frozen=True)
class VisualStoryExecutionPlanner:
    """Deterministic local planner for visual-story batch execution."""

    default_batch_size: int = DEFAULT_VISUAL_STORY_BATCH_SIZE
    default_context_budget: int = DEFAULT_VISUAL_STORY_CONTEXT_BUDGET

    def plan(
        self,
        *,
        source_text: str,
        storyboard_plan: Any,
        selected_visual_route: Mapping[str, Any] | None = None,
        batch_size: int | None = None,
        max_context_chars: int | None = None,
        continuity_ledger: Mapping[str, Any] | ContinuityLedger | None = None,
    ) -> VisualStoryExecutionPlan:
        frames = _storyboard_frames(storyboard_plan)
        if not frames:
            raise ValueError("storyboard_plan must contain at least one frame")
        resolved_batch_size = max(1, int(batch_size or self.default_batch_size))
        resolved_budget = max(1200, int(max_context_chars or self.default_context_budget))
        refs = [VisualStoryFrameRef.from_storyboard_frame(frame, i) for i, frame in enumerate(frames)]
        route_id = _route_id(selected_visual_route)
        batches = []
        for batch_index, start in enumerate(range(0, len(refs), resolved_batch_size)):
            batches.append(
                VisualStoryExecutionBatch(
                    batch_id=f"visual-story-batch-{batch_index + 1:03d}",
                    batch_index=batch_index,
                    frame_refs=tuple(refs[start : start + resolved_batch_size]),
                    max_context_chars=resolved_budget,
                    requires_previous_continuity_digest=batch_index > 0,
                )
            )
        ledger = continuity_ledger if isinstance(continuity_ledger, ContinuityLedger) else ContinuityLedger.from_mapping(continuity_ledger)
        if selected_visual_route and not ledger.route_digest:
            ledger = ContinuityLedger(
                route_digest=_route_digest(selected_visual_route),
                ip_identity_digest=ledger.ip_identity_digest,
                style_digest=ledger.style_digest,
                previous_batch_digest=ledger.previous_batch_digest,
                recurring_symbols=ledger.recurring_symbols,
                warnings=ledger.warnings,
            )
        return VisualStoryExecutionPlan(
            execution_plan_id=f"visual-story-exec-{_digest(source_text or route_id)}",
            source_text_digest=_digest(source_text),
            selected_route_id=route_id,
            batch_size=resolved_batch_size,
            max_context_chars=resolved_budget,
            batches=tuple(batches),
            continuity_ledger=ledger,
        )


def _storyboard_frames(storyboard_plan: Any) -> tuple[Any, ...]:
    if storyboard_plan is None:
        return ()
    if hasattr(storyboard_plan, "frames"):
        return tuple(storyboard_plan.frames)
    if isinstance(storyboard_plan, Mapping):
        return tuple(storyboard_plan.get("frames") or ())
    return ()


def _route_id(route: Mapping[str, Any] | None) -> str:
    if not isinstance(route, Mapping):
        return "default_visual_route"
    return str(route.get("route_id") or route.get("id") or "default_visual_route").strip() or "default_visual_route"


def _route_digest(route: Mapping[str, Any]) -> str:
    return " | ".join(str(route.get(k) or "").strip() for k in ("route_id", "route_name", "route_type", "visual_premise", "recommended_ip_role") if route.get(k))


def _digest(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


__all__ = ["VisualStoryExecutionPlanner"]
