from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.models.ip_duty import IPDutyPreset, IPPresentationForm
from pixelle_video.utils.bool_parsing import coerce_bool


class IPParticipationMechanism(str, Enum):
    """Content-bound ways a recurring IP may appear in a frame.

    These are not logo/carrier modes.  Each mechanism describes a semantic duty
    that makes the IP necessary to the frame's article explanation.
    """

    ACTION_EXECUTOR = "action_executor"
    READER_PROXY = "reader_proxy"
    OBSERVATION_GATEWAY = "observation_gateway"
    SYSTEM_COMPONENT = "system_component"
    CONFLICT_PARTICIPANT = "conflict_participant"
    SCALE_REFERENCE = "scale_reference"
    EXPLANATION_DIRECTOR = "explanation_director"
    TRANSFORMATION_MEDIUM = "transformation_medium"

    @classmethod
    def from_value(cls, value: Any, *, default: "IPParticipationMechanism" | None = None) -> "IPParticipationMechanism":
        if isinstance(value, cls):
            return value
        text = str(getattr(value, "value", value) or "").strip().lower()
        if not text:
            return default or cls.EXPLANATION_DIRECTOR
        aliases = {
            "operator": cls.ACTION_EXECUTOR,
            "executor": cls.ACTION_EXECUTOR,
            "guide": cls.EXPLANATION_DIRECTOR,
            "host": cls.EXPLANATION_DIRECTOR,
            "witness": cls.OBSERVATION_GATEWAY,
            "observer": cls.OBSERVATION_GATEWAY,
            "component": cls.SYSTEM_COMPONENT,
            "structure": cls.SYSTEM_COMPONENT,
            "contrast": cls.CONFLICT_PARTICIPANT,
            "judge": cls.CONFLICT_PARTICIPANT,
            "scale": cls.SCALE_REFERENCE,
            "proxy": cls.READER_PROXY,
            "emotional_proxy": cls.READER_PROXY,
            "transformer": cls.TRANSFORMATION_MEDIUM,
        }
        if text in aliases:
            return aliases[text]
        for item in cls:
            if text == item.value or text == item.name.lower():
                return item
        return default or cls.EXPLANATION_DIRECTOR


CONTENT_BOUND_POLICY_VERSION = "content_bound_ip_presence.v2"

DECORATIVE_IP_TERMS: tuple[str, ...] = (
    "贴纸", "logo", "Logo", "LOGO", "角标", "水印", "书签", "标签", "卡片", "小卡片", "印章",
    "藏书票", "压印", "雕刻纹样", "表面图案", "纹章", "徽章", "badge", "sticker", "corner",
    "watermark", "bookmark", "label", "stamp", "bookplate", "surface graphic", "printed mark",
)
WEAK_IP_ACTION_TERMS: tuple[str, ...] = (
    "只是出现", "仅出现", "站在旁边", "安静出现", "低调露出", "作为装饰", "作为小标识", "小型陪衬",
    "quietly appears", "stands beside", "standing beside", "decorative", "small supporting in-scene element",
)
SERIOUS_CONTENT_TERMS: tuple[str, ...] = (
    "灾难", "事故", "悼念", "犯罪", "战争", "冲突", "死亡", "伤亡", "医疗风险", "金融风险", "政治冲突",
    "真实人物", "历史人物", "宗教", "纪实", "新闻", "调查", "争议", "lawsuit", "crime", "war", "death",
    "disaster", "medical risk", "financial risk", "political conflict", "real person", "documentary", "news",
)
DEFAULT_FORBIDDEN_IP_FORMS: tuple[str, ...] = (
    "sticker", "logo", "corner_badge", "watermark", "bookmark", "label", "stamp", "small_card",
    "bookplate", "printed_mark", "surface_graphic", "decorative_prop",
)

_MECHANISM_TO_DUTY: dict[IPParticipationMechanism, IPDutyPreset] = {
    IPParticipationMechanism.ACTION_EXECUTOR: IPDutyPreset.OPERATOR_DEMONSTRATOR,
    IPParticipationMechanism.READER_PROXY: IPDutyPreset.EMOTIONAL_PROXY,
    IPParticipationMechanism.OBSERVATION_GATEWAY: IPDutyPreset.COMPANION_WITNESS,
    IPParticipationMechanism.SYSTEM_COMPONENT: IPDutyPreset.STRUCTURE_CARRIER,
    IPParticipationMechanism.CONFLICT_PARTICIPANT: IPDutyPreset.CONTRAST_JUDGE,
    IPParticipationMechanism.SCALE_REFERENCE: IPDutyPreset.METAPHOR_SYMBOL,
    IPParticipationMechanism.EXPLANATION_DIRECTOR: IPDutyPreset.GUIDE_EXPLAINER,
    IPParticipationMechanism.TRANSFORMATION_MEDIUM: IPDutyPreset.MECHANIC_REPAIRER,
}

