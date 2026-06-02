from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisibleTextPolicy

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
_MISSING = object()
_XIAOHEI_FIXED_ROLE_PATTERN_SPECS = (
    ("signature", re.compile(r"\bsignature\b", re.IGNORECASE)),
    ("character", re.compile(r"\bcharacter\b", re.IGNORECASE)),
    ("mascot", re.compile(r"\bmascot\b", re.IGNORECASE)),
    ("recurring figure", re.compile(r"\brecurring[-\s]+figure\b", re.IGNORECASE)),
    (
        "fixed figure",
        re.compile(r"\bfixed[-\s]+(?:recurring[-\s]+)?figure\b", re.IGNORECASE),
    ),
    ("xiaohei figure", re.compile(r"\bxiaohei[-\s]+figure\b", re.IGNORECASE)),
    (
        "figure repeated across panels",
        re.compile(
            r"\bfigure\b[^\n\r]*"
            r"(?:\b(?:appears?|appearing|in|marker|markers)\b[^\n\r]*)?"
            r"\b(?:every|each)\s+(?:frame|panel)\b",
            re.IGNORECASE,
        ),
    ),
)


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


@dataclass(frozen=True)
class CognitiveAnchorPlan:
    anchor_id: str
    anchor_kind: CognitiveAnchorKind
    anchor_claim: str
    anchor_question: str
    source_evidence_ids: tuple[str, ...]
    main_entities: tuple[str, ...]
    required_subjects: tuple[str, ...]
    source_text_excerpt: str
    confidence: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "anchor_id", _require_text(self.anchor_id, "anchor_id"))
        object.__setattr__(
            self,
            "anchor_kind",
            _required_enum_value(
                self.anchor_kind,
                CognitiveAnchorKind,
                "anchor_kind",
            ),
        )
        object.__setattr__(
            self,
            "anchor_claim",
            _require_text(self.anchor_claim, "anchor_claim"),
        )
        object.__setattr__(
            self,
            "anchor_question",
            _require_text(self.anchor_question, "anchor_question"),
        )
        object.__setattr__(
            self,
            "source_evidence_ids",
            _normalize_contract_text_tuple(self.source_evidence_ids, "source_evidence_ids"),
        )
        object.__setattr__(
            self,
            "main_entities",
            _normalize_contract_text_tuple(self.main_entities, "main_entities"),
        )
        object.__setattr__(
            self,
            "required_subjects",
            _normalize_contract_text_tuple(self.required_subjects, "required_subjects"),
        )
        source_text_excerpt = _require_text(
            self.source_text_excerpt,
            "source_text_excerpt",
        )
        object.__setattr__(self, "source_text_excerpt", source_text_excerpt)
        object.__setattr__(
            self,
            "confidence",
            _zero_to_one_float(self.confidence, "confidence"),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "anchor_id": self.anchor_id,
            "anchor_kind": self.anchor_kind.value,
            "anchor_claim": self.anchor_claim,
            "anchor_question": self.anchor_question,
            "source_evidence_ids": list(self.source_evidence_ids),
            "main_entities": list(self.main_entities),
            "required_subjects": list(self.required_subjects),
            "source_text_excerpt": self.source_text_excerpt,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ExplanationDiagramBrief:
    brief_id: str
    grammar: ExplanationDiagramGrammar
    primary_visual_task: PrimaryVisualTask
    diagram_title: str
    visual_metaphor: str
    composition_rules: tuple[str, ...]
    panel_plan: tuple[str, ...]
    forbidden_losses: tuple[str, ...]
    visible_text: VisibleTextResolution

    def __post_init__(self) -> None:
        object.__setattr__(self, "brief_id", _require_text(self.brief_id, "brief_id"))
        object.__setattr__(
            self,
            "grammar",
            _required_enum_value(
                self.grammar,
                ExplanationDiagramGrammar,
                "grammar",
            ),
        )
        object.__setattr__(
            self,
            "primary_visual_task",
            _required_enum_value(
                self.primary_visual_task,
                PrimaryVisualTask,
                "primary_visual_task",
            ),
        )
        object.__setattr__(
            self,
            "diagram_title",
            _require_text(self.diagram_title, "diagram_title"),
        )
        object.__setattr__(
            self,
            "visual_metaphor",
            _require_text(self.visual_metaphor, "visual_metaphor"),
        )
        object.__setattr__(
            self,
            "composition_rules",
            _normalize_contract_text_tuple(
                self.composition_rules,
                "composition_rules",
                require_non_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "panel_plan",
            _normalize_contract_text_tuple(
                self.panel_plan,
                "panel_plan",
                require_non_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "forbidden_losses",
            _normalize_contract_text_tuple(self.forbidden_losses, "forbidden_losses"),
        )
        if not isinstance(self.visible_text, VisibleTextResolution):
            raise TypeError("visible_text must be a VisibleTextResolution")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "brief_id": self.brief_id,
            "grammar": self.grammar.value,
            "primary_visual_task": self.primary_visual_task.value,
            "diagram_title": self.diagram_title,
            "visual_metaphor": self.visual_metaphor,
            "composition_rules": list(self.composition_rules),
            "panel_plan": list(self.panel_plan),
            "forbidden_losses": list(self.forbidden_losses),
            "visible_text": self.visible_text.to_dict(),
        }


@dataclass(frozen=True)
class SeriesVisualSignatureContract:
    enabled: bool
    role: SeriesVisualSignatureRole
    identity_profile_id: str | None
    participation_rule: str
    replacement_policy: Literal[
        "no_subject_replacement",
        "background_only",
        "may_lead_without_replacement",
    ]
    visual_weight: float
    forbidden_behaviors: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _bool_value(self.enabled, "enabled"))
        object.__setattr__(
            self,
            "role",
            _strict_enum_value(
                self.role,
                SeriesVisualSignatureRole,
                SeriesVisualSignatureRole.NONE,
                "role",
            ),
        )
        object.__setattr__(
            self,
            "identity_profile_id",
            _optional_text(self.identity_profile_id),
        )
        object.__setattr__(
            self,
            "participation_rule",
            _require_text(self.participation_rule, "participation_rule"),
        )
        object.__setattr__(
            self,
            "replacement_policy",
            _literal_value(
                self.replacement_policy,
                {
                    "no_subject_replacement",
                    "background_only",
                    "may_lead_without_replacement",
                },
                "replacement_policy",
            ),
        )
        object.__setattr__(
            self,
            "visual_weight",
            _zero_to_one_float(self.visual_weight, "visual_weight"),
        )
        _validate_signature_enabled_state(
            self.enabled,
            self.role,
            self.identity_profile_id,
            self.visual_weight,
        )
        object.__setattr__(
            self,
            "forbidden_behaviors",
            _normalize_contract_text_tuple(
                self.forbidden_behaviors,
                "forbidden_behaviors",
            ),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "enabled": self.enabled,
            "role": self.role.value,
            "identity_profile_id": self.identity_profile_id,
            "participation_rule": self.participation_rule,
            "replacement_policy": self.replacement_policy,
            "visual_weight": self.visual_weight,
            "forbidden_behaviors": list(self.forbidden_behaviors),
        }


@dataclass(frozen=True)
class DiagramRenderContract:
    render_style: DiagramRenderStyle
    canvas_aspect_ratio: DiagramAspectRatio
    diagram_panel_aspect_ratio: DiagramAspectRatio
    panel_inside_canvas: bool
    style_rules: tuple[str, ...]
    negative_style_rules: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "render_style",
            _required_enum_value(
                self.render_style,
                DiagramRenderStyle,
                "render_style",
            ),
        )
        object.__setattr__(
            self,
            "canvas_aspect_ratio",
            _required_enum_value(
                self.canvas_aspect_ratio,
                DiagramAspectRatio,
                "canvas_aspect_ratio",
            ),
        )
        object.__setattr__(
            self,
            "diagram_panel_aspect_ratio",
            _required_enum_value(
                self.diagram_panel_aspect_ratio,
                DiagramAspectRatio,
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
            "style_rules",
            _normalize_contract_text_tuple(
                self.style_rules,
                "style_rules",
                require_non_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "negative_style_rules",
            _normalize_contract_text_tuple(
                self.negative_style_rules,
                "negative_style_rules",
            ),
        )
        _validate_xiaohei_surface_style_rules(
            self.render_style,
            self.style_rules,
            self.negative_style_rules,
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "render_style": self.render_style.value,
            "canvas_aspect_ratio": self.canvas_aspect_ratio.value,
            "diagram_panel_aspect_ratio": self.diagram_panel_aspect_ratio.value,
            "panel_inside_canvas": self.panel_inside_canvas,
            "style_rules": list(self.style_rules),
            "negative_style_rules": list(self.negative_style_rules),
        }


@dataclass(frozen=True)
class ArticleConcretizationPlan:
    plan_id: str
    request: ArticleConcretizationRequest
    resolution: ArticleConcretizationResolution
    anchor: CognitiveAnchorPlan
    diagram: ExplanationDiagramBrief
    series_signature: SeriesVisualSignatureContract
    render: DiagramRenderContract

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _require_text(self.plan_id, "plan_id"))
        if not isinstance(self.request, ArticleConcretizationRequest):
            raise TypeError("request must be an ArticleConcretizationRequest")
        if not isinstance(self.resolution, ArticleConcretizationResolution):
            raise TypeError("resolution must be an ArticleConcretizationResolution")
        if not isinstance(self.anchor, CognitiveAnchorPlan):
            raise TypeError("anchor must be a CognitiveAnchorPlan")
        if not isinstance(self.diagram, ExplanationDiagramBrief):
            raise TypeError("diagram must be an ExplanationDiagramBrief")
        if not isinstance(self.series_signature, SeriesVisualSignatureContract):
            raise TypeError(
                "series_signature must be a SeriesVisualSignatureContract"
            )
        if not isinstance(self.render, DiagramRenderContract):
            raise TypeError("render must be a DiagramRenderContract")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "plan_id": self.plan_id,
            "request": self.request.to_dict(),
            "resolution": self.resolution.to_dict(),
            "anchor": self.anchor.to_dict(),
            "diagram": self.diagram.to_dict(),
            "series_signature": self.series_signature.to_dict(),
            "render": self.render.to_dict(),
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


def _required_enum_value(
    value: Any,
    enum_cls: type[Enum],
    field_name: str,
) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = _text_value(value)
    if not text:
        raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")
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


def _require_text(value: Any, field_name: str) -> str:
    text = _text_value(value)
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _optional_text(value: Any) -> str | None:
    text = _text_value(value)
    return text or None


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


def _normalize_contract_text_tuple(
    value: Any,
    field_name: str,
    *,
    require_non_empty: bool = False,
) -> tuple[str, ...]:
    if value is None:
        values = ()
    elif isinstance(value, str):
        values = (value,)
    elif isinstance(value, Sequence):
        values = value
    else:
        raise ValueError(f"{field_name} must be a list or tuple")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _text_value(item)
        if not text:
            raise ValueError(f"{field_name} must not contain blank values")
        if text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    if require_non_empty and not normalized:
        raise ValueError(f"{field_name} must not be empty")
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


def _validate_xiaohei_surface_style_rules(
    render_style: DiagramRenderStyle,
    style_rules: Sequence[str],
    negative_style_rules: Sequence[str],
) -> None:
    if render_style is not DiagramRenderStyle.XIAOHEI_HANDDRAWN:
        return
    for field_name, rules in (
        ("style_rules", style_rules),
        ("negative_style_rules", negative_style_rules),
    ):
        for rule in rules:
            if _xiaohei_fixed_role_match(rule):
                raise ValueError(
                    f"{field_name} for XIAOHEI_HANDDRAWN must describe surface "
                    "style only; fixed character/signature semantics belong in "
                    "SeriesVisualSignatureContract"
                )


def _xiaohei_fixed_role_match(rule: str) -> bool:
    return any(
        pattern.search(rule)
        for _, pattern in _XIAOHEI_FIXED_ROLE_PATTERN_SPECS
    )


def _validate_signature_enabled_state(
    enabled: bool,
    role: SeriesVisualSignatureRole,
    identity_profile_id: str | None,
    visual_weight: float,
) -> None:
    if enabled:
        if role in {SeriesVisualSignatureRole.NONE, SeriesVisualSignatureRole.AUTO}:
            raise ValueError("role must not be none or auto when enabled is true")
        return
    if role is not SeriesVisualSignatureRole.NONE:
        raise ValueError("role must be none when enabled is false")
    if identity_profile_id is not None:
        raise ValueError("identity_profile_id must be empty when enabled is false")
    if visual_weight != 0:
        raise ValueError("visual_weight must be 0 when enabled is false")


def _zero_to_one_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return number


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value.value if isinstance(value, Enum) else value).strip()


__all__ = [
    "ArticleConcretizationRequest",
    "ArticleConcretizationPlan",
    "ArticleConcretizationResolution",
    "CognitiveAnchorPlan",
    "CognitiveAnchorKind",
    "DiagramAspectRatio",
    "DiagramLayoutResolution",
    "DiagramRenderContract",
    "DiagramRenderStyle",
    "ExplanationDiagramBrief",
    "ExplanationDiagramGrammar",
    "SeriesVisualSignatureContract",
    "SeriesVisualSignatureRole",
    "VisibleTextResolution",
]
