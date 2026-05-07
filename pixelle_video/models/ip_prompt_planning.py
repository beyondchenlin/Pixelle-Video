from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

_HEX_COLOR_RE = re.compile(r"(?<![0-9a-fA-F])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])")


class IPPresenceType(str, Enum):
    STRONG_IDENTITY = "strong_identity"
    BALANCED_NARRATIVE = "balanced_narrative"
    SCENE_INTEGRATED = "scene_integrated"
    LOW_INTRUSION = "low_intrusion"
    SYMBOLIC_ONLY = "symbolic_only"
    ABSENT = "absent"


class IPRoleSlot(str, Enum):
    """Which narrative role the IP fills in this frame.

    决定 IP 在当前帧"替代谁"：
    - PROTAGONIST: IP 替代画面主角，占据前景主体位置
    - SUPPORTING:   IP 替代画面配角，中景融入场景
    - PASSERBY:     IP 替代画面路人/背景人物，远景边缘融入
    - ABSENT:       本帧 IP 不出镜

    用法：由 IPFrameAppearancePlanner 逐帧设定，写入 ip_adaptation.role_slot。
          image_generation.py 系统提示和 content_generators.py 权重门控都会读取此字段。
    """
    PROTAGONIST = "protagonist"
    SUPPORTING = "supporting"
    PASSERBY = "passerby"
    ABSENT = "absent"


