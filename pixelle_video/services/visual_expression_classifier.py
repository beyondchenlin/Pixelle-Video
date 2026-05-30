from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_expression import (
    VisualExpressionDecision,
    VisualExpressionMode,
    normalize_visual_expression_mode,
)


@dataclass(frozen=True)
class VisualExpressionClassifier:
    def classify_batch(
        self,
        *,
        frame_contexts: Sequence[Mapping[str, Any]],
        base_visual_briefs: Sequence[BaseVisualBrief],
        visual_expression_mode: VisualExpressionMode | str | None = None,
    ) -> tuple[VisualExpressionDecision, ...]:
        requested_mode = normalize_visual_expression_mode(visual_expression_mode)
        decisions: list[VisualExpressionDecision] = []
        for index, brief in enumerate(base_visual_briefs):
            frame_context = frame_contexts[index] if index < len(frame_contexts) else {}
            decisions.append(
                self.classify_frame(
                    frame_context=frame_context,
                    base_visual_brief=brief,
                    visual_expression_mode=requested_mode,
                )
            )
        return tuple(decisions)

    def classify_frame(
        self,
        *,
        frame_context: Mapping[str, Any] | None,
        base_visual_brief: BaseVisualBrief,
        visual_expression_mode: VisualExpressionMode | str | None = None,
    ) -> VisualExpressionDecision:
        requested_mode = normalize_visual_expression_mode(visual_expression_mode)
        if requested_mode is not VisualExpressionMode.AUTO:
            return VisualExpressionDecision(
                frame_id=base_visual_brief.frame_id,
                expression_mode=requested_mode,
                reason="user selected visual_expression_mode",
                source="user",
            )

        text = _combined_text(frame_context, base_visual_brief).lower()
        mode, reason = _classify_text(text)
        return VisualExpressionDecision(
            frame_id=base_visual_brief.frame_id,
            expression_mode=mode,
            reason=reason,
            source="rule",
        )


def _combined_text(frame_context: Mapping[str, Any] | None, brief: BaseVisualBrief) -> str:
    values: list[str] = [
        brief.core_message,
        brief.visual_moment,
        brief.subject_relationship,
        brief.setting,
        brief.base_image_prompt,
        " ".join(brief.main_subjects),
        " ".join(brief.key_props_symbols),
    ]
    if frame_context:
        for key in (
            "visual_goal",
            "prompt_intent",
            "source_text",
            "frame_source_text",
            "shot_purpose",
            "primary_subject",
            "focus_detail",
        ):
            values.append(str(frame_context.get(key) or ""))
    return " ".join(value for value in values if value)


def _classify_text(text: str) -> tuple[VisualExpressionMode, str]:
    if any(token in text for token in ("流程", "原理", "机制", "步骤", "diagram", "process", "how it works", "explain")):
        return VisualExpressionMode.EXPLANATORY_DIAGRAM, "matched explanation / process tokens"
    if any(token in text for token in ("列表", "时间线", "结构图", "层级", "数据", "infographic", "timeline", "chart")):
        return VisualExpressionMode.INFOGRAPHIC_LAYOUT, "matched infographic / structure tokens"
    if any(token in text for token in ("隐喻", "象征", "心理", "方法论", "认知", "metaphor", "mindset")):
        return VisualExpressionMode.COGNITIVE_METAPHOR, "matched cognitive metaphor tokens"
    if any(token in text for token in ("对比", "辩论", "比较", "vs", "versus", "debate", "compare")):
        return VisualExpressionMode.COMPARISON_OR_DEBATE_SCENE, "matched comparison / debate tokens"
    if any(token in text for token in ("商品", "产品", "设备", "包装", "product", "object", "device")):
        return VisualExpressionMode.PRODUCT_OR_OBJECT_SCENE, "matched product / object tokens"
    if any(token in text for token in ("主持", "人物", "portrait", "host", "speaker", "talking head")):
        return VisualExpressionMode.PORTRAIT_OR_HOST_SCENE, "matched portrait / host tokens"
    if any(token in text for token in ("品牌", "空间", "展厅", "环境", "branding", "environment")):
        return VisualExpressionMode.ENVIRONMENT_BRANDING, "matched environment branding tokens"
    return VisualExpressionMode.NARRATIVE_SCENE, "default narrative scene"


__all__ = ["VisualExpressionClassifier"]
