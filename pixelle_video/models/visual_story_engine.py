from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from pixelle_video.models.content_bound_ip import IPParticipationMechanism
from pixelle_video.models.ip_duty import (
    IPDutyPlan,
    IPDutyPreset,
    IPPresentationForm,
    build_default_ip_duty_plan,
    duty_from_legacy_role,
    duty_from_route_type,
)

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]

DEFAULT_ROUTE_CANDIDATE_COUNT = 5
DEFAULT_WEB_AUTO_SELECT_SECONDS = 10
DEFAULT_CONFIDENT_SCORE = 0.78
DEFAULT_CONFIDENT_MARGIN = 0.08


class ArticleInputKind(str, Enum):
    TOPIC = "topic"
    SHORT_COPY = "short_copy"
    FULL_ARTICLE = "full_article"
    NOVEL_OR_BOOK = "novel_or_book"
    BRAND_SCRIPT = "brand_script"
    UNKNOWN = "unknown"


class VisualRouteType(str, Enum):
    COGNITIVE_EXPLAINER = "cognitive_explainer"
    PHILOSOPHICAL_METAPHOR = "philosophical_metaphor"
    MATHEMATICAL_MODEL = "mathematical_model"
    SCIENTIFIC_ANALOGY = "scientific_analogy"
    ABSURD_COMIC = "absurd_comic"
    CARTOON_STORY = "cartoon_story"
    CINEMATIC_SCENE = "cinematic_scene"
    BRAND_KEY_VISUAL = "brand_key_visual"
    EDITORIAL_DIAGRAM = "editorial_diagram"
    STRUCTURE_MAP = "structure_map"
    PROCESS_MAP = "process_map"
    RELATIONSHIP_MAP = "relationship_map"
    EMOTIONAL_THEATER = "emotional_theater"
    ARCHIVE_INVESTIGATION = "archive_investigation"
    GAME_LEVEL = "game_level"
    COURTROOM_ARGUMENT = "courtroom_argument"
    MECHANICAL_CUTAWAY = "mechanical_cutaway"
    CUSTOM = "custom"


class VisualStyleFamily(str, Enum):
    HANDDRAWN_EXPLAINER = "handdrawn_explainer"
    EDITORIAL_DIAGRAM = "editorial_diagram"
    CLEAN_VECTOR = "clean_vector"
    CINEMATIC_METAPHOR = "cinematic_metaphor"
    BRAND_KV = "brand_kv"
    CARTOON_COMIC = "cartoon_comic"
    THREE_D_CONCEPT = "three_d_concept"
    INK_COLLAGE = "ink_collage"
    PHOTOREAL_CONCEPT = "photoreal_concept"
    MIXED_MEDIA = "mixed_media"
    CUSTOM = "custom"


class VisualSignatureRole(str, Enum):
    NONE = "none"
    CORE_ACTOR = "core_actor"
    SILENT_WITNESS = "silent_witness"
    OPERATOR = "operator"
    GUIDE = "guide"
    OBSTACLE = "obstacle"
    CONTAINER = "container"
    BACKGROUND_MARK = "background_mark"
    SYMBOL = "symbol"
    NARRATOR = "narrator"


class IPVisibilityLevel(str, Enum):
    NONE = "none"
    SYMBOLIC = "symbolic"
    BACKGROUND_MARK = "background_mark"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    HERO = "hero"


class StyleHarmonizationMode(str, Enum):
    MATCH_ROUTE_STYLE = "match_route_style"
    PRESERVE_IP_STYLE_AS_SIGNATURE = "preserve_ip_style_as_signature"
    HYBRID_LAYERED = "hybrid_layered"
    SYMBOLIC_PROJECTION = "symbolic_projection"


class RouteSelectionSource(str, Enum):
    MODEL_RECOMMENDED = "model_recommended"
    SYSTEM_DEFAULT = "system_default"
    USER_SELECTED = "user_selected"
    AUTO_TIMEOUT = "auto_timeout"
    API_AUTO = "api_auto"
    FALLBACK_CONSERVATIVE = "fallback_conservative"


@dataclass(frozen=True)
class EvidenceSpan:
    evidence_id: str
    quote: str
    role: str = "support"
    start_char: int | None = None
    end_char: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _require_text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "quote", _require_text(self.quote, "quote"))
        object.__setattr__(self, "role", _optional_text(self.role) or "support")
        object.__setattr__(self, "start_char", _optional_int(self.start_char, "start_char"))
        object.__setattr__(self, "end_char", _optional_int(self.end_char, "end_char"))
        if self.start_char is not None and self.end_char is not None and self.start_char > self.end_char:
            raise ValueError("start_char must be <= end_char")

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | Any) -> "EvidenceSpan":
        if not isinstance(source, Mapping):
            quote = _optional_text(source) or "source evidence"
            return cls(
                evidence_id="evidence-1",
                quote=quote,
                role="support",
            )
        return cls(
            evidence_id=source.get("evidence_id") or source.get("id") or "evidence-1",
            quote=source.get("quote") or source.get("text") or source.get("source_text") or "source evidence",
            role=source.get("role") or source.get("evidence_role") or "support",
            start_char=source.get("start_char"),
            end_char=source.get("end_char"),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "evidence_id": self.evidence_id,
            "quote": self.quote,
            "role": self.role,
            "start_char": self.start_char,
            "end_char": self.end_char,
        }


