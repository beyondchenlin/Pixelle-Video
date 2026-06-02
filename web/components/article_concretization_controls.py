from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from enum import Enum
from typing import Any

import streamlit as st

from pixelle_video.models.article_concretization import (
    ArticleConcretizationRequest,
    CognitiveAnchorKind,
    DiagramAspectRatio,
    DiagramRenderStyle,
    ExplanationDiagramGrammar,
    SeriesVisualSignatureRole,
    VisibleTextPolicy,
)
from web.i18n import tr

Translate = Callable[..., str]

_LABEL_SPLIT_PATTERN = re.compile(r"[,，、\r\n]+")

_OPTION_FALLBACK_LABELS = {
    "auto": "自动",
    "none": "无",
    "judgment": "判断",
    "causal_mechanism": "因果机制",
    "process": "流程",
    "structure": "结构",
    "state": "状态",
    "metaphor": "隐喻",
    "contrast": "对比",
    "relationship": "关系",
    "evidence": "证据",
    "decision_path": "决策路径",
    "state_machine": "状态机",
    "single_explanation_image": "单张解释图",
    "multi_panel_comic": "多面板漫画",
    "process_flow": "流程图",
    "structure_map": "结构图",
    "contrast_board": "对比板",
    "relationship_map": "关系图",
    "metaphor_scene": "隐喻场景",
    "decision_tree": "决策树",
    "evidence_map": "证据图",
    "core_actor": "核心行动者",
    "silent_witness": "沉默见证者",
    "operator": "操作员",
    "guide": "向导",
    "obstacle": "障碍",
    "container": "容器",
    "background_mark": "背景标识",
    "xiaohei_handdrawn": "小黑参考手绘风格",
    "editorial_diagram": "编辑图解风格",
    "clean_vector": "干净矢量风格",
    "cinematic_metaphor": "电影化隐喻",
    "brand_kv": "品牌主视觉",
    "three_d_concept": "3D 概念风格",
    "ink_collage": "墨迹拼贴",
    "landscape_16_9": "横向 16:9",
    "square_1_1": "方形 1:1",
    "portrait_4_5": "竖向 4:5",
    "vertical_9_16": "竖屏 9:16",
    "template": "跟随模板",
    "no_visible_text": "不生成可见文字",
    "source_text_only": "仅使用原文文字",
    "symbolic_labels_only": "仅符号化标签",
    "approved_labels_only": "仅批准标签",
    "free_text_allowed": "允许自由文字",
}


def build_article_concretization_payload(
    *,
    enabled: bool,
    cognitive_anchor_kind: str = "auto",
    explanation_diagram_grammar: str = "auto",
    diagram_render_style: str = "auto",
    series_visual_signature_role: str = "none",
    diagram_aspect_ratio: str = "auto",
    diagram_visible_text_policy: str = "no_visible_text",
    diagram_approved_labels: Sequence[str] | str | None = None,
    diagram_user_intent_hint: str | None = None,
) -> dict[str, Any]:
    request = ArticleConcretizationRequest(
        enabled=enabled,
        cognitive_anchor_kind=cognitive_anchor_kind,
        explanation_diagram_grammar=explanation_diagram_grammar,
        diagram_render_style=diagram_render_style,
        series_visual_signature_role=series_visual_signature_role,
        diagram_aspect_ratio=diagram_aspect_ratio,
        diagram_visible_text_policy=diagram_visible_text_policy,
        diagram_approved_labels=_normalize_approved_labels(diagram_approved_labels),
        diagram_user_intent_hint=diagram_user_intent_hint,
    )
    normalized = request.to_dict()
    return {
        "article_concretization_enabled": normalized["enabled"],
        "cognitive_anchor_kind": normalized["cognitive_anchor_kind"],
        "explanation_diagram_grammar": normalized["explanation_diagram_grammar"],
        "series_visual_signature_role": normalized["series_visual_signature_role"],
        "diagram_render_style": normalized["diagram_render_style"],
        "diagram_aspect_ratio": normalized["diagram_aspect_ratio"],
        "diagram_visible_text_policy": normalized["diagram_visible_text_policy"],
        "diagram_approved_labels": normalized["diagram_approved_labels"],
        "diagram_user_intent_hint": normalized["diagram_user_intent_hint"],
    }


