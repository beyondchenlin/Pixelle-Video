from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import floor

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


@dataclass(frozen=True)
class VisualSignatureCadenceDecision:
    frame_id: str
    visible_allowed: bool
    reason: str
    score: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "frame_id": self.frame_id,
            "visible_allowed": self.visible_allowed,
            "reason": self.reason,
            "score": self.score,
        }


@dataclass(frozen=True)
class VisualSignatureCadencePlanner:
    """Batch-level visibility planner for recurring visual signatures.

    The signature is not decided frame-by-frame in isolation. A whole batch first
    gets a sparse visibility cadence so repeated identity details feel intentional
    instead of becoming per-frame corner badges.
    """

    policy: VisualSignaturePolicy | None = None

    def plan_batch(
        self,
        *,
        base_visual_briefs: Sequence[BaseVisualBrief],
    ) -> tuple[VisualSignatureCadenceDecision, ...]:
        policy = self.policy or load_visual_signature_policy()
        briefs = tuple(base_visual_briefs)
        if not briefs:
            return ()

        scored: list[tuple[int, int, BaseVisualBrief, str]] = []
        forced_hidden: dict[str, str] = {}

        for index, brief in enumerate(briefs):
            risk_reason = _forced_hidden_reason(brief, policy=policy)
            if risk_reason:
                forced_hidden[brief.frame_id] = risk_reason
                continue
            score, reason = _score_visible_opportunity(brief)
            if score <= 0:
                forced_hidden[brief.frame_id] = reason
                continue
            scored.append((score, -index, brief, reason))

        visible_budget = _visible_budget(len(briefs), policy.visible_frame_budget_ratio)
        visible_frame_ids: set[str] = set()
        consecutive = 0
        previous_index = -10

        for _, negative_index, brief, _ in sorted(scored, reverse=True):
            if len(visible_frame_ids) >= visible_budget:
                break
            index = -negative_index
            if (
                policy.max_consecutive_visible_frames > 0
                and index == previous_index + 1
                and consecutive >= policy.max_consecutive_visible_frames
            ):
                continue
            if index == previous_index + 1:
                consecutive += 1
            else:
                consecutive = 1
            previous_index = index
            visible_frame_ids.add(brief.frame_id)

        decisions: list[VisualSignatureCadenceDecision] = []
        reason_by_frame = {brief.frame_id: reason for _, _, brief, reason in scored}
        score_by_frame = {brief.frame_id: score for score, _, brief, _ in scored}
        for brief in briefs:
            if brief.frame_id in forced_hidden:
                decisions.append(
                    VisualSignatureCadenceDecision(
                        frame_id=brief.frame_id,
                        visible_allowed=False,
                        reason=forced_hidden[brief.frame_id],
                        score=0,
                    )
                )
                continue
            if brief.frame_id in visible_frame_ids:
                decisions.append(
                    VisualSignatureCadenceDecision(
                        frame_id=brief.frame_id,
                        visible_allowed=True,
                        reason=reason_by_frame.get(brief.frame_id, "safe visible cadence slot"),
                        score=score_by_frame.get(brief.frame_id, 1),
                    )
                )
                continue
            decisions.append(
                VisualSignatureCadenceDecision(
                    frame_id=brief.frame_id,
                    visible_allowed=False,
                    reason="hidden by sparse batch cadence",
                    score=score_by_frame.get(brief.frame_id, 0),
                )
            )
        return tuple(decisions)


def _visible_budget(frame_count: int, ratio: float) -> int:
    if frame_count <= 0 or ratio <= 0:
        return 0
    return max(1, floor(frame_count * ratio))


def _forced_hidden_reason(brief: BaseVisualBrief, *, policy: VisualSignaturePolicy) -> str:
    text = " ".join(
        [
            brief.base_image_prompt,
            brief.core_message,
            brief.visual_moment,
            brief.setting,
            " ".join(brief.main_subjects),
            " ".join(brief.subject_identity_anchors),
        ]
    )
    if policy.contains_high_risk_scene_text(text) or policy.contains_high_risk_subject_text(text):
        return "high-risk subject or scene keeps recurring signature hidden"
    if (
        policy.suppress_named_subject_count > 0
        and len(brief.main_subjects) >= policy.suppress_named_subject_count
    ):
        return "multiple named source subjects keep recurring signature hidden"
    return ""


def _score_visible_opportunity(brief: BaseVisualBrief) -> tuple[int, str]:
    text = " ".join(
        [
            brief.base_image_prompt,
            brief.setting,
            " ".join(brief.anchor_affordances),
            " ".join(brief.key_props_symbols),
        ]
    )
    if not brief.anchor_affordances:
        return 0, "no explicit scene-bound carrier"
    score = 1
    reason = "has a scene-bound carrier"
    if any(token in text for token in ("书", "书页", "纸", "地图", "卷轴", "文件", "卡片", "相框")):
        score += 4
        reason = "paper, book, map, or archive carrier supports material signature"
    if any(token in text for token in ("墙", "壁画", "海报", "黑板", "讲解板", "招牌")):
        score += 3
        reason = "surface graphic carrier supports material signature"
    if any(token in text for token in ("桌", "桌面", "书签", "摆件", "徽章", "胸针")):
        score += 2
        reason = "small prop carrier supports low-intrusion signature"
    if not brief.main_subjects:
        score += 2
        reason = "abstract or subject-light frame can carry a clearer signature"
    return score, reason


__all__ = ["VisualSignatureCadenceDecision", "VisualSignatureCadencePlanner"]