@dataclass(frozen=True)
class ArticleVisualUnderstanding:
    input_kind: ArticleInputKind | str
    summary: str
    core_claim: str
    central_problem: str
    tone: str = ""
    key_subjects: Sequence[Any] = ()
    cognitive_opportunities: Sequence[Any] = ()
    metaphor_opportunities: Sequence[Any] = ()
    unsafe_or_sensitive_flags: Sequence[Any] = ()
    evidence_spans: Sequence[EvidenceSpan | Mapping[str, Any]] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_kind", _enum_value(self.input_kind, ArticleInputKind, ArticleInputKind.UNKNOWN))
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(self, "core_claim", _require_text(self.core_claim, "core_claim"))
        object.__setattr__(self, "central_problem", _optional_text(self.central_problem) or self.core_claim)
        object.__setattr__(self, "tone", _optional_text(self.tone))
        object.__setattr__(self, "key_subjects", _text_tuple(self.key_subjects))
        object.__setattr__(self, "cognitive_opportunities", _text_tuple(self.cognitive_opportunities))
        object.__setattr__(self, "metaphor_opportunities", _text_tuple(self.metaphor_opportunities))
        object.__setattr__(self, "unsafe_or_sensitive_flags", _text_tuple(self.unsafe_or_sensitive_flags))
        object.__setattr__(self, "evidence_spans", tuple(_evidence(value) for value in self.evidence_spans))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "ArticleVisualUnderstanding":
        if not isinstance(source, Mapping):
            source = {}
        return cls(
            input_kind=source.get("input_kind") or source.get("source_kind") or ArticleInputKind.UNKNOWN,
            summary=source.get("summary") or source.get("article_summary") or source.get("core_claim") or "article summary",
            core_claim=source.get("core_claim") or source.get("main_claim") or source.get("summary") or "article claim",
            central_problem=source.get("central_problem") or source.get("problem") or source.get("core_claim") or "article problem",
            tone=source.get("tone") or source.get("emotional_tone") or "",
            key_subjects=source.get("key_subjects") or source.get("main_entities") or (),
            cognitive_opportunities=source.get("cognitive_opportunities") or source.get("visualizable_points") or (),
            metaphor_opportunities=source.get("metaphor_opportunities") or (),
            unsafe_or_sensitive_flags=source.get("unsafe_or_sensitive_flags") or source.get("risk_flags") or (),
            evidence_spans=source.get("evidence_spans") or source.get("source_evidence") or (),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "input_kind": self.input_kind.value,
            "summary": self.summary,
            "core_claim": self.core_claim,
            "central_problem": self.central_problem,
            "tone": self.tone,
            "key_subjects": list(self.key_subjects),
            "cognitive_opportunities": list(self.cognitive_opportunities),
            "metaphor_opportunities": list(self.metaphor_opportunities),
            "unsafe_or_sensitive_flags": list(self.unsafe_or_sensitive_flags),
            "evidence_spans": [span.to_dict() for span in self.evidence_spans],
        }


@dataclass(frozen=True)
class VisualRouteScores:
    """Route scores with one deterministic content-only ranking authority.

    ``ip_compatibility`` and ``final`` remain accepted solely so historical
    serialized payloads keep loading during migration. Neither field is allowed
    to influence route ranking. Recurring visual identity is owned by the
    canonical V4.6 projection stage, and model-supplied final scores are treated
    as untrusted derived data.
    """

    content_fit: float = 0.0
    memorability: float = 0.0
    ip_compatibility: float = 0.0
    channel_consistency: float = 0.0
    production_reliability: float = 0.0
    risk: float = 0.0
    final: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "content_fit",
            "memorability",
            "ip_compatibility",
            "channel_consistency",
            "production_reliability",
            "risk",
        ):
            object.__setattr__(self, name, _score(getattr(self, name), name))
        if self.final is not None:
            object.__setattr__(self, "final", _score(self.final, "final"))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None) -> "VisualRouteScores":
        source = dict(source or {})
        return cls(
            content_fit=source.get("content_fit", source.get("content_fit_score", 0.0)),
            memorability=source.get(
                "memorability",
                source.get(
                    "visual_memorability",
                    source.get("visual_memorability_score", 0.0),
                ),
            ),
            ip_compatibility=source.get(
                "ip_compatibility",
                source.get("ip_compatibility_score", 0.0),
            ),
            channel_consistency=source.get(
                "channel_consistency",
                source.get(
                    "channel_fit",
                    source.get("channel_consistency_score", 0.0),
                ),
            ),
            production_reliability=source.get(
                "production_reliability",
                source.get("production_reliability_score", 0.0),
            ),
            risk=source.get("risk", source.get("risk_score", 0.0)),
            final=source.get("final", source.get("final_score")),
        )

    def computed_final(self) -> float:
        return _clamp(
            self.content_fit * 0.38
            + self.memorability * 0.22
            + self.channel_consistency * 0.17
            + self.production_reliability * 0.23
            - self.risk * 0.22
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "content_fit": self.content_fit,
            "memorability": self.memorability,
            "ip_compatibility": self.ip_compatibility,
            "channel_consistency": self.channel_consistency,
            "production_reliability": self.production_reliability,
            "risk": self.risk,
            "final": self.computed_final(),
        }


