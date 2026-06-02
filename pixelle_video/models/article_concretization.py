from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pixelle_video.models.visual_planning_mode import VisibleTextPolicy

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


class CognitiveAnchorKind(str, Enum):
    AUTO = "auto"
    JUDGMENT = "judgment"
    CAUSAL_MECHANISM = "causal_mechanism"
    PROCESS = "process"
    STRUCTURE = "structure"
    STATE = "state"
    METAPHOR = "metaphor"
    CONTRAST = "contrast"
    RELATIONSHIP = "relationship"
    EVIDENCE = "evidence"
    DECISION_PATH = "decision_path"
    STATE_MACHINE = "state_machine"


class ExplanationDiagramGrammar(str, Enum):
    AUTO = "auto"
    SINGLE_EXPLANATION_IMAGE = "single_explanation_image"
    MULTI_PANEL_COMIC = "multi_panel_comic"
    PROCESS_FLOW = "process_flow"
    STRUCTURE_MAP = "structure_map"
    CONTRAST_BOARD = "contrast_board"
    RELATIONSHIP_MAP = "relationship_map"
    METAPHOR_SCENE = "metaphor_scene"
    DECISION_TREE = "decision_tree"
    STATE_MACHINE = "state_machine"
    EVIDENCE_MAP = "evidence_map"


class SeriesVisualSignatureRole(str, Enum):
    NONE = "none"
    AUTO = "auto"
    CORE_ACTOR = "core_actor"
    SILENT_WITNESS = "silent_witness"
    OPERATOR = "operator"
    GUIDE = "guide"
    OBSTACLE = "obstacle"
    CONTAINER = "container"
    BACKGROUND_MARK = "background_mark"


class DiagramRenderStyle(str, Enum):
    AUTO = "auto"
    XIAOHEI_HANDDRAWN = "xiaohei_handdrawn"
    EDITORIAL_DIAGRAM = "editorial_diagram"
    CLEAN_VECTOR = "clean_vector"
    CINEMATIC_METAPHOR = "cinematic_metaphor"
    BRAND_KV = "brand_kv"
    THREE_D_CONCEPT = "three_d_concept"
    INK_COLLAGE = "ink_collage"


class DiagramAspectRatio(str, Enum):
    AUTO = "auto"
    LANDSCAPE_16_9 = "landscape_16_9"
    SQUARE_1_1 = "square_1_1"
    PORTRAIT_4_5 = "portrait_4_5"
    VERTICAL_9_16 = "vertical_9_16"
    TEMPLATE = "template"


