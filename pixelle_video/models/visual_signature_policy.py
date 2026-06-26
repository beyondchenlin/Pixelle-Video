from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pixelle_video.utils.bool_parsing import coerce_bool

_CONTENT_BOUND_CARRIER_TYPES = (
    "content_bound_ip_actor",
    "content_bound_system_component",
    "content_bound_scale_reference",
    "content_bound_explanation_director",
)

_LEGACY_CARRIER_TYPES = (
    "bookplate_or_stamp",
    "printed_mark",
    "embossed_mark",
    "engraved_mark",
    "surface_graphic",
    "decorative_object",
    "wearable_symbol",
    "small_supporting_prop",
    "minor_supporting_character",
)

_ALL_CARRIER_TYPES = tuple(dict.fromkeys([*_CONTENT_BOUND_CARRIER_TYPES, *_LEGACY_CARRIER_TYPES]))

_DECORATIVE_CARRIER_TYPES = {
    "bookplate_or_stamp",
    "printed_mark",
    "embossed_mark",
    "engraved_mark",
    "surface_graphic",
    "decorative_object",
    "wearable_symbol",
    "small_supporting_prop",
    "embedded_mark",
    "wall_art",
    "screen_mark",
    "page_mark",
    "environment_detail",
    "partial_detail",
}

_DEFAULT_OVERLAY_TERMS = (
    "画面角落",
    "画面边角",
    "画布角落",
    "画布边角",
    "右上角",
    "左上角",
    "右下角",
    "左下角",
    "角标",
    "水印",
    "悬浮",
    "漂浮",
    "浮在",
    "corner logo",
    "corner bug",
    "canvas corner",
    "canvas corners",
    "screen corner",
    "screen corners",
    "floating sticker",
    "watermark",
    "overlay",
    "UI badge",
    "ui badge",
    "UI层",
)

_CONTENT_FREE_IP_TERMS = (
    "贴纸",
    "标签",
    "小标签",
    "卡片",
    "小卡片",
    "书签",
    "藏书票",
    "印章",
    "表面图案",
    "压印",
    "雕刻纹样",
    "logo",
    "Logo",
    "LOGO",
    "sticker",
    "label",
    "card",
    "bookmark",
    "bookplate",
    "stamp",
    "printed mark",
    "surface graphic",
    "badge",
)

_DEFAULT_HIGH_RISK_TERMS = (
    "奥特曼",
    "超人",
    "Superman",
    "Ultraman",
    "宗教",
    "佛祖",
    "佛像",
    "菩萨",
    "真实人物",
    "历史人物",
    "严肃历史",
    "严肃纪实",
    "纪录片",
    "纪实",
    "灾难",
    "悼念",
)

_DEFAULT_POSITIVE_GUARDS = (
    "Recurring identity appears through a visible content action, not through a mark.",
    "The article subject remains primary; the recurring character explains, operates, carries, weighs, connects, or arranges the content metaphor.",
)