@dataclass(frozen=True)
class VisualRouteCandidate:
    route_id: str
    route_name: str
    route_type: VisualRouteType | str
    visual_premise: str
    why_it_fits_article: str
    frame_storytelling_logic: str = ""
    style_family: VisualStyleFamily | str = VisualStyleFamily.HANDDRAWN_EXPLAINER
    recommended_ip_role: VisualSignatureRole | str = VisualSignatureRole.SILENT_WITNESS
    ip_fit_reason: str = ""
    route_specific_rules: Sequence[Any] = ()
    risk_notes: Sequence[Any] = ()
    sample_frame_premise: str = ""
    scores: VisualRouteScores | Mapping[str, Any] = field(default_factory=VisualRouteScores)

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_name", _require_text(self.route_name, "route_name"))
        object.__setattr__(self, "route_id", _slug_or_fallback(self.route_id, self.route_name))
        object.__setattr__(self, "route_type", _enum_value(self.route_type, VisualRouteType, VisualRouteType.CUSTOM))
        object.__setattr__(self, "visual_premise", _require_text(self.visual_premise, "visual_premise"))
        object.__setattr__(self, "why_it_fits_article", _require_text(self.why_it_fits_article, "why_it_fits_article"))
        object.__setattr__(self, "frame_storytelling_logic", _optional_text(self.frame_storytelling_logic))
        object.__setattr__(self, "style_family", _enum_value(self.style_family, VisualStyleFamily, VisualStyleFamily.CUSTOM))
        object.__setattr__(self, "recommended_ip_role", _enum_value(self.recommended_ip_role, VisualSignatureRole, VisualSignatureRole.SILENT_WITNESS))
        object.__setattr__(self, "ip_fit_reason", _optional_text(self.ip_fit_reason))
        object.__setattr__(self, "route_specific_rules", _text_tuple(self.route_specific_rules))
        object.__setattr__(self, "risk_notes", _text_tuple(self.risk_notes))
        object.__setattr__(self, "sample_frame_premise", _optional_text(self.sample_frame_premise))
        if not isinstance(self.scores, VisualRouteScores):
            object.__setattr__(self, "scores", VisualRouteScores.from_mapping(self.scores if isinstance(self.scores, Mapping) else {}))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "VisualRouteCandidate":
        data = dict(source)
        return cls(
            route_id=data.get("route_id") or data.get("id") or data.get("name") or data.get("route_name") or "",
            route_name=data.get("route_name") or data.get("name") or data.get("title") or "visual route",
            route_type=data.get("route_type") or data.get("type") or VisualRouteType.CUSTOM,
            visual_premise=data.get("visual_premise") or data.get("premise") or "visualize the article meaning",
            why_it_fits_article=data.get("why_it_fits_article") or data.get("why_it_fits") or data.get("reason") or "fits the article",
            frame_storytelling_logic=data.get("frame_storytelling_logic") or data.get("storytelling_logic") or "",
            style_family=data.get("style_family") or data.get("render_style") or VisualStyleFamily.HANDDRAWN_EXPLAINER,
            recommended_ip_role=data.get("recommended_ip_role") or data.get("ip_role") or VisualSignatureRole.SILENT_WITNESS,
            ip_fit_reason=data.get("ip_fit_reason") or data.get("ip_reason") or "",
            route_specific_rules=data.get("route_specific_rules") or data.get("rules") or (),
            risk_notes=data.get("risk_notes") or data.get("risks") or (),
            sample_frame_premise=data.get("sample_frame_premise") or data.get("sample") or "",
            scores=VisualRouteScores.from_mapping(data.get("scores") if isinstance(data.get("scores"), Mapping) else data),
        )

    @property
    def final_score(self) -> float:
        return self.scores.computed_final()

    def with_scores(self, scores: VisualRouteScores) -> "VisualRouteCandidate":
        return replace(self, scores=scores)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "route_id": self.route_id,
            "route_name": self.route_name,
            "route_type": self.route_type.value,
            "visual_premise": self.visual_premise,
            "why_it_fits_article": self.why_it_fits_article,
            "frame_storytelling_logic": self.frame_storytelling_logic,
            "style_family": self.style_family.value,
            "recommended_ip_role": self.recommended_ip_role.value,
            "ip_fit_reason": self.ip_fit_reason,
            "route_specific_rules": list(self.route_specific_rules),
            "risk_notes": list(self.risk_notes),
            "sample_frame_premise": self.sample_frame_premise,
            "scores": self.scores.to_dict(),
        }


