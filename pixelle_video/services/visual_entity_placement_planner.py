from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRole,
)
from pixelle_video.models.visual_entity_placement import (
    NOT_APPLICABLE,
    VisualDepthPosition,
    VisualEntityPlacement,
    VisualEntitySceneFusion,
    VisualHorizontalPosition,
    VisualRelativeSize,
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
_FORBIDDEN_COMPOSITIONS = (
    "sticker, corner badge, emblem, logo, or watermark treatment",
    "centered or oversized character that hides a required subject",
    "unrelated display platform, sign, box, carrier, or stage",
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
    ) -> tuple[VisualEntityPlacement, VisualEntitySceneFusion]:
        if not signature.enabled or signature.profile is None:
            raise ValueError(
                f"frame {frame_id}: placement.signature requires an enabled profile"
            )
        scene_type = _scene_type(
            frame_context=frame_context,
            article_concretization=article_concretization,
        )
        relation_target = _relation_target(
            scene_type=scene_type,
            frame_context=frame_context,
            base_visual_brief=base_visual_brief,
            required_subjects=required_subjects,
        )
        horizontal_position = _horizontal_position(frame_id)
        support_relation = _support_relation(
            scene_type=scene_type,
            base_prompt=base_prompt,
            frame_context=frame_context,
        )
        action, spatial_relation, orientation = _role_behavior(
            role=signature.role,
            base_prompt=base_prompt,
            relation_target=relation_target,
        )
        placement = VisualEntityPlacement(
            frame_id=frame_id,
            scene_type=scene_type,
            instance_count=1,
            horizontal_position=horizontal_position,
            depth_position=VisualDepthPosition.MIDGROUND,
            relative_size=signature.relative_size,
            relation_target=relation_target,
            spatial_relation=spatial_relation,
            support_relation=support_relation,
            action=action,
            orientation=orientation,
            visible_extent=_visible_extent(signature.relative_size),
            visible_core_traits=signature.profile.core_identity_traits[:2],
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


def _relation_target(
    *,
    scene_type: VisualSceneType,
    frame_context: Mapping[str, Any],
    base_visual_brief: Mapping[str, Any] | None,
    required_subjects: Sequence[str],
) -> str:
    for value in required_subjects:
        text = _text(value)
        if text:
            return text
    brief = dict(base_visual_brief or {})
    for value in _sequence(brief.get("main_subjects")):
        text = _text(value)
        if text:
            return text
    primary_subject = _text(frame_context.get("primary_subject"))
    if primary_subject:
        return primary_subject
    if scene_type is VisualSceneType.ABSTRACT_DIAGRAM:
        return "diagram node"
    for value in _sequence(frame_context.get("world_elements")):
        text = _text(value)
        if text:
            return text
    return "scene subject"


def _horizontal_position(frame_id: str) -> VisualHorizontalPosition:
    digest = hashlib.sha256(str(frame_id).encode("utf-8")).digest()
    return (
        VisualHorizontalPosition.LEFT
        if digest[0] % 2 == 0
        else VisualHorizontalPosition.RIGHT
    )


def _support_relation(
    *,
    scene_type: VisualSceneType,
    base_prompt: str,
    frame_context: Mapping[str, Any],
) -> str:
    if scene_type is VisualSceneType.ABSTRACT_DIAGRAM:
        return "at node or path"
    candidates = [*_sequence(frame_context.get("world_elements")), base_prompt]
    for term in _SUPPORT_TERMS:
        for candidate in candidates:
            text = _text(candidate)
            lowered = text.casefold()
            if text and term.casefold() in lowered:
                return f"feet on existing {term}"
    return "feet on scene ground"


def _role_behavior(
    *,
    role: SeriesVisualSignatureRole,
    base_prompt: str,
    relation_target: str,
) -> tuple[str, str, str]:
    prompt = base_prompt.casefold()
    if any(
        marker in prompt
        for marker in (
            " walking ",
            " walks ",
            " strolling ",
            " strolls ",
            "同行",
            "行走",
            "散步",
        )
    ):
        return (
            f"walks with {relation_target}",
            "alongside",
            "faces movement direction",
        )
    if role is SeriesVisualSignatureRole.CORE_ACTOR:
        return "performs frame action", "beside", "faces target/camera"
    if role is SeriesVisualSignatureRole.OPERATOR:
        return "operates mechanism", "beside", "faces target/camera"
    if role is SeriesVisualSignatureRole.GUIDE:
        return (
            f"looks toward {relation_target}",
            "beside",
            "faces target/camera",
        )
    return "quietly observes", "beside", "faces target/camera"


def _visible_extent(relative_size: VisualRelativeSize) -> VisualVisibleExtent:
    if relative_size is VisualRelativeSize.LARGE:
        return VisualVisibleExtent.HALF_BODY
    return VisualVisibleExtent.FULL_BODY


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
            occlusion_relation="core-safe node/path occlusion",
            perspective_relation=NOT_APPLICABLE,
            contact_relation=NOT_APPLICABLE,
            lighting_relation=NOT_APPLICABLE,
            shadow_relation=NOT_APPLICABLE,
            style_relation="same diagram linework/material",
            protected_subjects=required_subjects,
            forbidden_compositions=_FORBIDDEN_COMPOSITIONS,
        )

    return VisualEntitySceneFusion(
        frame_id=frame_id,
        scene_type=scene_type,
        occlusion_relation="core-safe occlusion",
        perspective_relation="shared perspective",
        contact_relation=placement.support_relation,
        lighting_relation=_lighting_relation(base_prompt, frame_context),
        shadow_relation="matching contact shadow",
        style_relation="same style/material",
        protected_subjects=required_subjects,
        forbidden_compositions=_FORBIDDEN_COMPOSITIONS,
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
    explicit = ", ".join(facts) if facts else "scene light"
    return f"{explicit} direction/color/intensity"


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