@dataclass(frozen=True)
class VisualSignaturePolicy:
    """Runtime policy for recurring visual identity.

    v2 separates content-bound mandatory IP from legacy visual marks.  Legacy
    surface marks are still representable for old projects, but the default mode
    rejects them so the recurring IP cannot fall back into cards, stamps,
    bookmarks, labels, or surface graphics.
    """

    version: str = "visual_signature_policy.v2_0_content_bound_mandatory_ip"
    coverage_mode: Literal["sparse", "every_frame"] = "every_frame"
    suppress_allowed: bool = False
    fallback_strategy: Literal["suppress", "inject_safe_carrier", "rewrite_content_action"] = "rewrite_content_action"
    projection_failure: Literal["allow_anchor_free", "repair_or_fail"] = "repair_or_fail"
    require_concrete_identity: bool = True
    fail_closed_on_llm_error: bool = True
    fail_closed_on_rejected_candidate: bool = True
    prefer_suppressed_when_uncertain: bool = False
    suppress_named_subject_count: int = 0
    visible_frame_budget_ratio: float = 1.0
    max_consecutive_visible_frames: int = 0
    allowed_visible_carrier_types: tuple[str, ...] = _CONTENT_BOUND_CARRIER_TYPES
    forbidden_overlay_terms: tuple[str, ...] = _DEFAULT_OVERLAY_TERMS
    final_prompt_forbidden_terms: tuple[str, ...] = _CONTENT_FREE_IP_TERMS
    high_risk_subject_terms: tuple[str, ...] = _DEFAULT_HIGH_RISK_TERMS
    high_risk_scene_terms: tuple[str, ...] = _DEFAULT_HIGH_RISK_TERMS
    positive_prompt_guards: tuple[str, ...] = _DEFAULT_POSITIVE_GUARDS

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "VisualSignaturePolicy":
        payload = dict(payload or {})
        version = _text(payload.get("version"), cls.version)
        fallback = _fallback_strategy(payload.get("fallback_strategy"), version=version)
        default_carriers = _LEGACY_CARRIER_TYPES if _is_legacy_version(version, fallback) else _CONTENT_BOUND_CARRIER_TYPES
        return cls(
            version=version,
            coverage_mode=_coverage_mode(payload.get("coverage_mode")),
            suppress_allowed=coerce_bool(payload.get("suppress_allowed"), default=False),
            fallback_strategy=fallback,
            projection_failure=_projection_failure(payload.get("projection_failure")),
            require_concrete_identity=coerce_bool(payload.get("require_concrete_identity"), default=True),
            fail_closed_on_llm_error=coerce_bool(payload.get("fail_closed_on_llm_error"), default=True),
            fail_closed_on_rejected_candidate=coerce_bool(payload.get("fail_closed_on_rejected_candidate"), default=True),
            prefer_suppressed_when_uncertain=coerce_bool(payload.get("prefer_suppressed_when_uncertain"), default=False),
            suppress_named_subject_count=max(0, _int(payload.get("suppress_named_subject_count"), 0)),
            visible_frame_budget_ratio=_ratio(payload.get("visible_frame_budget_ratio"), 1.0),
            max_consecutive_visible_frames=max(0, _int(payload.get("max_consecutive_visible_frames"), 0)),
            allowed_visible_carrier_types=_allowed_carriers(payload.get("allowed_visible_carrier_types"), default_carriers),
            forbidden_overlay_terms=_merged_tuple(_DEFAULT_OVERLAY_TERMS, payload.get("forbidden_overlay_terms")),
            final_prompt_forbidden_terms=_merged_tuple(_CONTENT_FREE_IP_TERMS, payload.get("final_prompt_forbidden_terms")),
            high_risk_subject_terms=_merged_tuple(_DEFAULT_HIGH_RISK_TERMS, payload.get("high_risk_subject_terms")),
            high_risk_scene_terms=_merged_tuple(_DEFAULT_HIGH_RISK_TERMS, payload.get("high_risk_scene_terms")),
            positive_prompt_guards=_tuple(payload.get("positive_prompt_guards"), _DEFAULT_POSITIVE_GUARDS),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "coverage_mode": self.coverage_mode,
            "suppress_allowed": self.suppress_allowed,
            "fallback_strategy": self.fallback_strategy,
            "projection_failure": self.projection_failure,
            "require_concrete_identity": self.require_concrete_identity,
            "fail_closed_on_llm_error": self.fail_closed_on_llm_error,
            "fail_closed_on_rejected_candidate": self.fail_closed_on_rejected_candidate,
            "prefer_suppressed_when_uncertain": self.prefer_suppressed_when_uncertain,
            "suppress_named_subject_count": self.suppress_named_subject_count,
            "visible_frame_budget_ratio": self.visible_frame_budget_ratio,
            "max_consecutive_visible_frames": self.max_consecutive_visible_frames,
            "allowed_visible_carrier_types": list(self.allowed_visible_carrier_types),
            "forbidden_overlay_terms": list(self.forbidden_overlay_terms),
            "final_prompt_forbidden_terms": list(self.final_prompt_forbidden_terms),
            "high_risk_subject_terms": list(self.high_risk_subject_terms),
            "high_risk_scene_terms": list(self.high_risk_scene_terms),
            "positive_prompt_guards": list(self.positive_prompt_guards),
        }

    @property
    def requires_every_frame_signature(self) -> bool:
        return self.coverage_mode == "every_frame"

    @property
    def requires_repair_or_fail(self) -> bool:
        return self.projection_failure == "repair_or_fail"

    @property
    def is_content_bound_mandatory(self) -> bool:
        text = f"{self.version} {self.fallback_strategy}".lower()
        return "content_bound" in text or self.fallback_strategy == "rewrite_content_action"

    @property
    def is_legacy_visual_mark(self) -> bool:
        return _is_legacy_version(self.version, self.fallback_strategy)

    def carrier_type_allowed(self, carrier_type: Any) -> bool:
        value = str(getattr(carrier_type, "value", carrier_type) or "").strip()
        if value == "suppressed" and not self.suppress_allowed:
            return False
        if self.is_content_bound_mandatory and value in _DECORATIVE_CARRIER_TYPES:
            return False
        return value in set(self.allowed_visible_carrier_types)

    def contains_forbidden_overlay_text(self, text: str) -> bool:
        return _contains_any(text, self.forbidden_overlay_terms)

    def contains_forbidden_final_prompt_text(self, text: str) -> bool:
        return _contains_any(text, self.final_prompt_forbidden_terms)

    def contains_high_risk_subject_text(self, text: str) -> bool:
        return _contains_any(text, self.high_risk_subject_terms)

    def contains_high_risk_scene_text(self, text: str) -> bool:
        return _contains_any(text, self.high_risk_scene_terms)