@dataclass(frozen=True)
class IPRouteCompatibilityReport:
    route_id: str
    compatible: bool
    recommended_role: VisualSignatureRole | str
    recommended_visibility: IPVisibilityLevel | str
    compatibility_score: float
    reason: str
    style_conflict: str = ""
    mitigation_rules: Sequence[Any] = ()
    safety_warnings: Sequence[Any] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", _require_text(self.route_id, "route_id"))
        object.__setattr__(self, "compatible", bool(self.compatible))
        object.__setattr__(self, "recommended_role", _enum_value(self.recommended_role, VisualSignatureRole, VisualSignatureRole.SILENT_WITNESS))
        object.__setattr__(self, "recommended_visibility", _enum_value(self.recommended_visibility, IPVisibilityLevel, IPVisibilityLevel.LOW))
        object.__setattr__(self, "compatibility_score", _score(self.compatibility_score, "compatibility_score"))
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))
        object.__setattr__(self, "style_conflict", _optional_text(self.style_conflict))
        object.__setattr__(self, "mitigation_rules", _text_tuple(self.mitigation_rules))
        object.__setattr__(self, "safety_warnings", _text_tuple(self.safety_warnings))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "IPRouteCompatibilityReport":
        return cls(
            route_id=source.get("route_id") or "route",
            compatible=source.get("compatible", True),
            recommended_role=source.get("recommended_role") or source.get("ip_role") or VisualSignatureRole.SILENT_WITNESS,
            recommended_visibility=source.get("recommended_visibility") or source.get("ip_visibility") or IPVisibilityLevel.LOW,
            compatibility_score=source.get("compatibility_score", source.get("score", 0.7)),
            reason=source.get("reason") or "compatible by default",
            style_conflict=source.get("style_conflict") or "",
            mitigation_rules=source.get("mitigation_rules") or (),
            safety_warnings=source.get("safety_warnings") or (),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "route_id": self.route_id,
            "compatible": self.compatible,
            "recommended_role": self.recommended_role.value,
            "recommended_visibility": self.recommended_visibility.value,
            "compatibility_score": self.compatibility_score,
            "reason": self.reason,
            "style_conflict": self.style_conflict,
            "mitigation_rules": list(self.mitigation_rules),
            "safety_warnings": list(self.safety_warnings),
        }


@dataclass(frozen=True)
class RouteSelectionDecision:
    recommended_route_id: str
    selected_route_id: str
    selection_source: RouteSelectionSource | str
    reason: str
    auto_select_after_seconds: int = DEFAULT_WEB_AUTO_SELECT_SECONDS
    user_overrode: bool = False
    low_confidence: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "recommended_route_id", _require_text(self.recommended_route_id, "recommended_route_id"))
        object.__setattr__(self, "selected_route_id", _require_text(self.selected_route_id, "selected_route_id"))
        object.__setattr__(self, "selection_source", _enum_value(self.selection_source, RouteSelectionSource, RouteSelectionSource.API_AUTO))
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))
        object.__setattr__(self, "auto_select_after_seconds", max(0, int(self.auto_select_after_seconds)))
        object.__setattr__(self, "user_overrode", bool(self.user_overrode))
        object.__setattr__(self, "low_confidence", bool(self.low_confidence))
        object.__setattr__(self, "fallback_used", bool(self.fallback_used))
        object.__setattr__(self, "fallback_reason", _optional_text(self.fallback_reason))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "recommended_route_id": self.recommended_route_id,
            "selected_route_id": self.selected_route_id,
            "selection_source": self.selection_source.value,
            "reason": self.reason,
            "auto_select_after_seconds": self.auto_select_after_seconds,
            "user_overrode": self.user_overrode,
            "low_confidence": self.low_confidence,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class StyleHarmonizationPlan:
    route_id: str
    mode: StyleHarmonizationMode | str
    ip_style_policy: str
    scene_style_policy: str
    boundary_rule: str
    positive_rules: Sequence[Any] = ()
    negative_rules: Sequence[Any] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", _require_text(self.route_id, "route_id"))
        object.__setattr__(self, "mode", _enum_value(self.mode, StyleHarmonizationMode, StyleHarmonizationMode.HYBRID_LAYERED))
        object.__setattr__(self, "ip_style_policy", _require_text(self.ip_style_policy, "ip_style_policy"))
        object.__setattr__(self, "scene_style_policy", _require_text(self.scene_style_policy, "scene_style_policy"))
        object.__setattr__(self, "boundary_rule", _require_text(self.boundary_rule, "boundary_rule"))
        object.__setattr__(self, "positive_rules", _text_tuple(self.positive_rules))
        object.__setattr__(self, "negative_rules", _text_tuple(self.negative_rules))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "StyleHarmonizationPlan":
        return cls(
            route_id=source.get("route_id") or "route",
            mode=source.get("mode") or StyleHarmonizationMode.HYBRID_LAYERED,
            ip_style_policy=source.get("ip_style_policy") or "make the IP feel native to the selected visual route",
            scene_style_policy=source.get("scene_style_policy") or "preserve the selected route style family",
            boundary_rule=source.get("boundary_rule") or "IP must not overwrite article subjects",
            positive_rules=source.get("positive_rules") or (),
            negative_rules=source.get("negative_rules") or (),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "route_id": self.route_id,
            "mode": self.mode.value,
            "ip_style_policy": self.ip_style_policy,
            "scene_style_policy": self.scene_style_policy,
            "boundary_rule": self.boundary_rule,
            "positive_rules": list(self.positive_rules),
            "negative_rules": list(self.negative_rules),
        }