_MECHANISM_TO_PRESENTATION: dict[IPParticipationMechanism, IPPresentationForm] = {
    IPParticipationMechanism.ACTION_EXECUTOR: IPPresentationForm.FUNCTIONAL_ACTOR,
    IPParticipationMechanism.READER_PROXY: IPPresentationForm.SYMBOLIC_PARTICIPANT,
    IPParticipationMechanism.OBSERVATION_GATEWAY: IPPresentationForm.FUNCTIONAL_ACTOR,
    IPParticipationMechanism.SYSTEM_COMPONENT: IPPresentationForm.STRUCTURE_ELEMENT,
    IPParticipationMechanism.CONFLICT_PARTICIPANT: IPPresentationForm.FUNCTIONAL_ACTOR,
    IPParticipationMechanism.SCALE_REFERENCE: IPPresentationForm.SYMBOLIC_PARTICIPANT,
    IPParticipationMechanism.EXPLANATION_DIRECTOR: IPPresentationForm.FUNCTIONAL_ACTOR,
    IPParticipationMechanism.TRANSFORMATION_MEDIUM: IPPresentationForm.FUNCTIONAL_ACTOR,
}

_MECHANISM_TO_ROLE: dict[IPParticipationMechanism, str] = {
    IPParticipationMechanism.ACTION_EXECUTOR: "operator",
    IPParticipationMechanism.READER_PROXY: "core_actor",
    IPParticipationMechanism.OBSERVATION_GATEWAY: "guide",
    IPParticipationMechanism.SYSTEM_COMPONENT: "container",
    IPParticipationMechanism.CONFLICT_PARTICIPANT: "obstacle",
    IPParticipationMechanism.SCALE_REFERENCE: "symbol",
    IPParticipationMechanism.EXPLANATION_DIRECTOR: "guide",
    IPParticipationMechanism.TRANSFORMATION_MEDIUM: "operator",
}


