from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.models.frame_identity import MAX_STORYBOARD_FRAME_ID_CHARS

NOT_APPLICABLE = "not_applicable"
MAX_VISUAL_ENTITY_FRAME_ID_CHARS = MAX_STORYBOARD_FRAME_ID_CHARS
MAX_VISUAL_ENTITY_FACT_CHARS = 256
MAX_VISUAL_ENTITY_CORE_TRAITS = 32
MAX_VISUAL_ENTITY_PROTECTED_SUBJECTS = 64
MAX_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS = 16
DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS = (
    "sticker, corner badge, emblem, logo, or watermark overlay",
    "centered or oversized character that hides a required subject",
    "unrelated display platform, sign, box, carrier, or stage",
)


class VisualSceneType(str, Enum):
    PHYSICAL_SCENE = "physical_scene"
    ABSTRACT_DIAGRAM = "abstract_diagram"


class VisualHorizontalPosition(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VisualDepthPosition(str, Enum):
    FOREGROUND = "foreground"
    MIDGROUND = "midground"
    BACKGROUND = "background"


class VisualRelativeSize(str, Enum):
    SMALL = "small"
    MEDIUM_SMALL = "medium_small"
    MEDIUM = "medium"
    LARGE = "large"


class VisualVisibleExtent(str, Enum):
    FULL_BODY = "full_body"
    HALF_BODY = "half_body"
    PARTIAL = "partial"
    DISTANT_SILHOUETTE = "distant_silhouette"


@dataclass(frozen=True)
class VisualEntityPlacement:
    """Stable per-frame placement facts for one recurring text character."""

    frame_id: str
    scene_type: VisualSceneType | str
    instance_count: int
    horizontal_position: VisualHorizontalPosition | str
    depth_position: VisualDepthPosition | str
    relative_size: VisualRelativeSize | str
    relation_target: str
    spatial_relation: str
    support_relation: str
    action: str
    orientation: str
    visible_extent: VisualVisibleExtent | str
    visible_core_traits: Sequence[str]

    def __post_init__(self) -> None:
        frame_id = _require_text(
            "frame_id",
            self.frame_id,
            max_chars=MAX_VISUAL_ENTITY_FRAME_ID_CHARS,
        )
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(
            self,
            "scene_type",
            _enum_value(frame_id, "placement.scene_type", self.scene_type, VisualSceneType),
        )
        if (
            isinstance(self.instance_count, bool)
            or not isinstance(self.instance_count, int)
            or self.instance_count != 1
        ):
            raise ValueError(
                f"frame {frame_id}: placement.instance_count must equal 1"
            )
        object.__setattr__(self, "instance_count", 1)
        object.__setattr__(
            self,
            "horizontal_position",
            _enum_value(
                frame_id,
                "placement.horizontal_position",
                self.horizontal_position,
                VisualHorizontalPosition,
            ),
        )
        object.__setattr__(
            self,
            "depth_position",
            _enum_value(
                frame_id,
                "placement.depth_position",
                self.depth_position,
                VisualDepthPosition,
            ),
        )
        object.__setattr__(
            self,
            "relative_size",
            _enum_value(
                frame_id,
                "placement.relative_size",
                self.relative_size,
                VisualRelativeSize,
            ),
        )
        for field_name in (
            "relation_target",
            "spatial_relation",
            "support_relation",
            "action",
            "orientation",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_frame_text(
                    frame_id,
                    f"placement.{field_name}",
                    getattr(self, field_name),
                ),
            )
        object.__setattr__(
            self,
            "visible_extent",
            _enum_value(
                frame_id,
                "placement.visible_extent",
                self.visible_extent,
                VisualVisibleExtent,
            ),
        )
        object.__setattr__(
            self,
            "visible_core_traits",
            _frame_text_tuple(
                frame_id,
                "placement.visible_core_traits",
                self.visible_core_traits,
                allow_empty=False,
                max_items=MAX_VISUAL_ENTITY_CORE_TRAITS,
            ),
        )

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | "VisualEntityPlacement",
    ) -> "VisualEntityPlacement":
        if isinstance(source, cls):
            return source
        if not isinstance(source, Mapping):
            raise ValueError("visual entity placement must be a mapping")
        return cls(
            frame_id=source.get("frame_id", ""),
            scene_type=source.get("scene_type", ""),
            instance_count=source.get("instance_count", 0),
            horizontal_position=source.get("horizontal_position", ""),
            depth_position=source.get("depth_position", ""),
            relative_size=source.get("relative_size", ""),
            relation_target=source.get("relation_target", ""),
            spatial_relation=source.get("spatial_relation", ""),
            support_relation=source.get("support_relation", ""),
            action=source.get("action", ""),
            orientation=source.get("orientation", ""),
            visible_extent=source.get("visible_extent", ""),
            visible_core_traits=source.get("visible_core_traits") or (),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "scene_type": self.scene_type.value,
            "instance_count": self.instance_count,
            "horizontal_position": self.horizontal_position.value,
            "depth_position": self.depth_position.value,
            "relative_size": self.relative_size.value,
            "relation_target": self.relation_target,
            "spatial_relation": self.spatial_relation,
            "support_relation": self.support_relation,
            "action": self.action,
            "orientation": self.orientation,
            "visible_extent": self.visible_extent.value,
            "visible_core_traits": list(self.visible_core_traits),
        }