@dataclass(frozen=True)
class FrameVisualPlan:
    frame_id: str
    frame_index: int
    source_text: str
    local_claim: str
    visual_task: str
    visual_logic: str
    required_subjects: Sequence[Any] = ()
    forbidden_losses: Sequence[Any] = ()
    evidence_refs: Sequence[Any] = ()
    visible_text_policy: str = "no_visible_text"
    cognitive_anchor: str = ""
    physical_metaphor: str = ""
    scene_arena: str = ""
    ip_action_affordance: str = ""
    forbidden_ip_forms: Sequence[Any] = ()
    content_bound_ip_ready: bool = False
    serious_content_strategy: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_text(self.frame_id, "frame_id"))
        object.__setattr__(self, "frame_index", max(0, int(self.frame_index)))
        object.__setattr__(self, "source_text", _require_text(self.source_text, "source_text"))
        object.__setattr__(self, "local_claim", _optional_text(self.local_claim) or self.source_text)
        object.__setattr__(self, "visual_task", _require_text(self.visual_task, "visual_task"))
        object.__setattr__(self, "visual_logic", _require_text(self.visual_logic, "visual_logic"))
        object.__setattr__(self, "required_subjects", _text_tuple(self.required_subjects))
        object.__setattr__(self, "forbidden_losses", _text_tuple(self.forbidden_losses))
        object.__setattr__(self, "evidence_refs", _text_tuple(self.evidence_refs))
        object.__setattr__(self, "visible_text_policy", _optional_text(self.visible_text_policy) or "no_visible_text")
        object.__setattr__(self, "cognitive_anchor", _optional_text(self.cognitive_anchor))
        object.__setattr__(self, "physical_metaphor", _optional_text(self.physical_metaphor))
        object.__setattr__(self, "scene_arena", _optional_text(self.scene_arena))
        object.__setattr__(self, "ip_action_affordance", _optional_text(self.ip_action_affordance))
        object.__setattr__(self, "forbidden_ip_forms", _text_tuple(self.forbidden_ip_forms))
        object.__setattr__(self, "content_bound_ip_ready", _optional_bool(self.content_bound_ip_ready, default=False))
        object.__setattr__(self, "serious_content_strategy", _optional_text(self.serious_content_strategy))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "FrameVisualPlan":
        return cls(
            frame_id=source.get("frame_id") or "frame",
            frame_index=source.get("frame_index") or source.get("index") or 0,
            source_text=source.get("source_text") or source.get("frame_source_text") or "frame text",
            local_claim=source.get("local_claim") or source.get("frame_claim") or "",
            visual_task=source.get("visual_task") or source.get("frame_visual_task") or "visualize this frame",
            visual_logic=source.get("visual_logic") or source.get("local_visual_logic") or "follow selected route",
            required_subjects=source.get("required_subjects") or (),
            forbidden_losses=source.get("forbidden_losses") or (),
            evidence_refs=source.get("evidence_refs") or (),
            visible_text_policy=source.get("visible_text_policy") or "no_visible_text",
            cognitive_anchor=source.get("cognitive_anchor") or "",
            physical_metaphor=source.get("physical_metaphor") or "",
            scene_arena=source.get("scene_arena") or "",
            ip_action_affordance=source.get("ip_action_affordance") or source.get("ip_affordance") or "",
            forbidden_ip_forms=source.get("forbidden_ip_forms") or (),
            content_bound_ip_ready=source.get("content_bound_ip_ready") or False,
            serious_content_strategy=source.get("serious_content_strategy") or "",
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "frame_id": self.frame_id,
            "frame_index": self.frame_index,
            "source_text": self.source_text,
            "local_claim": self.local_claim,
            "visual_task": self.visual_task,
            "visual_logic": self.visual_logic,
            "required_subjects": list(self.required_subjects),
            "forbidden_losses": list(self.forbidden_losses),
            "evidence_refs": list(self.evidence_refs),
            "visible_text_policy": self.visible_text_policy,
            "cognitive_anchor": self.cognitive_anchor,
            "physical_metaphor": self.physical_metaphor,
            "scene_arena": self.scene_arena,
            "ip_action_affordance": self.ip_action_affordance,
            "forbidden_ip_forms": list(self.forbidden_ip_forms),
            "content_bound_ip_ready": self.content_bound_ip_ready,
            "serious_content_strategy": self.serious_content_strategy,
        }


