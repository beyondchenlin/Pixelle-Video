from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

VISUAL_STORY_CONTEXT_CONTRACT_VERSION = "v4_context_contract"
DEFAULT_MAX_TOTAL_CHARS = 9000


@dataclass(frozen=True)
class PromptBudgetPolicy:
    """Hard prompt budget for downstream visual-signature planning.

    The policy is intentionally expressed in characters rather than tokens because
    this project uses multiple OpenAI-compatible providers. The budget is set far
    below common provider limits so the visual-anchor prompt still has room for
    base visual briefs, identity profile, schema instructions, and repair context.
    """

    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS
    route_text_chars: int = 180
    frame_text_chars: int = 120
    plan_text_chars: int = 100
    list_items: int = 4
    hard_floor_route_chars: int = 48
    hard_floor_frame_chars: int = 36


@dataclass(frozen=True)
class BudgetedVisualStoryContext:
    """Serialized-safe context contract passed to visual-anchor integration."""

    payload: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def serialized_length(self) -> int:
        return len(_canonical_json(self.payload))


class VisualStoryContextContractBuilder:
    """Builds bounded context contracts from full frame contexts.

    Source-of-truth rule:
    - Full planning data belongs in planning_snapshot / trace artifacts.
    - LLM prompt payloads receive only this compact contract.
    - The builder must never return a payload larger than max_total_chars.
    """

    def __init__(self, policy: PromptBudgetPolicy | None = None) -> None:
        self.policy = policy or PromptBudgetPolicy()

    def build_for_visual_anchor(
        self,
        *,
        frame_contexts: Sequence[Mapping[str, Any]],
    ) -> BudgetedVisualStoryContext:
        source_frames = [
            dict(frame)
            for frame in frame_contexts
            if isinstance(frame, Mapping)
        ]
        diagnostics: dict[str, Any] = {
            "contract_version": VISUAL_STORY_CONTEXT_CONTRACT_VERSION,
            "input_frame_count": len(source_frames),
            "dropped_unbounded_fields": [
                "base_prompt",
                "base_image_prompt",
                "plan_source_text",
                "metadata",
                "article_concretization_plan",
                "selected_visual_route duplicated per frame",
            ],
            "degradation_level": "none",
        }

        payload = self._build_payload(
            source_frames,
            route_text_chars=self.policy.route_text_chars,
            frame_text_chars=self.policy.frame_text_chars,
            plan_text_chars=self.policy.plan_text_chars,
            include_secondary=True,
        )
        payload = self._with_contract_metadata(payload, diagnostics)
        if _within_budget(payload, self.policy.max_total_chars):
            return BudgetedVisualStoryContext(payload=payload, diagnostics=diagnostics)

        # Gradual degradation: keep the same shape, reduce text and list density.
        for level, route_chars, frame_chars, plan_chars, include_secondary in (
            ("compact", 140, 90, 80, True),
            ("tight", 96, 64, 56, False),
            ("minimal", 64, 48, 40, False),
        ):
            diagnostics = {**diagnostics, "degradation_level": level}
            payload = self._build_payload(
                source_frames,
                route_text_chars=route_chars,
                frame_text_chars=frame_chars,
                plan_text_chars=plan_chars,
                include_secondary=include_secondary,
            )
            payload = self._with_contract_metadata(payload, diagnostics)
            if _within_budget(payload, self.policy.max_total_chars):
                return BudgetedVisualStoryContext(payload=payload, diagnostics=diagnostics)

        # Hard-budget fallback: no free text except frame ids and very small role/task phrases.
        diagnostics = {**diagnostics, "degradation_level": "hard_budget"}
        payload = self._build_hard_budget_payload(source_frames)
        payload = self._with_contract_metadata(payload, diagnostics)
        if _within_budget(payload, self.policy.max_total_chars):
            return BudgetedVisualStoryContext(payload=payload, diagnostics=diagnostics)

        # If there are too many frames for the global budget, keep frame ids only.
        diagnostics = {**diagnostics, "degradation_level": "frame_ids_only"}
        payload = {
            "frame_contexts": [
                {
                    "frame_id": _first_text(frame.get("frame_id"), f"frame-{index + 1}"),
                    "frame_index": _safe_index(frame.get("frame_index"), index),
                }
                for index, frame in enumerate(source_frames)
            ],
            "selected_visual_route": _route_identity(_first_mapping(source_frames, "selected_visual_route")),
            "visual_story_frame_plans": [],
            "visual_story_ip_fusion_plans": [],
        }
        payload = self._with_contract_metadata(payload, diagnostics)

        # Absolute last resort: reduce frame list to count + first/last ids.
        if not _within_budget(payload, self.policy.max_total_chars):
            diagnostics = {**diagnostics, "degradation_level": "summary_only"}
            frame_ids = [
                _first_text(frame.get("frame_id"), f"frame-{index + 1}")
                for index, frame in enumerate(source_frames)
            ]
            payload = {
                "frame_summary": {
                    "frame_count": len(frame_ids),
                    "first_frame_id": frame_ids[0] if frame_ids else None,
                    "last_frame_id": frame_ids[-1] if frame_ids else None,
                    "requires_chunked_visual_anchor_planning": True,
                },
                "selected_visual_route": _route_identity(_first_mapping(source_frames, "selected_visual_route")),
            }
            payload = self._with_contract_metadata(payload, diagnostics)

        return BudgetedVisualStoryContext(payload=payload, diagnostics=diagnostics)

    def compact_one_frame(self, context: Mapping[str, Any]) -> dict[str, Any]:
        frame = dict(context or {})
        route = _compact_route(
            frame.get("selected_visual_route"),
            text_chars=self.policy.route_text_chars,
            include_reason=True,
        )
        result = _frame_summary(
            frame,
            index=0,
            text_chars=self.policy.frame_text_chars,
            include_secondary=True,
            list_items=self.policy.list_items,
        )
        if route:
            result["selected_visual_route"] = route
        frame_plan = _frame_plan_summary(
            frame.get("visual_story_frame_plan"),
            index=0,
            text_chars=self.policy.plan_text_chars,
            list_items=self.policy.list_items,
            include_forbidden=True,
        )
        if frame_plan:
            result["visual_story_frame_plan"] = frame_plan
        ip_plan = _ip_plan_summary(
            frame.get("visual_story_ip_fusion_plan"),
            index=0,
            text_chars=self.policy.plan_text_chars,
            list_items=self.policy.list_items,
            include_reason=True,
        )
        if ip_plan:
            result["visual_story_ip_fusion_plan"] = ip_plan
        return result

    def _build_payload(
        self,
        frames: Sequence[Mapping[str, Any]],
        *,
        route_text_chars: int,
        frame_text_chars: int,
        plan_text_chars: int,
        include_secondary: bool,
    ) -> dict[str, Any]:
        selected_route = _compact_route(
            _first_mapping(frames, "selected_visual_route"),
            text_chars=route_text_chars,
            include_reason=include_secondary,
        )
        return {
            "frame_contexts": [
                _frame_summary(
                    frame,
                    index=index,
                    text_chars=frame_text_chars,
                    include_secondary=include_secondary,
                    list_items=self.policy.list_items if include_secondary else 2,
                )
                for index, frame in enumerate(frames)
            ],
            # Route is global. Do not duplicate it inside every frame.
            "selected_visual_route": selected_route,
            "visual_story_frame_plans": [
                _frame_plan_summary(
                    frame.get("visual_story_frame_plan"),
                    index=index,
                    text_chars=plan_text_chars,
                    list_items=self.policy.list_items if include_secondary else 2,
                    include_forbidden=include_secondary,
                )
                for index, frame in enumerate(frames)
                if isinstance(frame.get("visual_story_frame_plan"), Mapping)
            ],
            "visual_story_ip_fusion_plans": [
                _ip_plan_summary(
                    frame.get("visual_story_ip_fusion_plan"),
                    index=index,
                    text_chars=plan_text_chars,
                    list_items=self.policy.list_items if include_secondary else 2,
                    include_reason=include_secondary,
                )
                for index, frame in enumerate(frames)
                if isinstance(frame.get("visual_story_ip_fusion_plan"), Mapping)
            ],
        }

    def _build_hard_budget_payload(self, frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "frame_contexts": [
                {
                    "frame_id": _first_text(frame.get("frame_id"), f"frame-{index + 1}"),
                    "frame_index": _safe_index(frame.get("frame_index"), index),
                    "source_text": _truncate(
                        _first_text(frame.get("frame_source_text"), frame.get("source_text")),
                        self.policy.hard_floor_frame_chars,
                    ),
                }
                for index, frame in enumerate(frames)
            ],
            "selected_visual_route": _compact_route(
                _first_mapping(frames, "selected_visual_route"),
                text_chars=self.policy.hard_floor_route_chars,
                include_reason=False,
            ),
            "visual_story_frame_plans": [
                _minimal_frame_plan(frame.get("visual_story_frame_plan"), fallback_index=index)
                for index, frame in enumerate(frames)
                if isinstance(frame.get("visual_story_frame_plan"), Mapping)
            ],
            "visual_story_ip_fusion_plans": [
                _minimal_ip_plan(frame.get("visual_story_ip_fusion_plan"), fallback_index=index)
                for index, frame in enumerate(frames)
                if isinstance(frame.get("visual_story_ip_fusion_plan"), Mapping)
            ],
        }

    def _with_contract_metadata(self, payload: dict[str, Any], diagnostics: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        result["context_contract"] = {
            "version": VISUAL_STORY_CONTEXT_CONTRACT_VERSION,
            "max_total_chars": self.policy.max_total_chars,
            "serialized_chars": len(_canonical_json(payload)),
            "degradation_level": diagnostics.get("degradation_level", "none"),
        }
        return result


def compact_visual_anchor_contexts(
    *,
    frame_contexts: Sequence[Mapping[str, Any]],
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> dict[str, Any]:
    """Backward-compatible entry point used by the visual-anchor planner."""

    policy = PromptBudgetPolicy(max_total_chars=max_total_chars)
    contract = VisualStoryContextContractBuilder(policy).build_for_visual_anchor(
        frame_contexts=frame_contexts,
    )
    return contract.payload


def compact_visual_story_frame_context(context: Mapping[str, Any]) -> dict[str, Any]:
    return VisualStoryContextContractBuilder().compact_one_frame(context)


def compact_visual_story_value(value: Any, *, max_text: int = 160, depth: int = 0) -> Any:
    """Legacy helper retained for callers that compact arbitrary values."""

    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _truncate(value, max_text)
    if isinstance(value, Mapping):
        if depth >= 2:
            return _truncate(_canonical_json(value), max_text)
        compact: dict[str, Any] = {}
        for key in _ordered_value_keys(value):
            item = compact_visual_story_value(value[key], max_text=max_text, depth=depth + 1)
            if item not in ("", None, [], {}):
                compact[str(key)] = item
        return compact
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            item
            for item in (
                compact_visual_story_value(entry, max_text=max_text, depth=depth + 1)
                for entry in list(value)[:6]
            )
            if item not in ("", None, [], {})
        ]
    return _truncate(str(value), max_text)


def _frame_summary(
    frame: Mapping[str, Any],
    *,
    index: int,
    text_chars: int,
    include_secondary: bool,
    list_items: int,
) -> dict[str, Any]:
    payload = {
        "frame_id": _first_text(frame.get("frame_id"), f"frame-{index + 1}"),
        "frame_index": _safe_index(frame.get("frame_index"), index),
        "source_text": _truncate(_first_text(frame.get("frame_source_text"), frame.get("source_text")), text_chars),
        "visual_goal": _truncate(frame.get("visual_goal"), text_chars),
        "prompt_intent": _truncate(frame.get("prompt_intent"), text_chars),
        "primary_subject": _truncate(frame.get("primary_subject"), 72),
    }
    if include_secondary:
        payload["secondary_subjects"] = _compact_list(frame.get("secondary_subjects"), item_limit=56, count=list_items)
        payload["continuity_anchors"] = _compact_list(frame.get("continuity_anchors"), item_limit=56, count=list_items)
    return _clean(payload)


def _compact_route(value: Any, *, text_chars: int, include_reason: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    payload = {
        "route_id": _truncate(value.get("route_id"), 80),
        "route_name": _truncate(value.get("route_name"), 80),
        "route_type": _truncate(value.get("route_type"), 80),
        "style_family": _truncate(_first_text(value.get("style_family"), value.get("family")), 80),
        "recommended_ip_role": _truncate(value.get("recommended_ip_role"), 80),
        "visual_premise": _truncate(value.get("visual_premise"), text_chars),
    }
    if include_reason:
        payload["why_it_fits_article"] = _truncate(value.get("why_it_fits_article"), text_chars)
        payload["risk"] = _truncate(value.get("risk"), text_chars)
    scores = value.get("scores")
    if isinstance(scores, Mapping) and include_reason:
        payload["scores"] = {
            key: scores[key]
            for key in ("content_fit", "ip_compatibility", "memorability", "channel_fit", "final")
            if key in scores and isinstance(scores[key], (int, float, str))
        }
    return _clean(payload)


def _route_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return _clean(
        {
            "route_id": _truncate(value.get("route_id"), 80),
            "route_name": _truncate(value.get("route_name"), 48),
            "recommended_ip_role": _truncate(value.get("recommended_ip_role"), 48),
        }
    )


def _frame_plan_summary(
    value: Any,
    *,
    index: int,
    text_chars: int,
    list_items: int,
    include_forbidden: bool,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    payload = {
        "frame_id": _first_text(value.get("frame_id"), f"frame-{index + 1}"),
        "frame_index": _safe_index(value.get("frame_index"), index),
        "local_claim": _truncate(value.get("local_claim"), text_chars),
        "visual_task": _truncate(value.get("visual_task"), text_chars),
        "route_application": _truncate(value.get("route_application"), text_chars),
        "required_subjects": _compact_list(value.get("required_subjects"), item_limit=56, count=list_items),
    }
    if include_forbidden:
        payload["forbidden_losses"] = _compact_list(value.get("forbidden_losses"), item_limit=64, count=list_items)
    return _clean(payload)


def _ip_plan_summary(
    value: Any,
    *,
    index: int,
    text_chars: int,
    list_items: int,
    include_reason: bool,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    payload = {
        "frame_id": _first_text(value.get("frame_id"), f"frame-{index + 1}"),
        "frame_index": _safe_index(value.get("frame_index"), index),
        "ip_role": _truncate(_first_text(value.get("ip_role"), value.get("role")), 60),
        "ip_visibility": _truncate(_first_text(value.get("ip_visibility"), value.get("visibility_tier")), 60),
        "ip_duty_preset": _truncate(value.get("ip_duty_preset"), 60),
        "duty_goal": _truncate(_first_text(value.get("duty_goal"), value.get("scene_function"), value.get("action_or_function")), text_chars),
        "action_verb": _truncate(value.get("action_verb"), 60),
        "interaction_target": _truncate(value.get("interaction_target"), text_chars),
        "scene_binding": _truncate(_first_text(value.get("scene_binding"), value.get("placement_logic"), value.get("placement_strategy")), text_chars),
        "presentation_form": _truncate(value.get("presentation_form"), 60),
        "fallback_presentation": _truncate(value.get("fallback_presentation"), 60),
        "semantic_removal_test": _truncate(_first_text(value.get("semantic_removal_test"), value.get("removal_test")), text_chars),
        "channel_identity_removal_test": _truncate(value.get("channel_identity_removal_test"), text_chars),
        "style_harmony_rule": _truncate(value.get("style_harmony_rule"), text_chars),
        "negative_rules": _compact_list(_first_non_empty_list(value.get("negative_rules"), value.get("negative_constraints")), item_limit=60, count=list_items),
    }
    if include_reason:
        payload["reason"] = _truncate(value.get("reason"), text_chars)
    return _clean(payload)


def _minimal_frame_plan(value: Any, *, fallback_index: int) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    return _clean(
        {
            "frame_id": _first_text(value.get("frame_id"), f"frame-{fallback_index + 1}"),
            "frame_index": _safe_index(value.get("frame_index"), fallback_index),
            "visual_task": _truncate(value.get("visual_task"), 40),
        }
    )


def _minimal_ip_plan(value: Any, *, fallback_index: int) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    return _clean(
        {
            "frame_id": _first_text(value.get("frame_id"), f"frame-{fallback_index + 1}"),
            "frame_index": _safe_index(value.get("frame_index"), fallback_index),
            "ip_role": _truncate(_first_text(value.get("ip_role"), value.get("role")), 36),
            "ip_visibility": _truncate(_first_text(value.get("ip_visibility"), value.get("visibility_tier")), 36),
            "ip_duty_preset": _truncate(value.get("ip_duty_preset"), 36),
            "action_verb": _truncate(value.get("action_verb"), 28),
            "interaction_target": _truncate(value.get("interaction_target"), 40),
            "scene_binding": _truncate(_first_text(value.get("scene_binding"), value.get("placement_logic")), 40),
        }
    )


def _first_mapping(rows: Sequence[Mapping[str, Any]], key: str) -> Mapping[str, Any]:
    for row in rows:
        value = row.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _compact_list(value: Any, *, item_limit: int, count: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = list(value)
    else:
        values = [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in values[:count]:
        text = _truncate(item, item_limit)
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _ordered_value_keys(value: Mapping[str, Any]) -> list[str]:
    priority = (
        "route_id",
        "route_name",
        "route_type",
        "style_family",
        "recommended_ip_role",
        "visual_premise",
        "why_it_fits_article",
        "frame_id",
        "frame_index",
        "local_claim",
        "visual_task",
        "route_application",
        "required_subjects",
        "ip_role",
        "ip_visibility",
        "ip_duty_preset",
        "duty_goal",
        "action_verb",
        "interaction_target",
        "scene_binding",
        "presentation_form",
        "fallback_presentation",
        "semantic_removal_test",
        "channel_identity_removal_test",
        "style_harmony_rule",
        "negative_rules",
        "reason",
    )
    keys = [key for key in priority if key in value]
    keys.extend(str(key) for key in value.keys() if key not in keys and len(keys) < 12)
    return keys


def _first_non_empty_list(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return ()

def _first_text(*values: Any) -> str:
    for value in values:
        text = "" if value is None else str(value.value if hasattr(value, "value") else value).strip()
        if text:
            return text
    return ""


def _safe_index(value: Any, fallback: int) -> int:
    try:
        if isinstance(value, bool) or value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _truncate(value: Any, limit: int) -> str:
    text = _first_text(value)
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _clean(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in ("", None, [], {})
    }


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return str(value)


def _within_budget(payload: Mapping[str, Any], max_total_chars: int) -> bool:
    # Use both canonical JSON and Python repr length. The current tests use repr,
    # while provider calls use rendered JSON inside templates.
    return len(_canonical_json(payload)) <= max_total_chars and len(str(payload)) <= int(max_total_chars * 1.22)


__all__ = [
    "BudgetedVisualStoryContext",
    "PromptBudgetPolicy",
    "VisualStoryContextContractBuilder",
    "compact_visual_anchor_contexts",
    "compact_visual_story_frame_context",
    "compact_visual_story_value",
]