@dataclass(frozen=True)
class ContentBoundIPPresencePlan:
    frame_id: str
    participation_mechanism: IPParticipationMechanism | str
    cognitive_anchor: str
    physical_metaphor: str
    scene_arena: str
    semantic_action: str
    action_verb: str
    interaction_target: str
    scene_binding: str
    composition_role: str
    scale_role: str = "supporting but readable"
    identity_binding: str = "same configured recurring identity"
    relation_to_article_subject: str = "preserves article subjects and does not replace them"
    semantic_removal_test: str = "removing the recurring character weakens the frame's explanatory action"
    decorative_risk_score: float = 0.0
    rewrite_required: bool = False
    rewrite_instruction: str = ""
    serious_content_strategy: str = ""
    forbidden_ip_forms: tuple[str, ...] = field(default_factory=lambda: DEFAULT_FORBIDDEN_IP_FORMS)
    version: str = CONTENT_BOUND_POLICY_VERSION

    def __post_init__(self) -> None:
        mechanism = IPParticipationMechanism.from_value(self.participation_mechanism)
        object.__setattr__(self, "participation_mechanism", mechanism)
        object.__setattr__(self, "frame_id", _require_text(self.frame_id, "frame_id"))
        object.__setattr__(self, "cognitive_anchor", _require_text(self.cognitive_anchor, "cognitive_anchor"))
        object.__setattr__(self, "physical_metaphor", _require_text(self.physical_metaphor, "physical_metaphor"))
        object.__setattr__(self, "scene_arena", _require_text(self.scene_arena, "scene_arena"))
        object.__setattr__(self, "semantic_action", _require_text(self.semantic_action, "semantic_action"))
        object.__setattr__(self, "action_verb", _require_text(self.action_verb, "action_verb"))
        object.__setattr__(self, "interaction_target", _require_text(self.interaction_target, "interaction_target"))
        object.__setattr__(self, "scene_binding", _require_text(self.scene_binding, "scene_binding"))
        object.__setattr__(self, "composition_role", _require_text(self.composition_role, "composition_role"))
        object.__setattr__(self, "scale_role", _optional_text(self.scale_role) or "supporting but readable")
        object.__setattr__(self, "identity_binding", _optional_text(self.identity_binding) or "same configured recurring identity")
        object.__setattr__(self, "relation_to_article_subject", _optional_text(self.relation_to_article_subject) or "preserves article subjects")
        object.__setattr__(self, "semantic_removal_test", _optional_text(self.semantic_removal_test) or "removing the recurring character weakens the frame's explanatory action")
        object.__setattr__(self, "decorative_risk_score", _score(self.decorative_risk_score))
        object.__setattr__(self, "rewrite_required", coerce_bool(self.rewrite_required, default=False))
        object.__setattr__(self, "rewrite_instruction", _optional_text(self.rewrite_instruction))
        object.__setattr__(self, "serious_content_strategy", _optional_text(self.serious_content_strategy))
        object.__setattr__(self, "forbidden_ip_forms", _text_tuple(self.forbidden_ip_forms or DEFAULT_FORBIDDEN_IP_FORMS))
        object.__setattr__(self, "version", _optional_text(self.version) or CONTENT_BOUND_POLICY_VERSION)

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None, *, frame_id: str | None = None) -> "ContentBoundIPPresencePlan":
        data = dict(source or {})
        if "content_bound_ip_presence_plan" in data and isinstance(data.get("content_bound_ip_presence_plan"), Mapping):
            data = {**dict(data.get("content_bound_ip_presence_plan") or {}), **data}
        return cls(
            frame_id=frame_id or data.get("frame_id") or "frame",
            participation_mechanism=data.get("participation_mechanism") or data.get("ip_participation_mechanism") or data.get("mechanism") or IPParticipationMechanism.EXPLANATION_DIRECTOR,
            cognitive_anchor=data.get("cognitive_anchor") or "explain",
            physical_metaphor=data.get("physical_metaphor") or data.get("metaphor") or "neutral explanation model",
            scene_arena=data.get("scene_arena") or data.get("visual_arena") or "neutral explanation space",
            semantic_action=data.get("semantic_action") or data.get("action_or_function") or data.get("duty_goal") or "explains the article point through a concrete action",
            action_verb=data.get("action_verb") or _verb_from_text(data.get("semantic_action") or data.get("action_or_function")) or "arranges",
            interaction_target=data.get("interaction_target") or data.get("target") or "the explanatory model",
            scene_binding=data.get("scene_binding") or data.get("placement_logic") or "the recurring character directly interacts with the explanatory model",
            composition_role=data.get("composition_role") or data.get("presentation_form") or "中景可见参与者，动作服务画面解释",
            scale_role=data.get("scale_role") or "supporting but readable",
            identity_binding=data.get("identity_binding") or "same configured recurring identity",
            relation_to_article_subject=data.get("relation_to_article_subject") or "preserves article subjects and does not replace them",
            semantic_removal_test=data.get("semantic_removal_test") or data.get("removal_test") or "removing the recurring character weakens the frame's explanatory action",
            decorative_risk_score=data.get("decorative_risk_score") or 0.0,
            rewrite_required=data.get("rewrite_required") or False,
            rewrite_instruction=data.get("rewrite_instruction") or "",
            serious_content_strategy=data.get("serious_content_strategy") or "",
            forbidden_ip_forms=tuple(data.get("forbidden_ip_forms") or DEFAULT_FORBIDDEN_IP_FORMS),
        )

    @property
    def duty_preset(self) -> IPDutyPreset:
        return _MECHANISM_TO_DUTY[self.participation_mechanism]

    @property
    def presentation_form(self) -> IPPresentationForm:
        return _MECHANISM_TO_PRESENTATION[self.participation_mechanism]

    @property
    def legacy_ip_role(self) -> str:
        return _MECHANISM_TO_ROLE[self.participation_mechanism]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frame_id": self.frame_id,
            "participation_mechanism": self.participation_mechanism.value,
            "cognitive_anchor": self.cognitive_anchor,
            "physical_metaphor": self.physical_metaphor,
            "scene_arena": self.scene_arena,
            "semantic_action": self.semantic_action,
            "action_verb": self.action_verb,
            "interaction_target": self.interaction_target,
            "scene_binding": self.scene_binding,
            "composition_role": self.composition_role,
            "scale_role": self.scale_role,
            "identity_binding": self.identity_binding,
            "relation_to_article_subject": self.relation_to_article_subject,
            "semantic_removal_test": self.semantic_removal_test,
            "decorative_risk_score": self.decorative_risk_score,
            "rewrite_required": self.rewrite_required,
            "rewrite_instruction": self.rewrite_instruction,
            "serious_content_strategy": self.serious_content_strategy,
            "forbidden_ip_forms": list(self.forbidden_ip_forms),
        }

    def to_frame_ip_fusion_payload(self, *, style_harmonization: str = "hybrid_layered") -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "ip_role": self.legacy_ip_role,
            "ip_visibility": "medium",
            "placement_logic": self.scene_binding,
            "action_or_function": self.semantic_action,
            "relation_to_article_subject": self.relation_to_article_subject,
            "style_harmonization": style_harmonization or "hybrid_layered",
            "positive_prompt_clause": image_prompt_clause_from_presence_plan(self, identity_phrase="configured recurring identity"),
            "negative_constraints": [
                "preserve article subjects",
                "use the configured recurring identity as a visible content participant",
            ],
            "ip_duty_preset": self.duty_preset.value,
            "duty_goal": self.semantic_action,
            "action_verb": self.action_verb,
            "interaction_target": self.interaction_target,
            "scene_binding": self.scene_binding,
            "presentation_form": self.presentation_form.value,
            "fallback_presentation": self.presentation_form.value,
            "semantic_removal_test": self.semantic_removal_test,
            "channel_identity_removal_test": "removing the recurring character removes the channel identity from this frame",
            "ip_participation_mechanism": self.participation_mechanism.value,
            "cognitive_anchor": self.cognitive_anchor,
            "physical_metaphor": self.physical_metaphor,
            "content_relation_type": "content_bound",
            "decorative_risk_score": self.decorative_risk_score,
            "rewrite_required": self.rewrite_required,
            "rewrite_instruction": self.rewrite_instruction,
            "content_bound_ip_presence_plan": self.to_dict(),
        }