@dataclass(frozen=True)
class FrameIPFusionPlan:
    frame_id: str
    ip_role: VisualSignatureRole | str
    ip_visibility: IPVisibilityLevel | str
    placement_logic: str
    action_or_function: str
    relation_to_article_subject: str
    style_harmonization: StyleHarmonizationMode | str
    positive_prompt_clause: str = ""
    negative_constraints: Sequence[Any] = ()
    ip_duty_preset: IPDutyPreset | str = IPDutyPreset.AUTO
    duty_goal: str = ""
    action_verb: str = ""
    interaction_target: str = ""
    scene_binding: str = ""
    presentation_form: IPPresentationForm | str = IPPresentationForm.AUTO
    fallback_presentation: IPPresentationForm | str = IPPresentationForm.EMBEDDED_MARK
    semantic_removal_test: str = ""
    channel_identity_removal_test: str = ""
    ip_participation_mechanism: IPParticipationMechanism | str = IPParticipationMechanism.EXPLANATION_DIRECTOR
    cognitive_anchor: str = ""
    physical_metaphor: str = ""
    content_relation_type: str = "content_bound"
    decorative_risk_score: float = 0.0
    rewrite_required: bool = False
    rewrite_instruction: str = ""
    content_bound_ip_presence_plan: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_text(self.frame_id, "frame_id"))
        object.__setattr__(self, "ip_role", _enum_value(self.ip_role, VisualSignatureRole, VisualSignatureRole.SILENT_WITNESS))
        object.__setattr__(self, "ip_visibility", _enum_value(self.ip_visibility, IPVisibilityLevel, IPVisibilityLevel.LOW))
        object.__setattr__(self, "placement_logic", _require_text(self.placement_logic, "placement_logic"))
        object.__setattr__(self, "action_or_function", _require_text(self.action_or_function, "action_or_function"))
        object.__setattr__(self, "relation_to_article_subject", _require_text(self.relation_to_article_subject, "relation_to_article_subject"))
        object.__setattr__(self, "style_harmonization", _enum_value(self.style_harmonization, StyleHarmonizationMode, StyleHarmonizationMode.HYBRID_LAYERED))
        object.__setattr__(self, "positive_prompt_clause", _optional_text(self.positive_prompt_clause))
        object.__setattr__(self, "negative_constraints", _text_tuple(self.negative_constraints))
        duty = IPDutyPlan(
            frame_id=self.frame_id,
            duty_preset=(
                self.ip_duty_preset
                if IPDutyPreset.from_value(self.ip_duty_preset, default=IPDutyPreset.AUTO) is not IPDutyPreset.AUTO
                else duty_from_legacy_role(self.ip_role)
            ),
            duty_goal=self.duty_goal or self.action_or_function,
            action_verb=self.action_verb,
            interaction_target=self.interaction_target,
            scene_binding=self.scene_binding or self.placement_logic,
            presentation_form=self.presentation_form,
            fallback_presentation=self.fallback_presentation,
            semantic_removal_test=self.semantic_removal_test,
            channel_identity_removal_test=self.channel_identity_removal_test,
            source="frame_ip_fusion_plan",
        )
        object.__setattr__(self, "ip_duty_preset", duty.duty_preset)
        object.__setattr__(self, "duty_goal", duty.duty_goal)
        object.__setattr__(self, "action_verb", duty.action_verb)
        object.__setattr__(self, "interaction_target", duty.interaction_target)
        object.__setattr__(self, "scene_binding", duty.scene_binding)
        object.__setattr__(self, "presentation_form", duty.presentation_form)
        object.__setattr__(self, "fallback_presentation", duty.fallback_presentation)
        object.__setattr__(self, "semantic_removal_test", duty.semantic_removal_test)
        object.__setattr__(self, "channel_identity_removal_test", duty.channel_identity_removal_test)
        object.__setattr__(self, "ip_participation_mechanism", IPParticipationMechanism.from_value(self.ip_participation_mechanism))
        object.__setattr__(self, "cognitive_anchor", _optional_text(self.cognitive_anchor))
        object.__setattr__(self, "physical_metaphor", _optional_text(self.physical_metaphor))
        object.__setattr__(self, "content_relation_type", _optional_text(self.content_relation_type) or "content_bound")
        object.__setattr__(self, "decorative_risk_score", _score(self.decorative_risk_score, "decorative_risk_score"))
        object.__setattr__(self, "rewrite_required", _optional_bool(self.rewrite_required, default=False))
        object.__setattr__(self, "rewrite_instruction", _optional_text(self.rewrite_instruction))
        object.__setattr__(self, "content_bound_ip_presence_plan", dict(self.content_bound_ip_presence_plan or {}))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "FrameIPFusionPlan":
        duty_preset = source.get("ip_duty_preset") or source.get("duty_preset") or source.get("duty")
        if not duty_preset:
            duty_preset = duty_from_route_type(source.get("route_type"), legacy_role=source.get("ip_role") or source.get("role"))
        return cls(
            frame_id=source.get("frame_id") or "frame",
            ip_role=source.get("ip_role") or source.get("role") or VisualSignatureRole.SILENT_WITNESS,
            ip_visibility=source.get("ip_visibility") or source.get("visibility_tier") or IPVisibilityLevel.LOW,
            placement_logic=source.get("placement_logic") or source.get("scene_binding") or "place the IP as a scene-bound participant",
            action_or_function=source.get("action_or_function") or source.get("function") or source.get("duty_goal") or "support article comprehension",
            relation_to_article_subject=source.get("relation_to_article_subject") or "does not replace article subjects",
            style_harmonization=source.get("style_harmonization") or StyleHarmonizationMode.HYBRID_LAYERED,
            positive_prompt_clause=source.get("positive_prompt_clause") or source.get("image_prompt_clause") or "",
            negative_constraints=source.get("negative_constraints") or source.get("negative_rules") or (),
            ip_duty_preset=duty_preset,
            duty_goal=source.get("duty_goal") or source.get("scene_function") or "",
            action_verb=source.get("action_verb") or "",
            interaction_target=source.get("interaction_target") or "",
            scene_binding=source.get("scene_binding") or "",
            presentation_form=source.get("presentation_form") or source.get("manifestation_form") or IPPresentationForm.AUTO,
            fallback_presentation=source.get("fallback_presentation") or IPPresentationForm.EMBEDDED_MARK,
            semantic_removal_test=source.get("semantic_removal_test") or source.get("removal_test") or "",
            channel_identity_removal_test=source.get("channel_identity_removal_test") or "",
            ip_participation_mechanism=source.get("ip_participation_mechanism") or source.get("participation_mechanism") or IPParticipationMechanism.EXPLANATION_DIRECTOR,
            cognitive_anchor=source.get("cognitive_anchor") or "",
            physical_metaphor=source.get("physical_metaphor") or "",
            content_relation_type=source.get("content_relation_type") or "content_bound",
            decorative_risk_score=source.get("decorative_risk_score") or 0.0,
            rewrite_required=source.get("rewrite_required") or False,
            rewrite_instruction=source.get("rewrite_instruction") or "",
            content_bound_ip_presence_plan=source.get("content_bound_ip_presence_plan") or {},
        )

    @classmethod
    def deterministic(
        cls,
        *,
        frame_id: str,
        route_type: Any = None,
        ip_role: Any = VisualSignatureRole.SILENT_WITNESS,
        ip_visibility: Any = IPVisibilityLevel.LOW,
        local_claim: str = "",
        visual_task: str = "",
        relation_to_article_subject: str = "IP supports comprehension and does not replace article subjects.",
        style_harmonization: Any = StyleHarmonizationMode.HYBRID_LAYERED,
        risk_text: str = "",
    ) -> "FrameIPFusionPlan":
        duty = build_default_ip_duty_plan(
            frame_id=frame_id,
            route_type=route_type,
            legacy_role=ip_role,
            local_claim=local_claim,
            visual_task=visual_task,
            risk_text=risk_text,
        )
        return cls(
            frame_id=frame_id,
            ip_role=ip_role,
            ip_visibility=ip_visibility,
            placement_logic=duty.scene_binding,
            action_or_function=duty.duty_goal,
            relation_to_article_subject=relation_to_article_subject,
            style_harmonization=style_harmonization,
            positive_prompt_clause="",
            negative_constraints=("preserve article subjects", "keep channel IP subordinate to frame meaning"),
            ip_duty_preset=duty.duty_preset,
            duty_goal=duty.duty_goal,
            action_verb=duty.action_verb,
            interaction_target=duty.interaction_target,
            scene_binding=duty.scene_binding,
            presentation_form=duty.presentation_form,
            fallback_presentation=duty.fallback_presentation,
            semantic_removal_test=duty.semantic_removal_test,
            channel_identity_removal_test=duty.channel_identity_removal_test,
            ip_participation_mechanism=IPParticipationMechanism.from_value(duty.duty_preset.value),
            cognitive_anchor="",
            physical_metaphor="",
            content_relation_type="content_bound",
            decorative_risk_score=0.0,
            rewrite_required=False,
            rewrite_instruction="",
            content_bound_ip_presence_plan={},
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "frame_id": self.frame_id,
            "ip_role": self.ip_role.value,
            "ip_visibility": self.ip_visibility.value,
            "placement_logic": self.placement_logic,
            "action_or_function": self.action_or_function,
            "relation_to_article_subject": self.relation_to_article_subject,
            "style_harmonization": self.style_harmonization.value,
            "positive_prompt_clause": self.positive_prompt_clause,
            "negative_constraints": list(self.negative_constraints),
            "ip_duty_preset": self.ip_duty_preset.value,
            "duty_goal": self.duty_goal,
            "action_verb": self.action_verb,
            "interaction_target": self.interaction_target,
            "scene_binding": self.scene_binding,
            "presentation_form": self.presentation_form.value,
            "fallback_presentation": self.fallback_presentation.value,
            "semantic_removal_test": self.semantic_removal_test,
            "channel_identity_removal_test": self.channel_identity_removal_test,
            "ip_participation_mechanism": self.ip_participation_mechanism.value,
            "cognitive_anchor": self.cognitive_anchor,
            "physical_metaphor": self.physical_metaphor,
            "content_relation_type": self.content_relation_type,
            "decorative_risk_score": self.decorative_risk_score,
            "rewrite_required": self.rewrite_required,
            "rewrite_instruction": self.rewrite_instruction,
            "content_bound_ip_presence_plan": dict(self.content_bound_ip_presence_plan or {}),
        }


