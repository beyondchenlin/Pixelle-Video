from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from pixelle_video.models.template_text_policy import normalize_template_text_policy

VISUAL_PROFILE_SCHEMA_VERSION = "visual_profile.v1"


@dataclass(frozen=True)
class VisualProfile:
    """End-to-end visual behavior contract for a generation run.

    A profile is intentionally broader than a template or style prefix.  It
    owns canvas defaults, template defaults, prompt requirements, negative
    rules, and preflight QA expectations.  Presets such as Xiaohei become
    data, not hard-coded branches.
    """

    profile_id: str
    display_name: str
    version: str = VISUAL_PROFILE_SCHEMA_VERSION
    description: str = ""
    canvas_width: int | None = None
    canvas_height: int | None = None
    media_width: int | None = None
    media_height: int | None = None
    frame_template: str | None = None
    template_text_policy: str = "caption_renderer"
    template_display: Mapping[str, Any] = field(default_factory=dict)
    planning_defaults: Mapping[str, Any] = field(default_factory=dict)
    positive_prompt_rules: tuple[str, ...] = ()
    composition_rules: tuple[str, ...] = ()
    visible_text_rules: tuple[str, ...] = ()
    negative_prompt_rules: tuple[str, ...] = ()
    required_prompt_terms: tuple[str, ...] = ()
    forbidden_prompt_terms: tuple[str, ...] = ()
    repair_prompt_clauses: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _required_text("profile_id", self.profile_id))
        object.__setattr__(self, "display_name", _required_text("display_name", self.display_name))
        object.__setattr__(self, "version", _required_text("version", self.version))
        object.__setattr__(self, "description", _optional_text(self.description))
        for field_name in ("canvas_width", "canvas_height", "media_width", "media_height"):
            object.__setattr__(self, field_name, _optional_positive_int(field_name, getattr(self, field_name)))
        object.__setattr__(self, "frame_template", _optional_text(self.frame_template) or None)
        object.__setattr__(
            self,
            "template_text_policy",
            normalize_template_text_policy(self.template_text_policy),
        )
        object.__setattr__(self, "template_display", dict(self.template_display or {}))
        object.__setattr__(self, "planning_defaults", dict(self.planning_defaults or {}))
        for field_name in (
            "positive_prompt_rules",
            "composition_rules",
            "visible_text_rules",
            "negative_prompt_rules",
            "required_prompt_terms",
            "forbidden_prompt_terms",
            "repair_prompt_clauses",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_text_tuple(field_name, getattr(self, field_name)),
            )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "VisualProfile":
        data = dict(payload or {})
        return cls(
            profile_id=str(data.get("profile_id") or data.get("id") or "").strip(),
            display_name=str(data.get("display_name") or data.get("name") or data.get("id") or "").strip(),
            version=str(data.get("version", VISUAL_PROFILE_SCHEMA_VERSION)),
            description=str(data.get("description", "")),
            canvas_width=data.get("canvas_width"),
            canvas_height=data.get("canvas_height"),
            media_width=data.get("media_width"),
            media_height=data.get("media_height"),
            frame_template=data.get("frame_template"),
            template_text_policy=data.get("template_text_policy", "caption_renderer"),
            template_display=data.get("template_display") or {},
            planning_defaults=data.get("planning_defaults") or {},
            positive_prompt_rules=data.get("positive_prompt_rules") or (),
            composition_rules=data.get("composition_rules") or (),
            visible_text_rules=data.get("visible_text_rules") or (),
            negative_prompt_rules=data.get("negative_prompt_rules") or (),
            required_prompt_terms=data.get("required_prompt_terms") or (),
            forbidden_prompt_terms=data.get("forbidden_prompt_terms") or (),
            repair_prompt_clauses=data.get("repair_prompt_clauses") or (),
            metadata=data.get("metadata") or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "description": self.description,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "media_width": self.media_width,
            "media_height": self.media_height,
            "frame_template": self.frame_template,
            "template_text_policy": self.template_text_policy,
            "template_display": dict(self.template_display),
            "planning_defaults": dict(self.planning_defaults),
            "positive_prompt_rules": list(self.positive_prompt_rules),
            "composition_rules": list(self.composition_rules),
            "visible_text_rules": list(self.visible_text_rules),
            "negative_prompt_rules": list(self.negative_prompt_rules),
            "required_prompt_terms": list(self.required_prompt_terms),
            "forbidden_prompt_terms": list(self.forbidden_prompt_terms),
            "repair_prompt_clauses": list(self.repair_prompt_clauses),
            "metadata": dict(self.metadata),
        }

    def prompt_contract_clauses(self) -> tuple[str, ...]:
        return _normalize_text_tuple(
            "prompt_contract_clauses",
            (
                *self.positive_prompt_rules,
                *self.composition_rules,
                *self.visible_text_rules,
            ),
        )

    def template_defaults(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in ("canvas_width", "canvas_height", "media_width", "media_height"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.frame_template:
            payload["frame_template"] = self.frame_template
        payload["template_text_policy"] = self.template_text_policy
        payload["template_display"] = dict(self.template_display)
        return payload


def _required_text(field_name: str, value: Any) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string")
    return text


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_positive_int(field_name: str, value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return number


def _normalize_text_tuple(field_name: str, values: Sequence[Any] | Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        candidates = [part.strip() for part in values.replace("；", ",").split(",")]
    elif isinstance(values, Sequence):
        candidates = [str(item or "").strip() for item in values]
    else:
        raise ValueError(f"{field_name} must be a sequence of strings")
    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)


__all__ = ["VISUAL_PROFILE_SCHEMA_VERSION", "VisualProfile"]
