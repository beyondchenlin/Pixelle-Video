from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_expression import VisualExpressionDecision
from pixelle_video.models.visual_role_planning import VisualRoleCritique, VisualRoleIntegratedPromptPlan
from pixelle_video.models.visual_role_profile import VisualRoleProfile
from pixelle_video.models.visual_role_request import VisualRoleRequest
from pixelle_video.services.visual_role_prompt_critic import VisualRolePromptCritic
from pixelle_video.services.visual_role_scene_planner import VisualRoleScenePlanner


class VisualRoleRepairFailedError(ValueError):
    pass


@dataclass(frozen=True)
class VisualRoleRepairLoop:
    max_repair_attempts: int = 2

    async def run_batch(
        self,
        *,
        planner: VisualRoleScenePlanner,
        critic: VisualRolePromptCritic,
        base_visual_briefs: Sequence[BaseVisualBrief],
        visual_role_request: VisualRoleRequest,
        visual_role_profile: VisualRoleProfile,
        expression_decisions: Sequence[VisualExpressionDecision],
        frame_contexts: Sequence[Mapping[str, Any]] = (),
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> tuple[tuple[VisualRoleIntegratedPromptPlan, ...], tuple[VisualRoleCritique, ...], dict[str, Any]]:
        repair_context_by_frame: dict[str, Any] = {}
        attempts_snapshot: dict[str, Any] = {}

        for attempt in range(max(1, self.max_repair_attempts + 1)):
            try:
                plans = await planner.plan_batch(
                    base_visual_briefs=base_visual_briefs,
                    visual_role_request=visual_role_request,
                    visual_role_profile=visual_role_profile,
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
                                "repair_instruction": "Return a valid integrated_scene_prompt that satisfies V4.1 visual role rules.",
                            }
                        ],
                        "instruction": "Rewrite failed frame. Do not output hidden/suppressed/fallback. Do not copy issue text into final prompt.",
                    }
                    for brief in base_visual_briefs
                }
                continue

            critique_items: list[VisualRoleCritique] = []
            for index, plan in enumerate(plans):
                critique_items.append(
                    await critic.critique(
                        plan=plan,
                        visual_role_profile=visual_role_profile,
                        visual_role_request=visual_role_request,
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
        raise VisualRoleRepairFailedError("visual role repair failed after attempts: " + "; ".join(errors[:12]))


__all__ = ["VisualRoleRepairFailedError", "VisualRoleRepairLoop"]