@dataclass(frozen=True)
class VisualStoryEnginePlan:
    plan_id: str
    article: ArticleVisualUnderstanding
    candidate_routes: Sequence[VisualRouteCandidate | Mapping[str, Any]]
    compatibility_reports: Sequence[IPRouteCompatibilityReport | Mapping[str, Any]]
    selection: RouteSelectionDecision
    style_harmonization: StyleHarmonizationPlan
    frame_visual_plans: Sequence[FrameVisualPlan | Mapping[str, Any]] = ()
    frame_ip_fusion_plans: Sequence[FrameIPFusionPlan | Mapping[str, Any]] = ()
    channel_memory_intent: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _require_text(self.plan_id, "plan_id"))
        if not isinstance(self.article, ArticleVisualUnderstanding):
            object.__setattr__(self, "article", ArticleVisualUnderstanding.from_mapping(self.article))
        object.__setattr__(self, "candidate_routes", tuple(_candidate(value) for value in self.candidate_routes))
        object.__setattr__(self, "compatibility_reports", tuple(_compat(value) for value in self.compatibility_reports))
        if not isinstance(self.selection, RouteSelectionDecision):
            raise TypeError("selection must be RouteSelectionDecision")
        if not isinstance(self.style_harmonization, StyleHarmonizationPlan):
            object.__setattr__(self, "style_harmonization", StyleHarmonizationPlan.from_mapping(self.style_harmonization))
        object.__setattr__(self, "frame_visual_plans", tuple(_frame_plan(value) for value in self.frame_visual_plans))
        object.__setattr__(self, "frame_ip_fusion_plans", tuple(_fusion_plan(value) for value in self.frame_ip_fusion_plans))
        object.__setattr__(self, "channel_memory_intent", _optional_text(self.channel_memory_intent))

    @property
    def selected_route(self) -> VisualRouteCandidate:
        by_id = {route.route_id: route for route in self.candidate_routes}
        return by_id.get(self.selection.selected_route_id) or max(self.candidate_routes, key=lambda route: route.final_score)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "plan_id": self.plan_id,
            "article": self.article.to_dict(),
            "candidate_routes": [route.to_dict() for route in self.candidate_routes],
            "compatibility_reports": [report.to_dict() for report in self.compatibility_reports],
            "selection": self.selection.to_dict(),
            "selected_visual_route": self.selected_route.to_dict(),
            "style_harmonization": self.style_harmonization.to_dict(),
            "frame_visual_plans": [plan.to_dict() for plan in self.frame_visual_plans],
            "frame_ip_fusion_plans": [plan.to_dict() for plan in self.frame_ip_fusion_plans],
            "channel_memory_intent": self.channel_memory_intent,
        }


