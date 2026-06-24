from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any


class IPDutyPreset(str, Enum):
    AUTO = "auto"
    NONE = "none"
    HOST_EXPLAINER = "host_explainer"
    GUIDE_EXPLAINER = "guide_explainer"
    OPERATOR_DEMONSTRATOR = "operator_demonstrator"
    POINTER_ANNOTATOR = "pointer_annotator"
    COMPANION_WITNESS = "companion_witness"
    EVIDENCE_CURATOR = "evidence_curator"
    CONTRAST_JUDGE = "contrast_judge"
    EMOTIONAL_PROXY = "emotional_proxy"
    METAPHOR_SYMBOL = "metaphor_symbol"
    STRUCTURE_CARRIER = "structure_carrier"
    RELATIONSHIP_MEDIATOR = "relationship_mediator"
    NAVIGATOR_PATHFINDER = "navigator_pathfinder"
    MECHANIC_REPAIRER = "mechanic_repairer"
    THRESHOLD_GUARDIAN = "threshold_guardian"
    BACKGROUND_SIGNATURE = "background_signature"
    COMIC_COUNTERPOINT = "comic_counterpoint"

    @classmethod
    def from_value(cls, value: Any, *, default: "IPDutyPreset" | None = None) -> "IPDutyPreset":
        if isinstance(value, cls):
            return value
        text = str(getattr(value, "value", value) or "").strip()
        if not text:
            return default or cls.AUTO
        aliases = {
            "environment_branding": cls.BACKGROUND_SIGNATURE,
            "background_mark": cls.BACKGROUND_SIGNATURE,
            "silent_witness": cls.COMPANION_WITNESS,
            "witness": cls.COMPANION_WITNESS,
            "guide": cls.GUIDE_EXPLAINER,
            "operator": cls.OPERATOR_DEMONSTRATOR,
            "narrator": cls.HOST_EXPLAINER,
            "core_actor": cls.OPERATOR_DEMONSTRATOR,
            "symbol": cls.METAPHOR_SYMBOL,
            "container": cls.STRUCTURE_CARRIER,
            "obstacle": cls.THRESHOLD_GUARDIAN,
        }
        key = text.lower()
        if key in aliases:
            return aliases[key]
        for item in cls:
            if key == item.value or key == item.name.lower():
                return item
        return default or cls.AUTO


class IPPresentationForm(str, Enum):
    AUTO = "auto"
    FUNCTIONAL_ACTOR = "functional_actor"
    EMBEDDED_MARK = "embedded_mark"
    SMALL_SUPPORTING_PROP = "small_supporting_prop"
    BACKGROUND_SIGNATURE = "background_signature"
    STRUCTURE_ELEMENT = "structure_element"
    SYMBOLIC_PARTICIPANT = "symbolic_participant"

    @classmethod
    def from_value(cls, value: Any, *, default: "IPPresentationForm" | None = None) -> "IPPresentationForm":
        if isinstance(value, cls):
            return value
        text = str(getattr(value, "value", value) or "").strip().lower()
        if not text:
            return default or cls.AUTO
        aliases = {
            "function_bound_ip_actor": cls.FUNCTIONAL_ACTOR,
            "functional_ip_actor": cls.FUNCTIONAL_ACTOR,
            "minor_supporting_character": cls.FUNCTIONAL_ACTOR,
            "visible_supporting_character": cls.FUNCTIONAL_ACTOR,
            "printed_mark": cls.EMBEDDED_MARK,
            "page_mark": cls.EMBEDDED_MARK,
            "surface_graphic": cls.EMBEDDED_MARK,
            "environment_branding": cls.BACKGROUND_SIGNATURE,
        }
        if text in aliases:
            return aliases[text]
        for item in cls:
            if text == item.value or text == item.name.lower():
                return item
        return default or cls.AUTO


