from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.content_bound_ip import ContentBoundIPPresencePlan
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
)
from pixelle_video.models.visual_entity_placement import (
    DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
    NOT_APPLICABLE,
    VisualDepthPosition,
    VisualEntityPlacement,
    VisualEntitySceneFusion,
    VisualHorizontalPosition,
    VisualSceneType,
    VisualVisibleExtent,
)

_ABSTRACT_GRAMMARS = frozenset(
    {
        "process_flow",
        "relationship_map",
        "structure_map",
        "decision_tree",
        "state_machine",
        "evidence_map",
        "contrast_board",
    }
)
_SUPPORT_TERMS = (
    "ground",
    "road",
    "floor",
    "path",
    "pavement",
    "地面",
    "道路",
    "地板",
    "小路",
    "路径",
    "table",
    "desk",
    "seat",
    "chair",
    "bench",
    "platform",
    "桌",
    "座椅",
    "长椅",
)
class VisualEntityPlacementPlanner:
    """Derive deterministic placement and fusion facts from existing frame facts."""

    def plan(
        self,
        *,
        frame_id: str,
        base_prompt: str,
        frame_context: Mapping[str, Any],
        base_visual_brief: Mapping[str, Any] | None,
        article_concretization: Mapping[str, Any] | None,
        required_subjects: Sequence[str],
        signature: SeriesVisualSignatureContract,
        participation_plan: ContentBoundIPPresencePlan,
    ) -> tuple[VisualEntityPlacement, VisualEntitySceneFusion]:
        if not signature.enabled or signature.profile is None:
            raise ValueError(
                f"frame {frame_id}: placement.signature requires an enabled profile"
            )
        scene_type = _scene_type(
            frame_context=frame_context,
            article_concretization=article_concretization,
        )
        if participation_plan.frame_id != frame_id:
            raise ValueError(
                f"frame {frame_id}: participation plan frame id must match placement"
            )
        horizontal_position = VisualHorizontalPosition(
            participation_plan.recommended_horizontal_position
        )
        depth_position = VisualDepthPosition(
            participation_plan.recommended_depth_position
        )
        support_relation = _support_relation(
            scene_type=scene_type,
            base_prompt=base_prompt,
            frame_context=frame_context,
            participation_text=participation_plan.scene_binding,
        )
        placement = VisualEntityPlacement(
            frame_id=frame_id,
            scene_type=scene_type,
            instance_count=1,
            horizontal_position=horizontal_position,
            depth_position=depth_position,
            relative_size=signature.relative_size,
            relation_target=participation_plan.interaction_target,
            spatial_relation=participation_plan.scene_binding,
            support_relation=support_relation,
            action=participation_plan.semantic_action,
            orientation=(
                f"body and gaze directed toward {participation_plan.interaction_target}"
            ),
            visible_extent=VisualVisibleExtent(
                participation_plan.recommended_visible_extent
            ),
            visible_core_traits=signature.profile.core_identity_traits[:2],
            area_ratio=participation_plan.recommended_area_ratio,
        )
        fusion = _scene_fusion(
            frame_id=frame_id,
            scene_type=scene_type,
            placement=placement,
            base_prompt=base_prompt,
            frame_context=frame_context,
            required_subjects=required_subjects,
        )
        return placement, fusion


def _scene_type(
    *,
    frame_context: Mapping[str, Any],
    article_concretization: Mapping[str, Any] | None,
) -> VisualSceneType:
    article = dict(article_concretization or {})
    diagram = article.get("diagram")
    diagram = dict(diagram) if isinstance(diagram, Mapping) else {}
    grammars = {
        _text(value).lower()
        for value in (
            diagram.get("grammar"),
            frame_context.get("effective_diagram_grammar"),
            frame_context.get("explanation_diagram_grammar"),
            frame_context.get("diagram_grammar"),
        )
        if _text(value)
    }
    if grammars & _ABSTRACT_GRAMMARS:
        return VisualSceneType.ABSTRACT_DIAGRAM
    return VisualSceneType.PHYSICAL_SCENE


def _support_relation(
    *,
    scene_type: VisualSceneType,
    base_prompt: str,
    frame_context: Mapping[str, Any],
    participation_text: str = "",
) -> str:
    if scene_type is VisualSceneType.ABSTRACT_DIAGRAM:
        return "at node or path"
    candidates = [
        participation_text,
        *_sequence(frame_context.get("world_elements")),
        base_prompt,
    ]
    for term in _SUPPORT_TERMS:
        for candidate in candidates:
            text = _text(candidate)
            lowered = text.casefold()
            if text and _contains_scene_term(lowered, term):
                return f"feet on existing {term}"
    return "feet on existing ground"


def _scene_fusion(
    *,
    frame_id: str,
    scene_type: VisualSceneType,
    placement: VisualEntityPlacement,
    base_prompt: str,
    frame_context: Mapping[str, Any],
    required_subjects: Sequence[str],
) -> VisualEntitySceneFusion:
    if scene_type is VisualSceneType.ABSTRACT_DIAGRAM:
        return VisualEntitySceneFusion(
            frame_id=frame_id,
            scene_type=scene_type,
            occlusion_relation="diagram links pass behind body, not core traits",
            perspective_relation=NOT_APPLICABLE,
            contact_relation=NOT_APPLICABLE,
            lighting_relation=NOT_APPLICABLE,
            shadow_relation=NOT_APPLICABLE,
            style_relation="same diagram linework/material/texture",
            protected_subjects=required_subjects,
            forbidden_compositions=DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
        )

    return VisualEntitySceneFusion(
        frame_id=frame_id,
        scene_type=scene_type,
        occlusion_relation="unobscured single identity",
        perspective_relation="scene perspective",
        contact_relation=placement.support_relation,
        lighting_relation=_lighting_relation(base_prompt, frame_context),
        shadow_relation="scene-soft contact shadow",
        style_relation="same line/material/texture/realism",
        protected_subjects=required_subjects,
        forbidden_compositions=DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
    )


def _lighting_relation(base_prompt: str, frame_context: Mapping[str, Any]) -> str:
    source = " ".join(
        part
        for part in (
            _text(frame_context.get("lighting")),
            _text(frame_context.get("light_source")),
            _text(base_prompt),
        )
        if part
    )
    lowered = source.casefold()
    facts = [
        term
        for term in (
            "left light",
            "right light",
            "backlight",
            "warm light",
            "cool light",
            "soft light",
            "hard light",
            "sunlight",
            "window light",
            "左侧光",
            "右侧光",
            "逆光",
            "暖光",
            "冷光",
            "柔光",
            "硬光",
            "阳光",
            "窗光",
        )
        if term in lowered
    ]
    if facts:
        return "matches " + ", ".join(facts[:2])
    return "matches scene light"


def _contains_scene_term(text: str, term: str) -> bool:
    normalized_term = term.casefold().strip()
    if not normalized_term:
        return False
    if normalized_term.isascii():
        pattern = re.compile(
            rf"(?<![a-z0-9_]){re.escape(normalized_term)}(?![a-z0-9_])",
            flags=re.IGNORECASE,
        )
        return pattern.search(text) is not None
    return normalized_term in text.casefold()


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return ()


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


__all__ = ["VisualEntityPlacementPlanner"]
