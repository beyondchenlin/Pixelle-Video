from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.content_bound_ip import (
    CONTENT_BOUND_POLICY_VERSION,
    DEFAULT_FORBIDDEN_IP_FORMS,
    ContentBoundIPPresencePlan,
    IPParticipationMechanism,
    contains_decorative_ip_language,
    contains_weak_ip_action_language,
    is_serious_content_text,
)


@dataclass(frozen=True)
class ContentBoundRepairResult:
    frame_visual_plans: tuple[dict[str, Any], ...]
    frame_ip_fusion_plans: tuple[dict[str, Any], ...]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_visual_plans": list(self.frame_visual_plans),
            "frame_ip_fusion_plans": list(self.frame_ip_fusion_plans),
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True)
class ContentBoundIPPlanner:
    """Deterministic contract owner for content-bound recurring IP presence.

    LLMs may propose a richer plan, but this service is the source-of-truth repair
    path.  It never solves missing IP by introducing a card, sticker, label,
    bookmark, surface mark, or logo-like carrier.  It rewrites the visual metaphor
    so the IP becomes a semantic participant.
    """

    def enrich_frame_visual_plan(
        self,
        frame_visual_plan: Mapping[str, Any],
        *,
        selected_visual_route: Mapping[str, Any] | None = None,
        article_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = dict(frame_visual_plan or {})
        route = dict(selected_visual_route or {})
        article = dict(article_summary or {})
        text = _joined_text(plan, route, article)
        serious = is_serious_content_text(text)
        mechanism = choose_ip_participation_mechanism(
            selected_visual_route=route,
            frame_visual_plan=plan,
            serious_content=serious,
        )
        cognitive_anchor = _first_text(plan.get("cognitive_anchor")) or _infer_cognitive_anchor(text, mechanism)
        physical_metaphor = _first_text(plan.get("physical_metaphor")) or _physical_metaphor(mechanism, cognitive_anchor, text)
        scene_arena = _first_text(plan.get("scene_arena")) or _scene_arena(mechanism, text, serious_content=serious)
        affordance = _first_text(plan.get("ip_action_affordance")) or _ip_action_affordance(mechanism, cognitive_anchor, physical_metaphor, serious_content=serious)
        enriched = {
            **plan,
            "cognitive_anchor": cognitive_anchor,
            "physical_metaphor": physical_metaphor,
            "scene_arena": scene_arena,
            "ip_action_affordance": affordance,
            "forbidden_ip_forms": list(plan.get("forbidden_ip_forms") or DEFAULT_FORBIDDEN_IP_FORMS),
            "content_bound_ip_ready": True,
            "serious_content_strategy": _serious_strategy(serious),
        }
        return enriched

    def plan_for_frame(
        self,
        frame_visual_plan: Mapping[str, Any],
        *,
        selected_visual_route: Mapping[str, Any] | None = None,
        style_harmonization: Mapping[str, Any] | None = None,
        article_summary: Mapping[str, Any] | None = None,
        ip_profile: Mapping[str, Any] | None = None,
        force_rewrite: bool = False,
        rewrite_reason: str = "",
    ) -> dict[str, Any]:
        visual_plan = self.enrich_frame_visual_plan(
            frame_visual_plan,
            selected_visual_route=selected_visual_route,
            article_summary=article_summary,
        )
        route = dict(selected_visual_route or {})
        style = dict(style_harmonization or {})
        text = _joined_text(visual_plan, route, article_summary or {})
        serious = is_serious_content_text(text)
        mechanism = choose_ip_participation_mechanism(
            selected_visual_route=route,
            frame_visual_plan=visual_plan,
            serious_content=serious,
        )
        cognitive_anchor = str(visual_plan.get("cognitive_anchor") or _infer_cognitive_anchor(text, mechanism))
        physical_metaphor = str(visual_plan.get("physical_metaphor") or _physical_metaphor(mechanism, cognitive_anchor, text))
        scene_arena = str(visual_plan.get("scene_arena") or _scene_arena(mechanism, text, serious_content=serious))
        action_verb = _action_verb(mechanism, cognitive_anchor)
        target = _interaction_target(mechanism, cognitive_anchor, physical_metaphor)
        semantic_action = _semantic_action(mechanism, cognitive_anchor, target)
        scene_binding = _scene_binding(mechanism, scene_arena, action_verb, target, serious_content=serious)
        rewrite_required = force_rewrite or _needs_rewrite_for_content_bound_ip(visual_plan)
        rewrite_instruction = rewrite_reason or (
            f"Rewrite the frame around {physical_metaphor} in {scene_arena}, with the recurring character visibly {action_verb} {target}."
            if rewrite_required
            else ""
        )
        presence = ContentBoundIPPresencePlan(
            frame_id=str(visual_plan.get("frame_id") or "frame"),
            participation_mechanism=mechanism,
            cognitive_anchor=cognitive_anchor,
            physical_metaphor=physical_metaphor,
            scene_arena=scene_arena,
            semantic_action=semantic_action,
            action_verb=action_verb,
            interaction_target=target,
            scene_binding=scene_binding,
            composition_role=_composition_role(mechanism, serious_content=serious),
            scale_role=_scale_role(mechanism),
            relation_to_article_subject="The recurring character explains or embodies the frame claim without replacing named article subjects.",
            semantic_removal_test="If the recurring character is removed, the frame loses the visible agent/state/component that performs the cognitive action.",
            decorative_risk_score=0.0,
            rewrite_required=rewrite_required,
            rewrite_instruction=rewrite_instruction,
            serious_content_strategy=_serious_strategy(serious),
            forbidden_ip_forms=tuple(visual_plan.get("forbidden_ip_forms") or DEFAULT_FORBIDDEN_IP_FORMS),
        )
        payload = presence.to_frame_ip_fusion_payload(
            style_harmonization=str(style.get("mode") or "hybrid_layered"),
        )
        payload["positive_prompt_clause"] = _positive_clause(presence, identity_phrase="configured recurring identity")
        payload["content_bound_repair_source"] = CONTENT_BOUND_POLICY_VERSION
        return payload

    def repair_batch(
        self,
        *,
        frame_visual_plans: Sequence[Mapping[str, Any]],
        frame_ip_fusion_plans: Sequence[Mapping[str, Any]],
        selected_visual_route: Mapping[str, Any] | None = None,
        style_harmonization: Mapping[str, Any] | None = None,
        article_summary: Mapping[str, Any] | None = None,
        ip_profile: Mapping[str, Any] | None = None,
        max_rewrite_passes: int = 1,
    ) -> ContentBoundRepairResult:
        repaired_visual: list[dict[str, Any]] = []
        repaired_ip: list[dict[str, Any]] = []
        repair_count = 0
        rejected_reasons: list[dict[str, Any]] = []
        ip_by_frame = {
            str(item.get("frame_id") or ""): dict(item)
            for item in frame_ip_fusion_plans
            if isinstance(item, Mapping)
        }
        for visual in frame_visual_plans:
            visual_plan = self.enrich_frame_visual_plan(
                visual,
                selected_visual_route=selected_visual_route,
                article_summary=article_summary,
            )
            frame_id = str(visual_plan.get("frame_id") or "frame")
            ip_plan = dict(ip_by_frame.get(frame_id) or {})
            reason = _invalid_ip_plan_reason(ip_plan)
            if reason:
                repair_count += 1
                rejected_reasons.append({"frame_id": frame_id, "reason": reason})
                ip_plan = self.plan_for_frame(
                    visual_plan,
                    selected_visual_route=selected_visual_route,
                    style_harmonization=style_harmonization,
                    article_summary=article_summary,
                    ip_profile=ip_profile,
                    force_rewrite=("rewrite_required" in reason or "decorative" in reason or "weak" in reason),
                    rewrite_reason=reason,
                )
                presence = dict(ip_plan.get("content_bound_ip_presence_plan") or {})
                if presence:
                    visual_plan = {
                        **visual_plan,
                        "cognitive_anchor": presence.get("cognitive_anchor") or visual_plan.get("cognitive_anchor"),
                        "physical_metaphor": presence.get("physical_metaphor") or visual_plan.get("physical_metaphor"),
                        "scene_arena": presence.get("scene_arena") or visual_plan.get("scene_arena"),
                        "ip_action_affordance": presence.get("scene_binding") or visual_plan.get("ip_action_affordance"),
                        "content_bound_rewrite_applied": bool(ip_plan.get("rewrite_required")),
                    }
                    # rewrite_required is now consumed by the deterministic repair.
                    ip_plan["rewrite_required"] = False
                    if isinstance(ip_plan.get("content_bound_ip_presence_plan"), Mapping):
                        ip_plan["content_bound_ip_presence_plan"] = {
                            **dict(ip_plan["content_bound_ip_presence_plan"]),
                            "rewrite_required": False,
                            "rewrite_instruction": "",
                        }
            else:
                ip_plan = self._normalize_valid_ip_plan(ip_plan, visual_plan, selected_visual_route, style_harmonization, article_summary, ip_profile)
            repaired_visual.append(visual_plan)
            repaired_ip.append(ip_plan)
        diagnostics = {
            "content_bound_policy_version": CONTENT_BOUND_POLICY_VERSION,
            "repair_count": repair_count,
            "rejected_reasons": rejected_reasons,
            "max_rewrite_passes": max(0, int(max_rewrite_passes)),
        }
        return ContentBoundRepairResult(
            frame_visual_plans=tuple(repaired_visual),
            frame_ip_fusion_plans=tuple(repaired_ip),
            diagnostics=diagnostics,
        )

    def _normalize_valid_ip_plan(
        self,
        ip_plan: Mapping[str, Any],
        visual_plan: Mapping[str, Any],
        selected_visual_route: Mapping[str, Any] | None,
        style_harmonization: Mapping[str, Any] | None,
        article_summary: Mapping[str, Any] | None,
        ip_profile: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        plan = dict(ip_plan)
        if not isinstance(plan.get("content_bound_ip_presence_plan"), Mapping):
            deterministic = self.plan_for_frame(
                visual_plan,
                selected_visual_route=selected_visual_route,
                style_harmonization=style_harmonization,
                article_summary=article_summary,
                ip_profile=ip_profile,
            )
            for key, value in deterministic.items():
                plan.setdefault(key, value)
        plan["content_relation_type"] = "content_bound"
        plan["decorative_risk_score"] = _score(plan.get("decorative_risk_score"), 0.0)
        return plan


def choose_ip_participation_mechanism(
    *,
    selected_visual_route: Mapping[str, Any] | None,
    frame_visual_plan: Mapping[str, Any] | None,
    serious_content: bool | None = None,
) -> IPParticipationMechanism:
    route = dict(selected_visual_route or {})
    frame = dict(frame_visual_plan or {})
    text = _joined_text(frame, route, {})
    if serious_content is None:
        serious_content = is_serious_content_text(text)
    if serious_content:
        return IPParticipationMechanism.EXPLANATION_DIRECTOR
    if _has_any(text, ("流程", "步骤", "方法", "工作流", "操作", "教程", "process", "workflow", "method", "steps")):
        return IPParticipationMechanism.ACTION_EXECUTOR
    if _has_any(text, ("焦虑", "压力", "困惑", "迷茫", "失败", "过载", "痛点", "anxiety", "pressure", "overload", "pain")):
        return IPParticipationMechanism.READER_PROXY
    if _has_any(text, ("黑盒", "机制", "系统", "模型", "结构", "过滤", "转化", "输入", "输出", "mechanism", "black box", "filter", "transform")):
        if _has_any(text, ("转化", "过滤", "输入", "输出", "transform", "filter")):
            return IPParticipationMechanism.TRANSFORMATION_MEDIUM
        return IPParticipationMechanism.SYSTEM_COMPONENT
    if _has_any(text, ("对比", "冲突", "权衡", "取舍", "两难", "contrast", "conflict", "tradeoff")):
        return IPParticipationMechanism.CONFLICT_PARTICIPANT
    if _has_any(text, ("成本", "规模", "风险", "增长", "差距", "重量", "距离", "cost", "scale", "risk", "growth", "gap")):
        return IPParticipationMechanism.SCALE_REFERENCE
    if _has_any(text, ("趋势", "现象", "行业", "社会", "城市", "平台", "trend", "industry", "society")):
        return IPParticipationMechanism.OBSERVATION_GATEWAY
    return IPParticipationMechanism.EXPLANATION_DIRECTOR


def _invalid_ip_plan_reason(ip_plan: Mapping[str, Any]) -> str:
    if not ip_plan:
        return "missing_content_bound_ip_plan"
    if _bool(ip_plan.get("rewrite_required"), False):
        return "rewrite_required_not_consumed"
    if str(ip_plan.get("content_relation_type") or "") != "content_bound" and not isinstance(ip_plan.get("content_bound_ip_presence_plan"), Mapping):
        return "missing_content_relation_type"
    relevant_text = " ".join(
        str(ip_plan.get(key) or "")
        for key in (
            "placement_logic",
            "action_or_function",
            "positive_prompt_clause",
            "duty_goal",
            "action_verb",
            "interaction_target",
            "scene_binding",
            "presentation_form",
            "fallback_presentation",
        )
    )
    if contains_decorative_ip_language(relevant_text):
        return "decorative_ip_carrier_rejected"
    if contains_weak_ip_action_language(relevant_text):
        return "weak_ip_action_rejected"
    if not str(ip_plan.get("action_verb") or "").strip():
        return "missing_action_verb"
    if not str(ip_plan.get("interaction_target") or "").strip():
        return "missing_interaction_target"
    if not str(ip_plan.get("scene_binding") or "").strip():
        return "missing_scene_binding"
    try:
        score = float(ip_plan.get("decorative_risk_score") or 0.0)
    except (TypeError, ValueError):
        score = 1.0
    if score > 0.3:
        return "decorative_risk_score_too_high"
    return ""


def _needs_rewrite_for_content_bound_ip(visual_plan: Mapping[str, Any]) -> bool:
    text = " ".join(str(visual_plan.get(key) or "") for key in ("visual_task", "visual_logic", "ip_action_affordance", "physical_metaphor", "scene_arena"))
    if contains_decorative_ip_language(text) or contains_weak_ip_action_language(text):
        return True
    return not bool(str(visual_plan.get("ip_action_affordance") or "").strip())


def _infer_cognitive_anchor(text: str, mechanism: IPParticipationMechanism) -> str:
    mapping = [
        (("筛选", "过滤", "filter"), "筛选"),
        (("对比", "冲突", "权衡", "tradeoff", "contrast"), "权衡"),
        (("连接", "关系", "network", "relationship"), "连接"),
        (("转化", "转换", "transform", "convert"), "转化"),
        (("阻断", "瓶颈", "卡住", "block", "bottleneck"), "阻断"),
        (("风险", "成本", "规模", "差距", "risk", "cost", "scale", "gap"), "衡量"),
        (("压力", "焦虑", "过载", "pressure", "overload"), "承受"),
        (("修复", "改善", "repair"), "修复"),
        (("流程", "步骤", "workflow", "process"), "操作"),
    ]
    for tokens, anchor in mapping:
        if _has_any(text, tokens):
            return anchor
    defaults = {
        IPParticipationMechanism.ACTION_EXECUTOR: "操作",
        IPParticipationMechanism.READER_PROXY: "承受",
        IPParticipationMechanism.OBSERVATION_GATEWAY: "观察",
        IPParticipationMechanism.SYSTEM_COMPONENT: "连接",
        IPParticipationMechanism.CONFLICT_PARTICIPANT: "权衡",
        IPParticipationMechanism.SCALE_REFERENCE: "衡量",
        IPParticipationMechanism.EXPLANATION_DIRECTOR: "拆解",
        IPParticipationMechanism.TRANSFORMATION_MEDIUM: "转化",
    }
    return defaults[mechanism]


def _physical_metaphor(mechanism: IPParticipationMechanism, cognitive_anchor: str, text: str) -> str:
    if mechanism is IPParticipationMechanism.ACTION_EXECUTOR:
        return f"一台低科技{cognitive_anchor}装置把抽象内容变成可见流程"
    if mechanism is IPParticipationMechanism.READER_PROXY:
        return f"一个代表读者处境的{cognitive_anchor}空间，压力以可见物体包围角色"
    if mechanism is IPParticipationMechanism.OBSERVATION_GATEWAY:
        return "巨大的系统地图、城市模型或规则迷宫，角色提供观看尺度"
    if mechanism is IPParticipationMechanism.SYSTEM_COMPONENT:
        return f"由节点、管道、桥梁或模块组成的{cognitive_anchor}系统"
    if mechanism is IPParticipationMechanism.CONFLICT_PARTICIPANT:
        return "两股力量、两端天平或拉扯绳索形成的权衡场景"
    if mechanism is IPParticipationMechanism.SCALE_REFERENCE:
        return "巨大的砝码、窄门、距离尺或体量差异形成的尺度隐喻"
    if mechanism is IPParticipationMechanism.TRANSFORMATION_MEDIUM:
        return "输入、处理、输出三段式转化机器或过滤通道"
    return "中性解释空间里的模型桌、证据墙或拆解沙盘"


def _scene_arena(mechanism: IPParticipationMechanism, text: str, *, serious_content: bool) -> str:
    if serious_content:
        return "中性新闻拆解空间、档案室或关系图模型桌"
    arenas = {
        IPParticipationMechanism.ACTION_EXECUTOR: "干净的解释空间中的低科技操作台",
        IPParticipationMechanism.READER_PROXY: "抽象但温和的读者心理场景",
        IPParticipationMechanism.OBSERVATION_GATEWAY: "大型系统模型或迷宫入口前",
        IPParticipationMechanism.SYSTEM_COMPONENT: "可剖开的机制装置内部",
        IPParticipationMechanism.CONFLICT_PARTICIPANT: "两端力量拉扯的简洁舞台",
        IPParticipationMechanism.SCALE_REFERENCE: "比例夸张的尺度空间",
        IPParticipationMechanism.TRANSFORMATION_MEDIUM: "输入输出清楚的转化通道",
        IPParticipationMechanism.EXPLANATION_DIRECTOR: "中性解释空间里的模型桌",
    }
    return arenas[mechanism]


def _ip_action_affordance(mechanism: IPParticipationMechanism, cognitive_anchor: str, physical_metaphor: str, *, serious_content: bool) -> str:
    if serious_content:
        return "角色在模型桌或关系图前移动线索、连接节点、指向事件链条"
    return _scene_binding(mechanism, "该隐喻场景", _action_verb(mechanism, cognitive_anchor), _interaction_target(mechanism, cognitive_anchor, physical_metaphor), serious_content=False)


def _action_verb(mechanism: IPParticipationMechanism, cognitive_anchor: str) -> str:
    if mechanism is IPParticipationMechanism.ACTION_EXECUTOR:
        return "操作"
    if mechanism is IPParticipationMechanism.READER_PROXY:
        return "承受并整理"
    if mechanism is IPParticipationMechanism.OBSERVATION_GATEWAY:
        return "观察并指向"
    if mechanism is IPParticipationMechanism.SYSTEM_COMPONENT:
        return "连接"
    if mechanism is IPParticipationMechanism.CONFLICT_PARTICIPANT:
        return "拉住并权衡"
    if mechanism is IPParticipationMechanism.SCALE_REFERENCE:
        return "衡量"
    if mechanism is IPParticipationMechanism.TRANSFORMATION_MEDIUM:
        return "转化"
    return "搭建并拆解"


def _interaction_target(mechanism: IPParticipationMechanism, cognitive_anchor: str, physical_metaphor: str) -> str:
    targets = {
        IPParticipationMechanism.ACTION_EXECUTOR: f"{cognitive_anchor}装置的把手、按钮或流程节点",
        IPParticipationMechanism.READER_PROXY: "压下来的信息块、任务线或压力物体",
        IPParticipationMechanism.OBSERVATION_GATEWAY: "系统地图、规则迷宫或趋势模型",
        IPParticipationMechanism.SYSTEM_COMPONENT: "节点、管道、桥梁或模块连接点",
        IPParticipationMechanism.CONFLICT_PARTICIPANT: "两端力量、天平或拉扯绳索",
        IPParticipationMechanism.SCALE_REFERENCE: "巨大砝码、窄门、距离尺或机会窗口",
        IPParticipationMechanism.TRANSFORMATION_MEDIUM: "输入输出通道、过滤器或转化机器",
        IPParticipationMechanism.EXPLANATION_DIRECTOR: "模型桌、证据墙、沙盘或关系线",
    }
    return targets[mechanism]


def _semantic_action(mechanism: IPParticipationMechanism, cognitive_anchor: str, target: str) -> str:
    return f"通过{_action_verb(mechanism, cognitive_anchor)}{target}来表达“{cognitive_anchor}”这个文章认知动作"


def _scene_binding(mechanism: IPParticipationMechanism, scene_arena: str, action_verb: str, target: str, *, serious_content: bool) -> str:
    if serious_content:
        return f"角色留在{scene_arena}中，{action_verb}{target}，以解释模型复盘事件而不进入真实事件现场"
    return f"角色位于{scene_arena}，身体动作直接作用于{target}，成为这一帧认知动作的可见参与者"


def _composition_role(mechanism: IPParticipationMechanism, *, serious_content: bool) -> str:
    if serious_content:
        return "前景或中景的克制分析者，提供视角入口但不戏剧化真实事件"
    roles = {
        IPParticipationMechanism.ACTION_EXECUTOR: "中景小型操作员，动作清楚但不抢占主体",
        IPParticipationMechanism.READER_PROXY: "读者代理角色，承担画面情绪中心",
        IPParticipationMechanism.OBSERVATION_GATEWAY: "前景观察者，提供尺度和视角入口",
        IPParticipationMechanism.SYSTEM_COMPONENT: "系统结构中的可见关键部件",
        IPParticipationMechanism.CONFLICT_PARTICIPANT: "冲突关系中的一方或中介点",
        IPParticipationMechanism.SCALE_REFERENCE: "尺度参照物，显示压力、大小或距离",
        IPParticipationMechanism.TRANSFORMATION_MEDIUM: "转化链路中的中间操作者或媒介",
        IPParticipationMechanism.EXPLANATION_DIRECTOR: "解释模型的导演和布景者",
    }
    return roles[mechanism]


def _scale_role(mechanism: IPParticipationMechanism) -> str:
    if mechanism is IPParticipationMechanism.SCALE_REFERENCE:
        return "used as a clear scale reference against a larger force or object"
    if mechanism in {IPParticipationMechanism.SYSTEM_COMPONENT, IPParticipationMechanism.TRANSFORMATION_MEDIUM}:
        return "integrated at the size required by the mechanism"
    return "supporting but readable"


def _serious_strategy(serious: bool) -> str:
    return "neutral_explanation_space_only; do not enter literal sensitive event scene" if serious else "normal_content_bound_scene"


def _positive_clause(plan: ContentBoundIPPresencePlan, *, identity_phrase: str) -> str:
    return (
        f"{plan.scene_arena}中有一个清晰可见的{identity_phrase}，"
        f"它{plan.action_verb}{plan.interaction_target}，"
        f"动作直接表达{plan.cognitive_anchor}，并与{plan.physical_metaphor}形成同一个视觉隐喻。"
    )


def _joined_text(*mappings: Mapping[str, Any]) -> str:
    parts: list[str] = []
    keys = (
        "source_text", "local_claim", "visual_task", "visual_logic", "visual_goal", "prompt_intent",
        "cognitive_anchor", "physical_metaphor", "scene_arena", "ip_action_affordance",
        "route_type", "route_name", "visual_premise", "why_it_fits_article", "risk", "summary", "core_claim", "central_problem",
    )
    for mapping in mappings:
        for key in keys:
            value = mapping.get(key)
            if value:
                parts.append(str(value))
    return " ".join(parts)


def _has_any(text: str, values: Sequence[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(value or "").lower() in lowered for value in values if str(value or ""))


def _first_text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).strip()


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return bool(value)


def _score(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number > 1.0 and number <= 10.0:
        number = number / 10.0
    return min(max(number, 0.0), 1.0)


__all__ = [
    "ContentBoundIPPlanner",
    "ContentBoundRepairResult",
    "choose_ip_participation_mechanism",
]