@dataclass(frozen=True)
class IPImageTextPlan:
    summary_text: str | None = None
    scene_text: tuple[str, ...] = ()
    visible_text_whitelist: tuple[str, ...] = ()
    text_safety_rules: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary_text", _optional_prompt_str("summary_text", self.summary_text))
        object.__setattr__(self, "scene_text", _normalize_prompt_tuple("scene_text", self.scene_text))
        object.__setattr__(
            self,
            "visible_text_whitelist",
            _normalize_prompt_tuple("visible_text_whitelist", self.visible_text_whitelist),
        )
        object.__setattr__(
            self,
            "text_safety_rules",
            _normalize_prompt_tuple("text_safety_rules", self.text_safety_rules),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_text": self.summary_text,
            "scene_text": list(self.scene_text),
            "visible_text_whitelist": list(self.visible_text_whitelist),
            "text_safety_rules": list(self.text_safety_rules),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IPImageTextPlan":
        _require_mapping("IPImageTextPlan", payload)
        return cls(
            summary_text=payload.get("summary_text"),
            scene_text=_payload_sequence_or_default(payload.get("scene_text")),
            visible_text_whitelist=_payload_sequence_or_default(payload.get("visible_text_whitelist")),
            text_safety_rules=_payload_sequence_or_default(payload.get("text_safety_rules")),
        )


@dataclass(frozen=True)
class IPFrameAdaptationPackage:
    frame_id: str
    ip_presence_type: IPPresenceType
    presence_mode: str | None = None
    semantic_reason: str | None = None
    must_not_replace: tuple[str, ...] = ()
    identity_anchors_visible: tuple[str, ...] = ()
    identity_anchors_suppressed: tuple[str, ...] = ()
    identity_color_terms: tuple[str, ...] = ()
    outfit_theme: str | None = None
    outfit_condition: str | None = None
    accessories: tuple[str, ...] = ()
    action: str | None = None
    expression: str | None = None
    pose: str | None = None
    camera_relationship: str | None = None
    depth_layer: str | None = None
    interaction_target: str | None = None
    continuity_from_previous: str | None = None
    appearance_description: str | None = None
    # 纯视觉特征（仅从 identity_lock 提取，不含角色标签如"古城文旅向导"）。
    # 由 IPFrameAppearancePlanner 逐帧设定，用于 post-append 回退和 LLM prompt context。
    visual_identity: str | None = None
    # IP 在当前帧替代的角色槽位（主角/配角/路人/不出镜）。
    # 由 IPFrameAppearancePlanner 逐帧设定，系统提示和权重门控都会读取此字段。
    role_slot: IPRoleSlot | None = None
    shot_fit_notes: str | None = None
    image_text_plan: IPImageTextPlan | None = None
    prompt_weight: float | None = None
    negative_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(self, "ip_presence_type", IPPresenceType(self.ip_presence_type))
        for field_name in (
            "presence_mode",
            "semantic_reason",
            "outfit_theme",
            "outfit_condition",
            "action",
            "expression",
            "pose",
            "camera_relationship",
            "depth_layer",
            "interaction_target",
            "continuity_from_previous",
            "appearance_description",
            "visual_identity",
            "shot_fit_notes",
        ):
            object.__setattr__(self, field_name, _optional_prompt_str(field_name, getattr(self, field_name)))
        for field_name in (
            "must_not_replace",
            "identity_anchors_visible",
            "identity_anchors_suppressed",
            "identity_color_terms",
            "accessories",
            "negative_constraints",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_prompt_tuple(field_name, getattr(self, field_name)),
            )
        if self.role_slot is not None and not isinstance(self.role_slot, IPRoleSlot):
            object.__setattr__(self, "role_slot", IPRoleSlot(self.role_slot))
        if self.image_text_plan is not None and not isinstance(self.image_text_plan, IPImageTextPlan):
            raise ValueError("image_text_plan must be an IPImageTextPlan")
        if self.prompt_weight is not None:
            object.__setattr__(self, "prompt_weight", _normalize_prompt_weight(self.prompt_weight))

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "ip_presence_type": self.ip_presence_type.value,
            "presence_mode": self.presence_mode,
            "semantic_reason": self.semantic_reason,
            "must_not_replace": list(self.must_not_replace),
            "identity_anchors_visible": list(self.identity_anchors_visible),
            "identity_anchors_suppressed": list(self.identity_anchors_suppressed),
            "identity_color_terms": list(self.identity_color_terms),
            "outfit_theme": self.outfit_theme,
            "outfit_condition": self.outfit_condition,
            "accessories": list(self.accessories),
            "action": self.action,
            "expression": self.expression,
            "pose": self.pose,
            "camera_relationship": self.camera_relationship,
            "depth_layer": self.depth_layer,
            "interaction_target": self.interaction_target,
            "continuity_from_previous": self.continuity_from_previous,
            "appearance_description": self.appearance_description,
            "visual_identity": self.visual_identity,
            "role_slot": self.role_slot.value if self.role_slot else None,
            "shot_fit_notes": self.shot_fit_notes,
            "image_text_plan": self.image_text_plan.to_dict() if self.image_text_plan else None,
            "prompt_weight": self.prompt_weight,
            "negative_constraints": list(self.negative_constraints),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IPFrameAdaptationPackage":
        _require_mapping("IPFrameAdaptationPackage", payload)
        image_text_plan = payload.get("image_text_plan")
        return cls(
            frame_id=payload.get("frame_id", ""),
            ip_presence_type=payload.get("ip_presence_type", IPPresenceType.ABSENT),
            presence_mode=payload.get("presence_mode"),
            semantic_reason=payload.get("semantic_reason"),
            must_not_replace=_payload_sequence_or_default(payload.get("must_not_replace")),
            identity_anchors_visible=_payload_sequence_or_default(payload.get("identity_anchors_visible")),
            identity_anchors_suppressed=_payload_sequence_or_default(payload.get("identity_anchors_suppressed")),
            identity_color_terms=_payload_sequence_or_default(payload.get("identity_color_terms")),
            outfit_theme=payload.get("outfit_theme"),
            outfit_condition=payload.get("outfit_condition"),
            accessories=_payload_sequence_or_default(payload.get("accessories")),
            action=payload.get("action"),
            expression=payload.get("expression"),
            pose=payload.get("pose"),
            camera_relationship=payload.get("camera_relationship"),
            depth_layer=payload.get("depth_layer"),
            interaction_target=payload.get("interaction_target"),
            continuity_from_previous=payload.get("continuity_from_previous"),
            appearance_description=payload.get("appearance_description"),
            visual_identity=payload.get("visual_identity"),
            role_slot=_parse_role_slot(payload.get("role_slot")),
            shot_fit_notes=payload.get("shot_fit_notes"),
            image_text_plan=IPImageTextPlan.from_dict(image_text_plan) if image_text_plan else None,
            prompt_weight=payload.get("prompt_weight"),
            negative_constraints=_payload_sequence_or_default(payload.get("negative_constraints")),
        )


def _parse_role_slot(value: Any) -> IPRoleSlot | None:
    if value is None:
        return None
    if isinstance(value, IPRoleSlot):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return IPRoleSlot(value.strip())
        except ValueError:
            return None
    return None


def _require_mapping(type_name: str, payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{type_name} payload must be a mapping")


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return _reject_hex_color(field_name, value.strip())


def _optional_prompt_str(field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        return None
    return _reject_hex_color(field_name, stripped)


def _normalize_prompt_tuple(field_name: str, value: Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(_require_non_empty(field_name, item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _reject_hex_color(field_name: str, value: str) -> str:
    if _HEX_COLOR_RE.search(value):
        raise ValueError(f"{field_name} must use prompt color terms, not hex colors")
    return value


def _normalize_prompt_weight(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("prompt_weight must be a finite int or float")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError("prompt_weight must be a finite int or float")
    return normalized


def _payload_sequence_or_default(value: Any) -> Any:
    if value is None:
        return ()
    return value


__all__ = [
    "IPFrameAdaptationPackage",
    "IPImageTextPlan",
    "IPPresenceType",
    "IPRoleSlot",
]