@dataclass(frozen=True)
class VisualEntitySceneFusion:
    """Executable scene-integration facts paired with one placement."""

    frame_id: str
    scene_type: VisualSceneType | str
    occlusion_relation: str
    perspective_relation: str
    contact_relation: str
    lighting_relation: str
    shadow_relation: str
    style_relation: str
    protected_subjects: Sequence[str] = field(default_factory=tuple)
    forbidden_compositions: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        frame_id = _require_text(
            "frame_id",
            self.frame_id,
            max_chars=MAX_VISUAL_ENTITY_FRAME_ID_CHARS,
        )
        object.__setattr__(self, "frame_id", frame_id)
        scene_type = _enum_value(
            frame_id,
            "scene_fusion.scene_type",
            self.scene_type,
            VisualSceneType,
        )
        object.__setattr__(self, "scene_type", scene_type)
        for field_name in (
            "occlusion_relation",
            "perspective_relation",
            "contact_relation",
            "lighting_relation",
            "shadow_relation",
            "style_relation",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_frame_text(
                    frame_id,
                    f"scene_fusion.{field_name}",
                    getattr(self, field_name),
                ),
            )
        physical_fields = (
            "perspective_relation",
            "contact_relation",
            "lighting_relation",
            "shadow_relation",
        )
        if scene_type is VisualSceneType.ABSTRACT_DIAGRAM:
            for field_name in physical_fields:
                if getattr(self, field_name) != NOT_APPLICABLE:
                    raise ValueError(
                        f"frame {frame_id}: scene_fusion.{field_name} must be "
                        f"{NOT_APPLICABLE} for an abstract diagram"
                    )
        else:
            for field_name in physical_fields:
                if getattr(self, field_name) == NOT_APPLICABLE:
                    raise ValueError(
                        f"frame {frame_id}: scene_fusion.{field_name} must contain "
                        "physical scene facts"
                    )
        object.__setattr__(
            self,
            "protected_subjects",
            _frame_text_tuple(
                frame_id,
                "scene_fusion.protected_subjects",
                self.protected_subjects,
                allow_empty=True,
                max_items=MAX_VISUAL_ENTITY_PROTECTED_SUBJECTS,
            ),
        )
        object.__setattr__(
            self,
            "forbidden_compositions",
            _frame_text_tuple(
                frame_id,
                "scene_fusion.forbidden_compositions",
                self.forbidden_compositions,
                allow_empty=False,
                max_items=MAX_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
            ),
        )

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | "VisualEntitySceneFusion",
    ) -> "VisualEntitySceneFusion":
        if isinstance(source, cls):
            return source
        if not isinstance(source, Mapping):
            raise ValueError("visual entity scene fusion must be a mapping")
        return cls(
            frame_id=source.get("frame_id", ""),
            scene_type=source.get("scene_type", ""),
            occlusion_relation=source.get("occlusion_relation", ""),
            perspective_relation=source.get("perspective_relation", ""),
            contact_relation=source.get("contact_relation", ""),
            lighting_relation=source.get("lighting_relation", ""),
            shadow_relation=source.get("shadow_relation", ""),
            style_relation=source.get("style_relation", ""),
            protected_subjects=source.get("protected_subjects") or (),
            forbidden_compositions=source.get("forbidden_compositions") or (),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "scene_type": self.scene_type.value,
            "occlusion_relation": self.occlusion_relation,
            "perspective_relation": self.perspective_relation,
            "contact_relation": self.contact_relation,
            "lighting_relation": self.lighting_relation,
            "shadow_relation": self.shadow_relation,
            "style_relation": self.style_relation,
            "protected_subjects": list(self.protected_subjects),
            "forbidden_compositions": list(self.forbidden_compositions),
        }


def _enum_value(
    frame_id: str,
    field_path: str,
    value: Any,
    enum_cls: type[Enum],
) -> Any:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        text = value.strip()
        for item in enum_cls:
            if text == item.value or text.lower() == item.name.lower():
                return item
    raise ValueError(f"frame {frame_id}: {field_path} must be a valid {enum_cls.__name__}")


def _require_text(
    field_name: str,
    value: Any,
    *,
    max_chars: int = MAX_VISUAL_ENTITY_FACT_CHARS,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    text = unicodedata.normalize("NFC", " ".join(value.strip().split()))
    if len(text) > max_chars:
        raise ValueError(f"{field_name} must be <= {max_chars} characters")
    return text


def _require_frame_text(frame_id: str, field_path: str, value: Any) -> str:
    try:
        return _require_text(field_path, value)
    except ValueError as exc:
        raise ValueError(f"frame {frame_id}: {field_path} must be a non-empty string") from exc


def _frame_text_tuple(
    frame_id: str,
    field_path: str,
    values: Sequence[Any],
    *,
    allow_empty: bool,
    max_items: int,
) -> tuple[str, ...]:
    if values is None:
        values = ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"frame {frame_id}: {field_path} must be a sequence of strings")
    if len(values) > max_items:
        raise ValueError(
            f"frame {frame_id}: {field_path} must contain at most {max_items} items"
        )
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _require_frame_text(frame_id, field_path, value)
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    if not allow_empty and not result:
        raise ValueError(f"frame {frame_id}: {field_path} must not be empty")
    return tuple(result)


__all__ = [
    "DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS",
    "MAX_VISUAL_ENTITY_CORE_TRAITS",
    "MAX_VISUAL_ENTITY_FACT_CHARS",
    "MAX_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS",
    "MAX_VISUAL_ENTITY_FRAME_ID_CHARS",
    "MAX_VISUAL_ENTITY_PROTECTED_SUBJECTS",
    "NOT_APPLICABLE",
    "VisualDepthPosition",
    "VisualEntityPlacement",
    "VisualEntitySceneFusion",
    "VisualHorizontalPosition",
    "VisualRelativeSize",
    "VisualSceneType",
    "VisualVisibleExtent",
]
