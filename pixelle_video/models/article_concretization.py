from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pixelle_video.models.visual_planning_mode import VisibleTextPolicy

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
_MISSING = object()


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
        nested_data = dict(nested) if isinstance(nested, Mapping) else None
        merged = {**data, **nested_data} if nested_data is not None else data
        return cls(
            enabled=_merged_enabled_value(data, nested_data),
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


VisibleTextOrigin = Literal[
    "none",
    "source",
    "approved",
    "intersection",
    "symbolic_controlled",
    "free",
]
LayoutIntent = Literal["match_canvas", "panel_inside_canvas", "template_default"]


@dataclass(frozen=True)
class VisibleTextResolution:
    effective_policy: VisibleTextPolicy | str
    allowed_visible_text: Sequence[Any] = ()
    text_origin: VisibleTextOrigin = "none"
    warnings: Sequence[Any] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "effective_policy",
            _strict_enum_value(
                self.effective_policy,
                VisibleTextPolicy,
                VisibleTextPolicy.NO_VISIBLE_TEXT,
                "effective_policy",
            ),
        )
        object.__setattr__(
            self,
            "allowed_visible_text",
            _normalize_string_tuple(self.allowed_visible_text, "allowed_visible_text"),
        )
        object.__setattr__(
            self,
            "text_origin",
            _literal_value(
                self.text_origin,
                {
                    "none",
                    "source",
                    "approved",
                    "intersection",
                    "symbolic_controlled",
                    "free",
                },
                "text_origin",
            ),
        )
        object.__setattr__(
            self,
            "warnings",
            _normalize_string_tuple(self.warnings, "warnings"),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "effective_policy": self.effective_policy.value,
            "allowed_visible_text": list(self.allowed_visible_text),
            "text_origin": self.text_origin,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class DiagramLayoutResolution:
    canvas_aspect_ratio: DiagramAspectRatio | str
    diagram_panel_aspect_ratio: DiagramAspectRatio | str
    panel_inside_canvas: bool
    layout_intent: LayoutIntent
    warnings: Sequence[Any] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canvas_aspect_ratio",
            _strict_enum_value(
                self.canvas_aspect_ratio,
                DiagramAspectRatio,
                DiagramAspectRatio.AUTO,
                "canvas_aspect_ratio",
            ),
        )
        object.__setattr__(
            self,
            "diagram_panel_aspect_ratio",
            _strict_enum_value(
                self.diagram_panel_aspect_ratio,
                DiagramAspectRatio,
                DiagramAspectRatio.AUTO,
                "diagram_panel_aspect_ratio",
            ),
        )
        object.__setattr__(
            self,
            "panel_inside_canvas",
            _bool_value(self.panel_inside_canvas, "panel_inside_canvas"),
        )
        object.__setattr__(
            self,
            "layout_intent",
            _literal_value(
                self.layout_intent,
                {"match_canvas", "panel_inside_canvas", "template_default"},
                "layout_intent",
            ),
        )
        object.__setattr__(
            self,
            "warnings",
            _normalize_string_tuple(self.warnings, "warnings"),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "canvas_aspect_ratio": self.canvas_aspect_ratio.value,
            "diagram_panel_aspect_ratio": self.diagram_panel_aspect_ratio.value,
            "panel_inside_canvas": self.panel_inside_canvas,
            "layout_intent": self.layout_intent,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ArticleConcretizationResolution:
    request: ArticleConcretizationRequest
    enabled: bool
    effective_anchor_kind: CognitiveAnchorKind | str
    effective_diagram_grammar: ExplanationDiagramGrammar | str
    effective_signature_role: SeriesVisualSignatureRole | str
    effective_render_style: DiagramRenderStyle | str
    layout: DiagramLayoutResolution
    visible_text: VisibleTextResolution
    approved_labels: Sequence[Any]
    warnings: Sequence[Any]
    errors: Sequence[Any]
    fallback_used: bool
    fallback_reason: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, ArticleConcretizationRequest):
            raise TypeError("request must be an ArticleConcretizationRequest")
        if not isinstance(self.layout, DiagramLayoutResolution):
            raise TypeError("layout must be a DiagramLayoutResolution")
        if not isinstance(self.visible_text, VisibleTextResolution):
            raise TypeError("visible_text must be a VisibleTextResolution")
        object.__setattr__(self, "enabled", _bool_value(self.enabled, "enabled"))
        object.__setattr__(
            self,
            "effective_anchor_kind",
            _strict_enum_value(
                self.effective_anchor_kind,
                CognitiveAnchorKind,
                CognitiveAnchorKind.AUTO,
                "effective_anchor_kind",
            ),
        )
        object.__setattr__(
            self,
            "effective_diagram_grammar",
            _strict_enum_value(
                self.effective_diagram_grammar,
                ExplanationDiagramGrammar,
                ExplanationDiagramGrammar.AUTO,
                "effective_diagram_grammar",
            ),
        )
        object.__setattr__(
            self,
            "effective_signature_role",
            _strict_enum_value(
                self.effective_signature_role,
                SeriesVisualSignatureRole,
                SeriesVisualSignatureRole.NONE,
                "effective_signature_role",
            ),
        )
        object.__setattr__(
            self,
            "effective_render_style",
            _strict_enum_value(
                self.effective_render_style,
                DiagramRenderStyle,
                DiagramRenderStyle.AUTO,
                "effective_render_style",
            ),
        )
        object.__setattr__(
            self,
            "approved_labels",
            _normalize_string_tuple(self.approved_labels, "approved_labels"),
        )
        object.__setattr__(
            self,
            "warnings",
            _normalize_string_tuple(self.warnings, "warnings"),
        )
        object.__setattr__(
            self,
            "errors",
            _normalize_string_tuple(self.errors, "errors"),
        )
        object.__setattr__(
            self,
            "fallback_used",
            _bool_value(self.fallback_used, "fallback_used"),
        )
        object.__setattr__(
            self,
            "fallback_reason",
            _optional_limited_text(
                self.fallback_reason,
                "fallback_reason",
                max_length=500,
            ),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "request": self.request.to_dict(),
            "enabled": self.enabled,
            "effective_anchor_kind": self.effective_anchor_kind.value,
            "effective_diagram_grammar": self.effective_diagram_grammar.value,
            "effective_signature_role": self.effective_signature_role.value,
            "effective_render_style": self.effective_render_style.value,
            "layout": self.layout.to_dict(),
            "visible_text": self.visible_text.to_dict(),
            "approved_labels": list(self.approved_labels),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


def _merged_enabled_value(
    flat: Mapping[str, Any],
    nested: Mapping[str, Any] | None,
) -> Any:
    if nested is not None:
        nested_value = _enabled_alias_value(nested, _MISSING)
        if nested_value is not _MISSING:
            return nested_value
    return _enabled_alias_value(flat, False)


def _enabled_alias_value(source: Mapping[str, Any], default: Any) -> Any:
    if "enabled" in source:
        return source["enabled"]
    return source.get("article_concretization_enabled", default)


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


def _literal_value(value: Any, allowed_values: set[str], field_name: str) -> str:
    text = str(value.value if isinstance(value, Enum) else value or "").strip()
    if text in allowed_values:
        return text
    raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed_values))}")


def _normalize_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Sequence):
        values = value
    else:
        raise ValueError(f"{field_name} must be a list or tuple")

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
    "ArticleConcretizationResolution",
    "CognitiveAnchorKind",
    "DiagramAspectRatio",
    "DiagramLayoutResolution",
    "DiagramRenderStyle",
    "ExplanationDiagramGrammar",
    "SeriesVisualSignatureRole",
    "VisibleTextResolution",
]
