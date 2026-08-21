from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRole,
)
from pixelle_video.models.visual_entity_placement import (
    DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
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
            frame_context=frame_context,
            base_visual_brief=base_visual_brief,
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
            return _compact_fact_label(text)
    brief = dict(base_visual_brief or {})
    for value in _sequence(brief.get("main_subjects")):
        text = _text(value)
        if text:
            return _compact_fact_label(text)
    primary_subject = _text(frame_context.get("primary_subject"))
    if primary_subject:
        return _compact_fact_label(primary_subject)
    if scene_type is VisualSceneType.ABSTRACT_DIAGRAM:
        return "diagram node"
    for value in _sequence(frame_context.get("world_elements")):
        text = _text(value)
        if text:
            return _compact_fact_label(text)
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
            if text and _contains_scene_term(lowered, term):
                return f"feet on existing {term}"
    return "feet on existing ground"


def _role_behavior(
    *,
    role: SeriesVisualSignatureRole,
    base_prompt: str,
    frame_context: Mapping[str, Any],
    base_visual_brief: Mapping[str, Any] | None,
) -> tuple[str, str, str]:
    prompt = base_prompt.casefold()
    if any(
        _contains_scene_term(prompt, marker)
        for marker in (
            "walking",
            "walks",
            "strolling",
            "strolls",
            "同行",
            "行走",
            "散步",
        )
    ):
        return (
            "walks with it",
            "alongside",
            "faces movement direction",
        )
    action_fact = _frame_action_fact(
        frame_context=frame_context,
        base_visual_brief=base_visual_brief,
        base_prompt=base_prompt,
    )
    if role is SeriesVisualSignatureRole.CORE_ACTOR:
        return (
            f"acts within {action_fact}",
            "beside",
            "3/4 toward it",
        )
    if role is SeriesVisualSignatureRole.OPERATOR:
        return (
            f"demonstrates {action_fact}",
            "beside",
            "3/4 toward it",
        )
    if role is SeriesVisualSignatureRole.GUIDE:
        return (
            "points toward it",
            "beside",
            "3/4 toward it",
        )
    return (
        "observes it",
        "beside",
        "3/4 toward it",
    )


def _frame_action_fact(
    *,
    frame_context: Mapping[str, Any],
    base_visual_brief: Mapping[str, Any] | None,
    base_prompt: str,
) -> str:
    brief = dict(base_visual_brief or {})
    for value in (
        frame_context.get("prompt_intent"),
        frame_context.get("visual_goal"),
        frame_context.get("shot_purpose"),
        brief.get("core_message"),
        frame_context.get("frame_source_text"),
        base_prompt,
    ):
        text = _text(value).strip(" .,:;，。；：")
        if text:
            return _compact_fact_label(text, limit=72)
    return "the visible scene action"


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


def _compact_fact_label(text: str, limit: int = 32) -> str:
    """Create a compact derived label without implying it is the full source fact."""

    if len(text) <= limit:
        return text
    prefix = text[:limit].rstrip(" .,:;，。；：")
    if " " in prefix:
        word_bounded = prefix.rsplit(" ", 1)[0].rstrip(" .,:;，。；：")
        if len(word_bounded) >= limit // 2:
            return word_bounded
    return prefix


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