def render_article_concretization_controls(
    *,
    ui=st,
    translate: Translate = tr,
    key_prefix: str,
    selected_template_type_for_storyboard: str | None = None,
    static_template_allows_layout_changes: bool = False,
) -> dict[str, Any]:
    """Render article concretization controls and return flat generation params."""
    with ui.expander(
        translate(
            "article_concretization.section_title",
            fallback="文章具象化解读",
        ),
        expanded=False,
    ):
        enabled = ui.checkbox(
            translate(
                "article_concretization.enabled",
                fallback="启用文章具象化解读",
            ),
            value=False,
            key=f"{key_prefix}_article_concretization_enabled",
            help=translate(
                "article_concretization.enabled_help",
                fallback="把文章中的判断、结构或因果关系转成可解释的图解画面。",
            ),
        )

        default_col1, default_col2 = ui.columns(2)
        with default_col1:
            cognitive_anchor_kind = _enum_selectbox(
                ui,
                translate,
                label_key="article_concretization.cognitive_anchor_kind",
                fallback_label="认知锚点",
                enum_cls=CognitiveAnchorKind,
                default=CognitiveAnchorKind.AUTO.value,
                key=f"{key_prefix}_cognitive_anchor_kind",
            )
            diagram_render_style = _enum_selectbox(
                ui,
                translate,
                label_key="article_concretization.diagram_render_style",
                fallback_label="渲染风格",
                enum_cls=DiagramRenderStyle,
                default=DiagramRenderStyle.AUTO.value,
                key=f"{key_prefix}_diagram_render_style",
            )
        with default_col2:
            explanation_diagram_grammar = _enum_selectbox(
                ui,
                translate,
                label_key="article_concretization.explanation_diagram_grammar",
                fallback_label="解释图类型",
                enum_cls=ExplanationDiagramGrammar,
                default=ExplanationDiagramGrammar.AUTO.value,
                key=f"{key_prefix}_explanation_diagram_grammar",
            )

        with ui.expander(
            translate(
                "article_concretization.advanced_title",
                fallback="高级控件",
            ),
            expanded=False,
        ):
            advanced_col1, advanced_col2 = ui.columns(2)
            with advanced_col1:
                series_visual_signature_role = _enum_selectbox(
                    ui,
                    translate,
                    label_key="article_concretization.series_visual_signature_role",
                    fallback_label="系列视觉签名角色",
                    enum_cls=SeriesVisualSignatureRole,
                    default=SeriesVisualSignatureRole.NONE.value,
                    key=f"{key_prefix}_series_visual_signature_role",
                )
                diagram_visible_text_policy = _enum_selectbox(
                    ui,
                    translate,
                    label_key="article_concretization.diagram_visible_text_policy",
                    fallback_label="可见文字策略",
                    enum_cls=VisibleTextPolicy,
                    default=VisibleTextPolicy.NO_VISIBLE_TEXT.value,
                    key=f"{key_prefix}_diagram_visible_text_policy",
                )
            with advanced_col2:
                aspect_ratio_disabled = (
                    selected_template_type_for_storyboard == "static"
                    and not static_template_allows_layout_changes
                )
                diagram_aspect_ratio = _enum_selectbox(
                    ui,
                    translate,
                    label_key="article_concretization.diagram_aspect_ratio",
                    fallback_label="图解面板比例",
                    enum_cls=DiagramAspectRatio,
                    default=DiagramAspectRatio.AUTO.value,
                    key=f"{key_prefix}_diagram_aspect_ratio",
                    disabled=aspect_ratio_disabled,
                    help=translate(
                        "article_concretization.diagram_aspect_ratio_help",
                        fallback="控制图解面板自身比例；静态模板可能会固定布局。",
                    ),
                )
                if aspect_ratio_disabled:
                    ui.caption(
                        translate(
                            "article_concretization.diagram_aspect_ratio_static_hint",
                            fallback="静态模板不允许布局变化时，图解面板比例不可调整。",
                        )
                    )

            diagram_approved_labels = ui.text_area(
                translate(
                    "article_concretization.diagram_approved_labels",
                    fallback="批准标签",
                ),
                key=f"{key_prefix}_diagram_approved_labels",
                value=_session_text(
                    ui.session_state,
                    f"{key_prefix}_diagram_approved_labels",
                ),
                height=70,
                help=translate(
                    "article_concretization.diagram_approved_labels_help",
                    fallback="可用逗号、中文逗号、顿号或换行分隔。",
                ),
            )
            diagram_user_intent_hint = ui.text_area(
                translate(
                    "article_concretization.diagram_user_intent_hint",
                    fallback="补充意图",
                ),
                key=f"{key_prefix}_diagram_user_intent_hint",
                value=_session_text(
                    ui.session_state,
                    f"{key_prefix}_diagram_user_intent_hint",
                ),
                height=80,
                help=translate(
                    "article_concretization.diagram_user_intent_hint_help",
                    fallback="补充你希望图解强调的关系、冲突或解释方向。",
                ),
            )

    return build_article_concretization_payload(
        enabled=enabled,
        cognitive_anchor_kind=cognitive_anchor_kind,
        explanation_diagram_grammar=explanation_diagram_grammar,
        diagram_render_style=diagram_render_style,
        series_visual_signature_role=series_visual_signature_role,
        diagram_aspect_ratio=diagram_aspect_ratio,
        diagram_visible_text_policy=diagram_visible_text_policy,
        diagram_approved_labels=diagram_approved_labels,
        diagram_user_intent_hint=diagram_user_intent_hint,
    )


def _normalize_approved_labels(value: Sequence[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = _LABEL_SPLIT_PATTERN.split(value)
    else:
        raw_values = value

    normalized: list[str] = []
    for item in raw_values:
        if item is None:
            continue
        text = str(item.value if isinstance(item, Enum) else item).strip()
        if text:
            normalized.append(text)
    return normalized


def _enum_selectbox(
    ui,
    translate: Translate,
    *,
    label_key: str,
    fallback_label: str,
    enum_cls: type[Enum],
    default: str,
    key: str,
    disabled: bool = False,
    help: str | None = None,
) -> str:
    options = [item.value for item in enum_cls]
    index = options.index(default) if default in options else 0
    return ui.selectbox(
        translate(label_key, fallback=fallback_label),
        options=options,
        index=index,
        key=key,
        format_func=lambda value: translate(
            f"article_concretization.option.{value}",
            fallback=_OPTION_FALLBACK_LABELS.get(value, value),
        ),
        disabled=disabled,
        help=help,
    )


def _session_text(session_state, key: str) -> str:
    value = session_state.get(key, "")
    if value is None:
        return ""
    return str(value)


__all__ = [
    "build_article_concretization_payload",
    "render_article_concretization_controls",
]