def _is_legacy_version(version: str, fallback: str | None = None) -> bool:
    text = f"{version or ''} {fallback or ''}".lower()
    return "legacy" in text or "v1_" in text or fallback == "inject_safe_carrier"


def _coverage_mode(value: Any) -> Literal["sparse", "every_frame"]:
    text = str(value or "every_frame").strip().lower()
    return "sparse" if text == "sparse" else "every_frame"


def _fallback_strategy(value: Any, *, version: str = "") -> Literal["suppress", "inject_safe_carrier", "rewrite_content_action"]:
    text = str(value or "").strip().lower()
    if text == "suppress":
        return "suppress"
    if text == "inject_safe_carrier":
        return "inject_safe_carrier"
    if text == "rewrite_content_action":
        return "rewrite_content_action"
    return "inject_safe_carrier" if _is_legacy_version(version, text) else "rewrite_content_action"


def _projection_failure(value: Any) -> Literal["allow_anchor_free", "repair_or_fail"]:
    text = str(value or "repair_or_fail").strip().lower()
    return "allow_anchor_free" if text == "allow_anchor_free" else "repair_or_fail"


def _text(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ratio(value: Any, default: float) -> float:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(ratio, 0.0), 1.0)


def _allowed_carriers(value: Any, default: Sequence[str]) -> tuple[str, ...]:
    if value is None:
        return tuple(default)
    requested = set(_tuple(value, default))
    all_allowed = [item for item in _ALL_CARRIER_TYPES if item in requested]
    return tuple(all_allowed) or tuple(default)


def _tuple(value: Any, default: Sequence[str]) -> tuple[str, ...]:
    raw_values = default if value is None else value
    if isinstance(raw_values, str):
        raw_values = (raw_values,)
    if not isinstance(raw_values, Sequence):
        return tuple(default)
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _merged_tuple(default: Sequence[str], value: Any) -> tuple[str, ...]:
    return _tuple([*default, *_tuple(value, ())], default)


def _contains_any(text: str, values: Sequence[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(value or "").lower() in lowered for value in values if str(value or ""))


__all__ = ["VisualSignaturePolicy"]