def duty_from_mechanism(value: Any) -> IPDutyPreset:
    return _MECHANISM_TO_DUTY[IPParticipationMechanism.from_value(value)]


def presentation_from_mechanism(value: Any) -> IPPresentationForm:
    return _MECHANISM_TO_PRESENTATION[IPParticipationMechanism.from_value(value)]


def is_serious_content_text(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term.lower() in lowered for term in SERIOUS_CONTENT_TERMS)


def contains_decorative_ip_language(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term.lower() in lowered for term in DECORATIVE_IP_TERMS)


def contains_weak_ip_action_language(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term.lower() in lowered for term in WEAK_IP_ACTION_TERMS)


def image_prompt_clause_from_presence_plan(plan: ContentBoundIPPresencePlan, *, identity_phrase: str) -> str:
    identity = _optional_text(identity_phrase) or "configured recurring identity"
    action_phrase = _action_phrase(plan.action_verb, plan.interaction_target)
    # Provider-facing visual description only: no policy words, no “do not”.
    return (
        f"{plan.scene_arena}中出现一个清晰可见的{identity}，"
        f"它{action_phrase}，"
        f"这个动作直接表达{plan.cognitive_anchor}：{plan.physical_metaphor}；"
        f"{plan.scene_binding}，{plan.composition_role}。"
    )


def positive_visual_clause_from_payload(payload: Mapping[str, Any], *, identity_phrase: str) -> str:
    return image_prompt_clause_from_presence_plan(ContentBoundIPPresencePlan.from_mapping(payload), identity_phrase=identity_phrase)


def _verb_from_text(value: Any) -> str:
    text = _optional_text(value)
    if not text:
        return ""
    for token in ("筛选", "整理", "连接", "操作", "引导", "称量", "承受", "观察", "修复", "搭建", "转化", "阻挡", "推动", "拉动"):
        if token in text:
            return token
    for token in ("filter", "sort", "connect", "operate", "guide", "weigh", "carry", "observe", "repair", "build", "transform", "block", "push", "pull"):
        if token in text.lower():
            return token
    return "arranges"


def _action_phrase(action_verb: Any, interaction_target: Any) -> str:
    verb = _optional_text(action_verb)
    target = _optional_text(interaction_target)
    if not verb:
        return target
    if not target:
        return verb
    if _is_ascii_words(verb) or _is_ascii_words(target):
        return f" {verb} {target}"
    return f"{verb}{target}"


def _is_ascii_words(value: str) -> bool:
    return bool(value) and value.isascii() and bool(re.search(r"[A-Za-z]", value))


def _require_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).strip()


def _score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return min(number / 10.0, 1.0) if number <= 10 else 1.0
    return round(number, 4)


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
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return tuple(result)


__all__ = [
    "CONTENT_BOUND_POLICY_VERSION",
    "DECORATIVE_IP_TERMS",
    "DEFAULT_FORBIDDEN_IP_FORMS",
    "IPParticipationMechanism",
    "ContentBoundIPPresencePlan",
    "contains_decorative_ip_language",
    "contains_weak_ip_action_language",
    "duty_from_mechanism",
    "image_prompt_clause_from_presence_plan",
    "is_serious_content_text",
    "positive_visual_clause_from_payload",
    "presentation_from_mechanism",
]