@dataclass(frozen=True)
class IPDutySpec:
    preset: IPDutyPreset
    role_family: str
    default_action_verb: str
    default_target: str
    default_presentation: IPPresentationForm
    fallback_presentation: IPPresentationForm
    semantic_removal_required: bool = True
    channel_identity_removal_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset.value,
            "role_family": self.role_family,
            "default_action_verb": self.default_action_verb,
            "default_target": self.default_target,
            "default_presentation": self.default_presentation.value,
            "fallback_presentation": self.fallback_presentation.value,
            "semantic_removal_required": self.semantic_removal_required,
            "channel_identity_removal_required": self.channel_identity_removal_required,
        }


_DUTY_SPECS: dict[IPDutyPreset, IPDutySpec] = {
    IPDutyPreset.HOST_EXPLAINER: IPDutySpec(IPDutyPreset.HOST_EXPLAINER, "explainer", "points to", "the main topic card", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.GUIDE_EXPLAINER: IPDutySpec(IPDutyPreset.GUIDE_EXPLAINER, "guide", "guides", "the route node", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.SMALL_SUPPORTING_PROP),
    IPDutyPreset.OPERATOR_DEMONSTRATOR: IPDutySpec(IPDutyPreset.OPERATOR_DEMONSTRATOR, "operator", "operates", "the process control", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.POINTER_ANNOTATOR: IPDutySpec(IPDutyPreset.POINTER_ANNOTATOR, "annotator", "marks", "the key evidence area", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.COMPANION_WITNESS: IPDutySpec(IPDutyPreset.COMPANION_WITNESS, "witness", "observes", "the analysis material", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.BACKGROUND_SIGNATURE, semantic_removal_required=False),
    IPDutyPreset.EVIDENCE_CURATOR: IPDutySpec(IPDutyPreset.EVIDENCE_CURATOR, "curator", "sorts", "the evidence cards", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.CONTRAST_JUDGE: IPDutySpec(IPDutyPreset.CONTRAST_JUDGE, "judge", "weighs", "the two comparison cards", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.EMOTIONAL_PROXY: IPDutySpec(IPDutyPreset.EMOTIONAL_PROXY, "emotional_proxy", "embodies", "the emotional pressure", IPPresentationForm.SYMBOLIC_PARTICIPANT, IPPresentationForm.SMALL_SUPPORTING_PROP),
    IPDutyPreset.METAPHOR_SYMBOL: IPDutySpec(IPDutyPreset.METAPHOR_SYMBOL, "symbol", "carries", "the metaphor object", IPPresentationForm.SYMBOLIC_PARTICIPANT, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.STRUCTURE_CARRIER: IPDutySpec(IPDutyPreset.STRUCTURE_CARRIER, "structure", "connects", "the structure modules", IPPresentationForm.STRUCTURE_ELEMENT, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.RELATIONSHIP_MEDIATOR: IPDutySpec(IPDutyPreset.RELATIONSHIP_MEDIATOR, "mediator", "organizes", "the relationship lines", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.NAVIGATOR_PATHFINDER: IPDutySpec(IPDutyPreset.NAVIGATOR_PATHFINDER, "navigator", "marks", "the path node", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.SMALL_SUPPORTING_PROP),
    IPDutyPreset.MECHANIC_REPAIRER: IPDutySpec(IPDutyPreset.MECHANIC_REPAIRER, "repairer", "repairs", "the blocked mechanism", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.THRESHOLD_GUARDIAN: IPDutySpec(IPDutyPreset.THRESHOLD_GUARDIAN, "guardian", "guards", "the boundary marker", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.BACKGROUND_SIGNATURE),
    IPDutyPreset.BACKGROUND_SIGNATURE: IPDutySpec(IPDutyPreset.BACKGROUND_SIGNATURE, "identity_mark", "identifies", "the scene carrier", IPPresentationForm.BACKGROUND_SIGNATURE, IPPresentationForm.EMBEDDED_MARK, semantic_removal_required=False),
    IPDutyPreset.COMIC_COUNTERPOINT: IPDutySpec(IPDutyPreset.COMIC_COUNTERPOINT, "counterpoint", "reacts to", "the absurd contrast", IPPresentationForm.FUNCTIONAL_ACTOR, IPPresentationForm.EMBEDDED_MARK),
    IPDutyPreset.NONE: IPDutySpec(IPDutyPreset.NONE, "none", "", "", IPPresentationForm.AUTO, IPPresentationForm.AUTO, semantic_removal_required=False, channel_identity_removal_required=False),
    IPDutyPreset.AUTO: IPDutySpec(IPDutyPreset.AUTO, "auto", "supports", "the frame meaning", IPPresentationForm.AUTO, IPPresentationForm.EMBEDDED_MARK),
}


@dataclass(frozen=True)
class IPDutyPlan:
    frame_id: str
    duty_preset: IPDutyPreset | str
    duty_goal: str
    action_verb: str
    interaction_target: str
    scene_binding: str
    presentation_form: IPPresentationForm | str = IPPresentationForm.AUTO
    fallback_presentation: IPPresentationForm | str = IPPresentationForm.EMBEDDED_MARK
    semantic_removal_test: str = ""
    channel_identity_removal_test: str = ""
    risk_notes: tuple[str, ...] = ()
    source: str = "auto"

    def __post_init__(self) -> None:
        preset = IPDutyPreset.from_value(self.duty_preset, default=IPDutyPreset.AUTO)
        spec = duty_spec(preset)
        presentation = IPPresentationForm.from_value(self.presentation_form, default=spec.default_presentation)
        fallback = IPPresentationForm.from_value(self.fallback_presentation, default=spec.fallback_presentation)
        object.__setattr__(self, "frame_id", _require_text(self.frame_id, "frame_id"))
        object.__setattr__(self, "duty_preset", preset)
        object.__setattr__(self, "presentation_form", presentation)
        object.__setattr__(self, "fallback_presentation", fallback)
        object.__setattr__(self, "duty_goal", _optional_text(self.duty_goal) or f"{spec.role_family} duty for this frame")
        object.__setattr__(self, "action_verb", _optional_text(self.action_verb) or spec.default_action_verb)
        object.__setattr__(self, "interaction_target", _optional_text(self.interaction_target) or spec.default_target)
        object.__setattr__(self, "scene_binding", _optional_text(self.scene_binding) or "physically connected to a real in-scene carrier")
        if spec.semantic_removal_required:
            semantic = _optional_text(self.semantic_removal_test) or "removing the IP would weaken the frame's explanatory action"
        else:
            semantic = _optional_text(self.semantic_removal_test) or "semantic meaning may remain, but the channel presence duty would be lost"
        channel = _optional_text(self.channel_identity_removal_test) or "removing the IP would remove the recurring channel identity from this frame"
        object.__setattr__(self, "semantic_removal_test", semantic)
        object.__setattr__(self, "channel_identity_removal_test", channel)
        object.__setattr__(self, "risk_notes", _text_tuple(self.risk_notes))
        object.__setattr__(self, "source", _optional_text(self.source) or "auto")

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None, *, frame_id: str | None = None) -> "IPDutyPlan":
        data = dict(source or {})
        legacy_role = data.get("ip_role") or data.get("role")
        preset = data.get("ip_duty_preset") or data.get("duty_preset") or data.get("duty") or duty_from_legacy_role(legacy_role)
        if IPDutyPreset.from_value(preset, default=IPDutyPreset.AUTO) is IPDutyPreset.AUTO:
            preset = duty_from_route_type(data.get("route_type") or data.get("visual_route_type"), legacy_role=legacy_role)
        spec = duty_spec(IPDutyPreset.from_value(preset, default=IPDutyPreset.AUTO))
        return cls(
            frame_id=frame_id or data.get("frame_id") or "frame",
            duty_preset=preset,
            duty_goal=data.get("duty_goal") or data.get("scene_function") or data.get("action_or_function") or "",
            action_verb=data.get("action_verb") or _verb_from_action(data.get("action_or_function")) or spec.default_action_verb,
            interaction_target=data.get("interaction_target") or data.get("target") or _target_from_text(data.get("action_or_function")) or spec.default_target,
            scene_binding=data.get("scene_binding") or data.get("placement_logic") or data.get("binding") or "",
            presentation_form=data.get("presentation_form") or data.get("manifestation_form") or spec.default_presentation,
            fallback_presentation=data.get("fallback_presentation") or spec.fallback_presentation,
            semantic_removal_test=data.get("semantic_removal_test") or data.get("removal_test") or "",
            channel_identity_removal_test=data.get("channel_identity_removal_test") or "",
            risk_notes=_text_tuple(data.get("risk_notes") or data.get("safety_warnings") or ()),
            source=data.get("source") or "mapping",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "ip_duty_preset": self.duty_preset.value,
            "duty_goal": self.duty_goal,
            "action_verb": self.action_verb,
            "interaction_target": self.interaction_target,
            "scene_binding": self.scene_binding,
            "presentation_form": self.presentation_form.value,
            "fallback_presentation": self.fallback_presentation.value,
            "semantic_removal_test": self.semantic_removal_test,
            "channel_identity_removal_test": self.channel_identity_removal_test,
            "risk_notes": list(self.risk_notes),
            "source": self.source,
        }


_ROUTE_TO_DUTY: dict[str, IPDutyPreset] = {
    "cognitive_explainer": IPDutyPreset.POINTER_ANNOTATOR,
    "philosophical_metaphor": IPDutyPreset.METAPHOR_SYMBOL,
    "mathematical_model": IPDutyPreset.OPERATOR_DEMONSTRATOR,
    "scientific_analogy": IPDutyPreset.OPERATOR_DEMONSTRATOR,
    "absurd_comic": IPDutyPreset.COMIC_COUNTERPOINT,
    "cartoon_story": IPDutyPreset.COMIC_COUNTERPOINT,
    "cinematic_scene": IPDutyPreset.COMPANION_WITNESS,
    "brand_key_visual": IPDutyPreset.HOST_EXPLAINER,
    "editorial_diagram": IPDutyPreset.POINTER_ANNOTATOR,
    "structure_map": IPDutyPreset.STRUCTURE_CARRIER,
    "process_map": IPDutyPreset.OPERATOR_DEMONSTRATOR,
    "relationship_map": IPDutyPreset.RELATIONSHIP_MEDIATOR,
    "emotional_theater": IPDutyPreset.EMOTIONAL_PROXY,
    "archive_investigation": IPDutyPreset.EVIDENCE_CURATOR,
    "game_level": IPDutyPreset.NAVIGATOR_PATHFINDER,
    "courtroom_argument": IPDutyPreset.CONTRAST_JUDGE,
    "mechanical_cutaway": IPDutyPreset.MECHANIC_REPAIRER,
}

_ROLE_TO_DUTY: dict[str, IPDutyPreset] = {
    "none": IPDutyPreset.NONE,
    "operator": IPDutyPreset.OPERATOR_DEMONSTRATOR,
    "guide": IPDutyPreset.GUIDE_EXPLAINER,
    "silent_witness": IPDutyPreset.COMPANION_WITNESS,
    "background_mark": IPDutyPreset.BACKGROUND_SIGNATURE,
    "symbol": IPDutyPreset.METAPHOR_SYMBOL,
    "narrator": IPDutyPreset.HOST_EXPLAINER,
    "core_actor": IPDutyPreset.OPERATOR_DEMONSTRATOR,
    "container": IPDutyPreset.STRUCTURE_CARRIER,
    "obstacle": IPDutyPreset.THRESHOLD_GUARDIAN,
}

_SERIOUS_RISK_MARKERS = (
    "严肃",
    "纪实",
    "纪录",
    "真实人物",
    "历史人物",
    "灾难",
    "悼念",
    "宗教",
    "法律",
    "版权",
    "品牌",
    "奥特曼",
    "超人",
    "news",
    "documentary",
    "real person",
    "Superman",
    "Ultraman",
    "copyrighted character",
    "brand character",
)


def duty_spec(preset: IPDutyPreset | str) -> IPDutySpec:
    return _DUTY_SPECS[IPDutyPreset.from_value(preset, default=IPDutyPreset.AUTO)]


def duty_from_legacy_role(role: Any) -> IPDutyPreset:
    key = str(getattr(role, "value", role) or "").strip().lower()
    return _ROLE_TO_DUTY.get(key, IPDutyPreset.AUTO)


def duty_from_route_type(route_type: Any, *, legacy_role: Any = None, risk_text: str = "") -> IPDutyPreset:
    risk = str(risk_text or "")
    if any(marker.lower() in risk.lower() for marker in _SERIOUS_RISK_MARKERS):
        return IPDutyPreset.BACKGROUND_SIGNATURE
    role_duty = duty_from_legacy_role(legacy_role)
    if role_duty is not IPDutyPreset.AUTO:
        return role_duty
    key = str(getattr(route_type, "value", route_type) or "").strip().lower()
    if not key:
        return IPDutyPreset.BACKGROUND_SIGNATURE
    return _ROUTE_TO_DUTY.get(key, IPDutyPreset.BACKGROUND_SIGNATURE)


def build_default_ip_duty_plan(
    *,
    frame_id: str,
    route_type: Any = None,
    legacy_role: Any = None,
    local_claim: str = "",
    visual_task: str = "",
    risk_text: str = "",
) -> IPDutyPlan:
    preset = duty_from_route_type(route_type, legacy_role=legacy_role, risk_text=risk_text)
    spec = duty_spec(preset)
    goal = _optional_text(visual_task) or _optional_text(local_claim) or f"{spec.role_family} duty for the frame"
    return IPDutyPlan(
        frame_id=frame_id,
        duty_preset=preset,
        duty_goal=goal,
        action_verb=spec.default_action_verb,
        interaction_target=spec.default_target,
        scene_binding="physically interacts with the local scene structure",
        presentation_form=spec.default_presentation,
        fallback_presentation=spec.fallback_presentation,
        source="deterministic_route_duty",
    )


def compact_ip_duty_payload(value: Mapping[str, Any] | IPDutyPlan | None) -> dict[str, Any]:
    plan = value if isinstance(value, IPDutyPlan) else IPDutyPlan.from_mapping(value or {})
    return {
        "frame_id": plan.frame_id,
        "ip_duty_preset": plan.duty_preset.value,
        "duty_goal": plan.duty_goal,
        "action_verb": plan.action_verb,
        "interaction_target": plan.interaction_target,
        "scene_binding": plan.scene_binding,
        "presentation_form": plan.presentation_form.value,
        "fallback_presentation": plan.fallback_presentation.value,
        "semantic_removal_test": plan.semantic_removal_test,
        "channel_identity_removal_test": plan.channel_identity_removal_test,
    }


def _verb_from_action(value: Any) -> str:
    text = _optional_text(value)
    if not text:
        return ""
    for token in ("sorts", "marks", "points to", "operates", "guides", "guards", "repairs", "weighs", "observes", "connects", "carries"):
        if token in text.lower():
            return token
    for token in ("整理", "标记", "指向", "操作", "引导", "守住", "修复", "称量", "观察", "连接", "承载"):
        if token in text:
            return token
    return "supports"


def _target_from_text(value: Any) -> str:
    text = _optional_text(value)
    if not text:
        return ""
    separators = ("target:", "目标：", "对象：")
    lowered = text.lower()
    for sep in separators:
        index = lowered.find(sep.lower())
        if index >= 0:
            return text[index + len(sep):].strip(" ：:，,。.;；")[:80]
    return ""


def _require_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).strip()


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
    "IPDutyPlan",
    "IPDutyPreset",
    "IPDutySpec",
    "IPPresentationForm",
    "build_default_ip_duty_plan",
    "compact_ip_duty_payload",
    "duty_from_legacy_role",
    "duty_from_route_type",
    "duty_spec",
]