@dataclass(frozen=True)
class ArticleConcretizationRequest:
    enabled: bool = False
    cognitive_anchor_kind: CognitiveAnchorKind | str = CognitiveAnchorKind.AUTO
    explanation_diagram_grammar: (
        ExplanationDiagramGrammar | str
    ) = ExplanationDiagramGrammar.AUTO
    series_visual_signature_role: (
        SeriesVisualSignatureRole | str
    ) = SeriesVisualSignatureRole.NONE
    diagram_render_style: DiagramRenderStyle | str = DiagramRenderStyle.AUTO
    diagram_aspect_ratio: DiagramAspectRatio | str = DiagramAspectRatio.AUTO
    diagram_visible_text_policy: VisibleTextPolicy | str = VisibleTextPolicy.NO_VISIBLE_TEXT
    diagram_approved_labels: Sequence[Any] | str | None = ()
    diagram_user_intent_hint: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "enabled",
            _bool_value(self.enabled, "enabled"),
        )
        object.__setattr__(
            self,
            "cognitive_anchor_kind",
            _strict_enum_value(
                self.cognitive_anchor_kind,
                CognitiveAnchorKind,
                CognitiveAnchorKind.AUTO,
                "cognitive_anchor_kind",
            ),
        )
        object.__setattr__(
            self,
            "explanation_diagram_grammar",
            _strict_enum_value(
                self.explanation_diagram_grammar,
                ExplanationDiagramGrammar,
                ExplanationDiagramGrammar.AUTO,
                "explanation_diagram_grammar",
            ),
        )
        object.__setattr__(
            self,
            "series_visual_signature_role",
            _strict_enum_value(
                self.series_visual_signature_role,
                SeriesVisualSignatureRole,
                SeriesVisualSignatureRole.NONE,
                "series_visual_signature_role",
            ),
        )
        object.__setattr__(
            self,
            "diagram_render_style",
            _strict_enum_value(
                self.diagram_render_style,
                DiagramRenderStyle,
                DiagramRenderStyle.AUTO,
                "diagram_render_style",
            ),
        )
        object.__setattr__(
            self,
            "diagram_aspect_ratio",
            _strict_enum_value(
                self.diagram_aspect_ratio,
                DiagramAspectRatio,
                DiagramAspectRatio.AUTO,
                "diagram_aspect_ratio",
            ),
        )
        object.__setattr__(
            self,
            "diagram_visible_text_policy",
            _strict_enum_value(
                self.diagram_visible_text_policy,
                VisibleTextPolicy,
                VisibleTextPolicy.NO_VISIBLE_TEXT,
                "diagram_visible_text_policy",
            ),
        )
        object.__setattr__(
            self,
            "diagram_approved_labels",
            _normalize_approved_labels(self.diagram_approved_labels),
        )
        object.__setattr__(
            self,
            "diagram_user_intent_hint",
            _optional_limited_text(
                self.diagram_user_intent_hint,
                "diagram_user_intent_hint",
                max_length=500,
            ),
        )

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | None,
    ) -> "ArticleConcretizationRequest":
        data = dict(source or {})
        nested = data.get("article_concretization")
        merged = {**data, **dict(nested)} if isinstance(nested, Mapping) else data
        return cls(
            enabled=_merged_enabled_value(merged),
            cognitive_anchor_kind=merged.get("cognitive_anchor_kind", CognitiveAnchorKind.AUTO),
            explanation_diagram_grammar=merged.get(
                "explanation_diagram_grammar",
                ExplanationDiagramGrammar.AUTO,
            ),
            series_visual_signature_role=merged.get(
                "series_visual_signature_role",
                SeriesVisualSignatureRole.NONE,
            ),
            diagram_render_style=merged.get(
                "diagram_render_style",
                DiagramRenderStyle.AUTO,
            ),
            diagram_aspect_ratio=merged.get(
                "diagram_aspect_ratio",
                DiagramAspectRatio.AUTO,
            ),
            diagram_visible_text_policy=merged.get(
                "diagram_visible_text_policy",
                VisibleTextPolicy.NO_VISIBLE_TEXT,
            ),
            diagram_approved_labels=merged.get("diagram_approved_labels", ()),
            diagram_user_intent_hint=merged.get("diagram_user_intent_hint"),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "enabled": self.enabled,
            "cognitive_anchor_kind": self.cognitive_anchor_kind.value,
            "explanation_diagram_grammar": self.explanation_diagram_grammar.value,
            "series_visual_signature_role": self.series_visual_signature_role.value,
            "diagram_render_style": self.diagram_render_style.value,
            "diagram_aspect_ratio": self.diagram_aspect_ratio.value,
            "diagram_visible_text_policy": self.diagram_visible_text_policy.value,
            "diagram_approved_labels": list(self.diagram_approved_labels),
            "diagram_user_intent_hint": self.diagram_user_intent_hint,
        }


def _merged_enabled_value(source: Mapping[str, Any]) -> Any:
    if "enabled" in source:
        return source["enabled"]
    return source.get("article_concretization_enabled", False)


def _strict_enum_value(
    value: Any,
    enum_cls: type[Enum],
    default: Any,
    field_name: str,
) -> Any:
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    text = str(value.value if isinstance(value, Enum) else value).strip()
    if not text:
        return default
    for item in enum_cls:
        if text.lower() == str(item.value).lower() or text.lower() == item.name.lower():
            return item
    raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")


def _bool_value(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off", ""}:
            return False
        raise ValueError(f"{field_name} must be a boolean value")
    return bool(value)


def _optional_limited_text(value: Any, field_name: str, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value.value if isinstance(value, Enum) else value).strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer")
    return text


def _normalize_approved_labels(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, Sequence):
        values = value
    else:
        raise ValueError("diagram_approved_labels must be a list, tuple, or CSV string")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item is None:
            continue
        text = str(item.value if isinstance(item, Enum) else item).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return tuple(normalized)


__all__ = [
    "ArticleConcretizationRequest",
    "CognitiveAnchorKind",
    "DiagramAspectRatio",
    "DiagramRenderStyle",
    "ExplanationDiagramGrammar",
    "SeriesVisualSignatureRole",
]
