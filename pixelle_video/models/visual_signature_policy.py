from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

_DEFAULT_ALLOWED_CARRIER_TYPES = (
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

_DEFAULT_FORBIDDEN_TERMS = (
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
    "贴纸",
    "悬浮",
    "漂浮",
    "浮在",
    "logo",
    "Logo",
    "LOGO",
    "watermark",
    "corner logo",
    "corner bug",
    "canvas corner",
    "canvas corners",
    "screen corner",
    "screen corners",
    "floating sticker",
    "sticker",
    "overlay",
    "UI badge",
    "ui badge",
    "UI层",
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
    "所有新增识别细节都属于场景内真实物体或材质表面的一部分。",
    "主要画面主体保持清晰，画面表面干净完整，细节服从主体叙事。",
)


@dataclass(frozen=True)
class VisualSignaturePolicy:
    """Runtime policy for recurring visual signatures.

    Human-editable Markdown controls project-specific policy data. Python keeps
    the non-negotiable safety gates so a project policy can tighten or specialize
    behavior without reintroducing canvas-corner badges, stickers, or watermarks.
    """

    version: str = "visual_signature_policy.v1_0_mandatory_ip_participation"
    coverage_mode: Literal["sparse", "every_frame"] = "every_frame"
    suppress_allowed: bool = False
    fallback_strategy: Literal["suppress", "inject_safe_carrier"] = "inject_safe_carrier"
    projection_failure: Literal["allow_anchor_free", "repair_or_fail"] = "repair_or_fail"
    require_concrete_identity: bool = True
    fail_closed_on_llm_error: bool = True
    fail_closed_on_rejected_candidate: bool = True
    prefer_suppressed_when_uncertain: bool = False
    suppress_named_subject_count: int = 0
    visible_frame_budget_ratio: float = 1.0
    max_consecutive_visible_frames: int = 0
    allowed_visible_carrier_types: tuple[str, ...] = _DEFAULT_ALLOWED_CARRIER_TYPES
    forbidden_overlay_terms: tuple[str, ...] = _DEFAULT_FORBIDDEN_TERMS
    final_prompt_forbidden_terms: tuple[str, ...] = _DEFAULT_FORBIDDEN_TERMS
    high_risk_subject_terms: tuple[str, ...] = _DEFAULT_HIGH_RISK_TERMS
    high_risk_scene_terms: tuple[str, ...] = _DEFAULT_HIGH_RISK_TERMS
    positive_prompt_guards: tuple[str, ...] = _DEFAULT_POSITIVE_GUARDS

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "VisualSignaturePolicy":
        payload = dict(payload or {})
        return cls(
            version=_text(payload.get("version"), cls.version),
            coverage_mode=_coverage_mode(payload.get("coverage_mode")),
            suppress_allowed=_bool(payload.get("suppress_allowed"), False),
            fallback_strategy=_fallback_strategy(payload.get("fallback_strategy")),
            projection_failure=_projection_failure(payload.get("projection_failure")),
            require_concrete_identity=_bool(payload.get("require_concrete_identity"), True),
            fail_closed_on_llm_error=_bool(payload.get("fail_closed_on_llm_error"), True),
            fail_closed_on_rejected_candidate=_bool(
                payload.get("fail_closed_on_rejected_candidate"), True
            ),
            prefer_suppressed_when_uncertain=_bool(
                payload.get("prefer_suppressed_when_uncertain"), False
            ),
            suppress_named_subject_count=max(0, _int(payload.get("suppress_named_subject_count"), 0)),
            visible_frame_budget_ratio=_ratio(payload.get("visible_frame_budget_ratio"), 1.0),
            max_consecutive_visible_frames=max(
                0, _int(payload.get("max_consecutive_visible_frames"), 0)
            ),
            allowed_visible_carrier_types=_allowed_carriers(
                payload.get("allowed_visible_carrier_types")
            ),
            forbidden_overlay_terms=_merged_tuple(
                _DEFAULT_FORBIDDEN_TERMS, payload.get("forbidden_overlay_terms")
            ),
            final_prompt_forbidden_terms=_merged_tuple(
                _DEFAULT_FORBIDDEN_TERMS, payload.get("final_prompt_forbidden_terms")
            ),
            high_risk_subject_terms=_merged_tuple(
                _DEFAULT_HIGH_RISK_TERMS, payload.get("high_risk_subject_terms")
            ),
            high_risk_scene_terms=_merged_tuple(
                _DEFAULT_HIGH_RISK_TERMS, payload.get("high_risk_scene_terms")
            ),
            positive_prompt_guards=_tuple(
                payload.get("positive_prompt_guards"), _DEFAULT_POSITIVE_GUARDS
            ),
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

    def carrier_type_allowed(self, carrier_type: Any) -> bool:
        value = str(getattr(carrier_type, "value", carrier_type) or "").strip()
        if value == "suppressed" and not self.suppress_allowed:
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


def _coverage_mode(value: Any) -> Literal["sparse", "every_frame"]:
    text = str(value or "every_frame").strip().lower()
    return "sparse" if text == "sparse" else "every_frame"


def _fallback_strategy(value: Any) -> Literal["suppress", "inject_safe_carrier"]:
    text = str(value or "inject_safe_carrier").strip().lower()
    return "suppress" if text == "suppress" else "inject_safe_carrier"


def _projection_failure(value: Any) -> Literal["allow_anchor_free", "repair_or_fail"]:
    text = str(value or "repair_or_fail").strip().lower()
    return "allow_anchor_free" if text == "allow_anchor_free" else "repair_or_fail"

def _text(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


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


def _allowed_carriers(value: Any) -> tuple[str, ...]:
    if value is None:
        return _DEFAULT_ALLOWED_CARRIER_TYPES
    requested = set(_tuple(value, _DEFAULT_ALLOWED_CARRIER_TYPES))
    allowed = [item for item in _DEFAULT_ALLOWED_CARRIER_TYPES if item in requested]
    return tuple(allowed) or _DEFAULT_ALLOWED_CARRIER_TYPES


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
