from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_planning import (
    SeriesVisualSignatureCritique,
    SeriesVisualSignatureIntegratedPromptPlan,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.models.series_visual_signature_request import SeriesVisualSignatureRequest
from pixelle_video.models.visual_expression import VisualExpressionDecision
from pixelle_video.services.series_visual_signature_prompt_critic import (
    SeriesVisualSignaturePromptCritic,
)
from pixelle_video.services.series_visual_signature_scene_planner import (
    SeriesVisualSignatureScenePlanner,
)


class SeriesVisualSignatureRepairFailedError(ValueError):
    pass


@dataclass(frozen=True)
class SeriesVisualSignatureRepairLoop:
    max_repair_attempts: int = 2

    async def run_batch(
        self,
        *,
        planner: SeriesVisualSignatureScenePlanner,
        critic: SeriesVisualSignaturePromptCritic,
        base_visual_briefs: Sequence[BaseVisualBrief],
        series_visual_signature_request: SeriesVisualSignatureRequest,
        series_visual_signature_profile: SeriesVisualSignatureProfile,
        expression_decisions: Sequence[VisualExpressionDecision],
        frame_contexts: Sequence[Mapping[str, Any]] = (),
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> tuple[tuple[SeriesVisualSignatureIntegratedPromptPlan, ...], tuple[SeriesVisualSignatureCritique, ...], dict[str, Any]]:
        repair_context_by_frame: dict[str, Any] = {}
        attempts_snapshot: dict[str, Any] = {}

        for attempt in range(max(1, self.max_repair_attempts + 1)):
            try:
                plans = await planner.plan_batch(
                    base_visual_briefs=base_visual_briefs,
                    series_visual_signature_request=series_visual_signature_request,
                    series_visual_signature_profile=series_visual_signature_profile,
                    expression_decisions=expression_decisions,
                    frame_contexts=frame_contexts,
                    repair_context_by_frame=repair_context_by_frame,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                )
            except Exception as exc:
                attempts_snapshot[f"attempt_{attempt + 1}"] = {
                    "planner_error": str(exc),
                    "repair_context_by_frame": repair_context_by_frame,
                }
                repair_context_by_frame = {
                    brief.frame_id: {
                        "attempt": attempt + 1,
                        "issues": [
                            {
                                "code": "planner_failed",
                                "severity": "blocking",
                                "message": str(exc),
                                "repair_instruction": "Return a valid integrated_scene_prompt that satisfies V4.1 series visual signature rules.",
                            }
                        ],
                        "instruction": "Rewrite failed frame. Do not output hidden/suppressed/fallback. Do not copy issue text into final prompt.",
                    }
                    for brief in base_visual_briefs
                }
                continue

            critique_items: list[SeriesVisualSignatureCritique] = []
            for index, plan in enumerate(plans):
                critique_items.append(
                    await critic.critique(
                        plan=plan,
                        series_visual_signature_profile=series_visual_signature_profile,
                        series_visual_signature_request=series_visual_signature_request,
                        base_visual_brief=base_visual_briefs[index] if index < len(base_visual_briefs) else None,
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                    )
                )
            critiques = tuple(critique_items)
            attempts_snapshot[f"attempt_{attempt + 1}"] = {
                "plans": [plan.to_dict() for plan in plans],
                "critiques": [critique.to_dict() for critique in critiques],
            }
            failed = [critique for critique in critiques if not critique.passed]
            if not failed:
                return plans, critiques, attempts_snapshot

            repair_context_by_frame = {
                critique.frame_id: {
                    "attempt": attempt + 1,
                    "issues": [issue.to_dict() for issue in critique.issues],
                    "instruction": "Rewrite failed frame. Do not output hidden/suppressed/fallback. Do not copy issue text into final prompt.",
                }
                for critique in failed
            }

        errors = []
        for frame_id, context in repair_context_by_frame.items():
            errors.append(f"{frame_id}: {context.get('issues')}")
        raise SeriesVisualSignatureRepairFailedError("series visual signature repair failed after attempts: " + "; ".join(errors[:12]))


__all__ = ["SeriesVisualSignatureRepairFailedError", "SeriesVisualSignatureRepairLoop"]