# ---- helpers ----

def _evidence(value: EvidenceSpan | Mapping[str, Any]) -> EvidenceSpan:
    return value if isinstance(value, EvidenceSpan) else EvidenceSpan.from_mapping(value)


def _candidate(value: VisualRouteCandidate | Mapping[str, Any]) -> VisualRouteCandidate:
    return value if isinstance(value, VisualRouteCandidate) else VisualRouteCandidate.from_mapping(value)


def _compat(value: IPRouteCompatibilityReport | Mapping[str, Any]) -> IPRouteCompatibilityReport:
    return value if isinstance(value, IPRouteCompatibilityReport) else IPRouteCompatibilityReport.from_mapping(value)


def _frame_plan(value: FrameVisualPlan | Mapping[str, Any]) -> FrameVisualPlan:
    return value if isinstance(value, FrameVisualPlan) else FrameVisualPlan.from_mapping(value)


def _fusion_plan(value: FrameIPFusionPlan | Mapping[str, Any]) -> FrameIPFusionPlan:
    return value if isinstance(value, FrameIPFusionPlan) else FrameIPFusionPlan.from_mapping(value)


def _enum_value(value: Any, enum_cls: type[Enum], default: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = str(value.value if isinstance(value, Enum) else value or "").strip()
    if text:
        for item in enum_cls:
            if text.lower() == item.value.lower() or text.lower() == item.name.lower():
                return item
    return default


def _require_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value.value if isinstance(value, Enum) else value).strip()


def _optional_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled"}:
            return True
        if text in {"0", "false", "no", "off", "disabled"}:
            return False
    return bool(value)


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    number = int(value)
    if number < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return number


def _text_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    elif not isinstance(values, Sequence):
        values = (values,)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _optional_text(value)
        key = text.casefold()
        if not text or key in seen:
            continue
        result.append(text)
        seen.add(key)
    return tuple(result)


def _score(value: Any, field_name: str) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return _clamp(number)


def _clamp(number: float) -> float:
    return max(0.0, min(1.0, round(float(number), 4)))


def _slug_or_fallback(value: Any, fallback: str) -> str:
    text = _optional_text(value)
    if not text:
        text = _optional_text(fallback)
    slug = re.sub(r"[^A-Za-z0-9_\-]+", "_", text.strip().lower()).strip("_")
    return slug[:80] or "visual_route"


__all__ = [
    "ArticleInputKind",
    "VisualRouteType",
    "VisualStyleFamily",
    "VisualSignatureRole",
    "IPVisibilityLevel",
    "IPDutyPreset",
    "IPPresentationForm",
    "StyleHarmonizationMode",
    "RouteSelectionSource",
    "EvidenceSpan",
    "ArticleVisualUnderstanding",
    "VisualRouteScores",
    "VisualRouteCandidate",
    "IPRouteCompatibilityReport",
    "RouteSelectionDecision",
    "StyleHarmonizationPlan",
    "FrameVisualPlan",
    "FrameIPFusionPlan",
    "VisualStoryEnginePlan",
]
