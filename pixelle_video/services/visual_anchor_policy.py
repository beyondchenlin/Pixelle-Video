from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy

CANVAS_OVERLAY_TERMS: tuple[str, ...] = (
    "画面角落", "画面边角", "画布角落", "画布边角", "右上角", "左上角", "右下角", "左下角",
    "角标", "水印", "UI层", "UI badge", "ui badge", "ui layer", "漂浮", "悬浮", "浮在",
    "corner logo", "corner bug", "canvas corner", "canvas corners", "screen corner", "screen corners",
    "lower right", "upper right", "lower left", "upper left", "watermark", "floating sticker", "overlay",
)

CANVAS_ONLY_SUPPORT_TERMS: tuple[str, ...] = (
    "画面", "画布", "镜头", "边缘", "角落", "屏幕角落", "canvas", "frame", "corner",
)

CONTENT_ACTION_CARRIER_TYPES: frozenset[str] = frozenset(
    {
        "content_bound_ip_actor",
        "content_bound_system_component",
        "content_bound_scale_reference",
        "content_bound_explanation_director",
    }
)

LEGACY_DECORATIVE_CARRIER_TYPES: frozenset[str] = frozenset(
    {
        "bookplate_or_stamp", "printed_mark", "embossed_mark", "engraved_mark", "surface_graphic",
        "decorative_object", "wearable_symbol", "small_supporting_prop", "embedded_mark", "wall_art",
        "screen_mark", "page_mark", "environment_detail", "partial_detail",
    }
)

CONTENT_FREE_MARK_TERMS: tuple[str, ...] = (
    "贴纸", "标签", "小标签", "卡片", "小卡片", "书签", "藏书票", "印章", "表面图案", "压印",
    "雕刻纹样", "logo", "Logo", "LOGO", "sticker", "label", "card", "bookmark", "bookplate", "stamp",
    "printed mark", "surface graphic", "badge",
)

IN_WORLD_CARRIER_TERMS: tuple[str, ...] = (
    # legacy material carriers
    "书", "书页", "纸", "封面", "地图", "图例", "相框", "照片", "桌", "桌面", "木板", "墙", "墙面",
    "黑板", "白板", "讲解板", "海报", "路牌", "招牌", "家具", "窗台", "地毯", "衣物", "屏幕", "地面",
    "book", "page", "paper", "map", "desk", "table", "wall", "poster", "sign", "prop", "surface", "ground", "floor",
    # content-bound arenas and affordances
    "解释空间", "档案室", "地图桌", "模型桌", "证据墙", "沙盘", "装置", "机器", "控制台", "把手", "拉杆", "筛选", "过滤器",
    "管道", "桥", "节点", "迷宫", "入口", "窄门", "天平", "砝码", "秤", "重物", "压力", "输入", "输出", "传送带", "路径",
    "关系线", "流程", "系统", "黑盒", "模块", "模型", "archive", "map table", "model desk", "evidence wall", "machine", "handle",
    "lever", "filter", "pipe", "bridge", "node", "maze", "scale", "weight", "input", "output", "workflow", "black box",
    "neutral explanation space", "explanatory model", "explanation model", "analytical diagram space",
)

MATERIAL_BINDING_TERMS: tuple[str, ...] = (
    "表面", "纸面", "木纹", "墙面", "刺绣", "雕刻", "压印", "印刷", "印在", "刻在", "绣在", "画在", "放在",
    "挂在", "嵌入", "贴合", "融入", "接触", "站在", "落在", "resting", "standing", "attached", "mounted",
    "painted", "engraved", "printed", "embossed", "embroidered",
)

CONTENT_ACTION_BINDING_TERMS: tuple[str, ...] = (
    "执行", "操作", "拉动", "推动", "搬动", "连接", "承受", "支撑", "衡量", "权衡", "观察", "整理", "排列", "搭建", "修复",
    "转化", "过滤", "穿过", "跨过", "指向", "调整", "分拣", "放置", "站在", "作用于", "参与", "承担", "operates", "pulls",
    "pushes", "carries", "connects", "weighs", "balances", "arranges", "repairs", "filters", "transforms", "crosses",
)

ANCHOR_INTERNAL_TERMS: tuple[str, ...] = (
    "视觉锚点", "visual anchor", "visual signature", "视觉签名", "support_anchor", "placement_zone", "carrier_type",
    "anchor_function", "prominence", "content_bound_ip_presence_plan", "rewrite_required", "policy", "forbidden",
)


@dataclass(frozen=True)
class SceneAnchorAffordances:
    """Scene-bound opportunities for content-bound recurring IP action."""

    carriers: tuple[str, ...]
    forbidden_zones: tuple[str, ...]
    notes: tuple[str, ...]


def anchor_identity_from_profile(anchor_profile: Any) -> str:
    raw_parts = [
        getattr(anchor_profile, "fixed_identity_clause", ""),
        getattr(anchor_profile, "canonical_identity_name", ""),
        getattr(anchor_profile, "visual_summary", ""),
        *_read_sequence(getattr(anchor_profile, "identity_lock", ())),
        *_read_sequence(getattr(anchor_profile, "required_identity_traits", ())),
        *_read_sequence(getattr(anchor_profile, "minimal_traits", ())),
        *_read_sequence(getattr(anchor_profile, "identity_anchors", ())),
        getattr(anchor_profile, "name", ""),
    ]
    candidates = [_clean_identity_part(part) for part in raw_parts]
    candidates = [part for part in candidates if part and not _generic_identity_part(part)]
    if not candidates:
        raise ValueError("mandatory visual signature requires a concrete identity kernel")
    phrase = _dedupe(candidates)[0]
    if phrase.endswith(("轮廓", "形象", "纹样", "小角色", "小物件")):
        return phrase
    if any(token in phrase for token in ("狗", "猫", "兔", "鸟", "雀", "机器人", "小人", "角色", "小黑")):
        return f"{phrase}轮廓"
    return phrase


def infer_scene_anchor_affordances(
    *,
    base_prompt: str,
    main_subjects: Sequence[str] = (),
    key_props: Sequence[str] = (),
) -> SceneAnchorAffordances:
    """Infer action affordances, not fallback cards, for content-bound IP."""

    text = " ".join([str(base_prompt or ""), " ".join(str(item or "") for item in key_props)])
    carriers: list[str] = []
    notes: list[str] = []

    for prop in key_props:
        prop_text = str(prop or "").strip()
        if prop_text and not _looks_like_canvas_only_support(prop_text):
            carriers.append(f"{prop_text}可被角色直接操作、连接、衡量或整理的位置")

    if _has_any(text, ("流程", "步骤", "方法", "工作流", "process", "workflow")):
        carriers.extend(("流程装置的把手或控制台", "输入输出机器的操作区", "传送带旁的分拣位置"))
    if _has_any(text, ("信息", "筛选", "过滤", "转化", "输入", "输出", "AI", "工具")):
        carriers.extend(("过滤机器入口", "黑盒模型的输入输出路径", "筛选装置的拉杆"))
    if _has_any(text, ("对比", "冲突", "权衡", "取舍", "两难")):
        carriers.extend(("左右拉扯绳索的中间位置", "天平两端的权衡位置", "两股力量之间的受力点"))
    if _has_any(text, ("风险", "成本", "规模", "增长", "差距", "压力")):
        carriers.extend(("巨大砝码旁的尺度位置", "越来越窄的门缝", "需要承受的重物下方空间"))
    if _has_any(text, ("关系", "结构", "系统", "机制", "平台", "行业")):
        carriers.extend(("关系模型桌", "节点与管道组成的系统结构", "桥梁或连接节点"))
    if _has_any(text, ("新闻", "案例", "调查", "证据", "复盘", "严肃", "灾难", "犯罪")):
        carriers.extend(("中性档案室的证据墙", "地图桌上的事件链模型", "不进入真实现场的解释沙盘"))

    carriers = _dedupe(carriers)
    if not carriers:
        notes.append("缺少动作位时必须重写画面隐喻，让角色参与内容动作；不得注入卡片、标签、书签或表面标记。")
    else:
        notes.append("优先把身份投影为内容动作参与者，而不是绑定到小载体或表面图案。")

    forbidden_zones = (
        "画布四角",
        "画面边缘悬浮层",
        "UI层、水印层、logo层",
        "小卡片、小标签、小书签、藏书票、印章、表面图案",
        "主体脸部、胸前关键标志和主要动作区域",
    )
    return SceneAnchorAffordances(
        carriers=tuple(carriers),
        forbidden_zones=forbidden_zones,
        notes=tuple(_dedupe(notes)),
    )


def is_content_bound_carrier_type(carrier_type: Any) -> bool:
    value = str(getattr(carrier_type, "value", carrier_type) or "").strip()
    return value in CONTENT_ACTION_CARRIER_TYPES


def is_scene_bound_anchor_candidate(
    *,
    image_prompt_clause: str,
    support_anchor: str,
    placement: str = "",
    contact_relation: str = "",
    carrier_type: Any = "",
    policy: VisualSignaturePolicy | None = None,
) -> bool:
    policy = policy or load_visual_signature_policy()
    clause = str(image_prompt_clause or "").strip()
    support = str(support_anchor or "").strip()
    placement_text = str(placement or "").strip()
    contact = str(contact_relation or "").strip()
    carrier_text = str(getattr(carrier_type, "value", carrier_type) or "").strip()

    if not clause:
        return False
    combined = " ".join([clause, support, placement_text, contact, carrier_text])

    if contains_forbidden_overlay_language(combined, policy=policy):
        return False
    if not policy.carrier_type_allowed(carrier_type):
        return False
    if _looks_like_canvas_only_support(support):
        return False
    if not support:
        return False

    if is_content_bound_carrier_type(carrier_type) or policy.is_content_bound_mandatory:
        if _has_any(combined, CONTENT_FREE_MARK_TERMS):
            return False
        if not _has_any(combined, IN_WORLD_CARRIER_TERMS):
            return False
        if not _has_any(combined, CONTENT_ACTION_BINDING_TERMS):
            return False
        return True

    if not _has_any(combined, IN_WORLD_CARRIER_TERMS):
        return False
    if _has_any(combined, ("漂浮", "悬浮", "浮在", "floating")):
        return False
    if not _has_any(combined, MATERIAL_BINDING_TERMS):
        return False
    return True


def contains_forbidden_overlay_language(text: str, *, policy: VisualSignaturePolicy | None = None) -> bool:
    value = str(text or "")
    if _has_any(value, CANVAS_OVERLAY_TERMS):
        return True
    if policy is None:
        policy = load_visual_signature_policy()
    return policy.contains_forbidden_overlay_text(value)


def sanitize_provider_anchor_clause(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    for term in ANCHOR_INTERNAL_TERMS:
        cleaned = cleaned.replace(term, "")
    return " ".join(cleaned.split()).strip(" ，,。.;；")


def _clean_identity_part(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip(" ，,。.;；")
    for prefix in ("Fixed IP identity:", "fixed identity:", "required identity traits:", "required traits:"):
        text = text.replace(prefix, "")
    return " ".join(text.split()).strip(" ，,。.;；")


def _generic_identity_part(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    return lowered in {"ip", "visual signature", "channel identity", "频道视觉签名", "频道识别", "频道识别轮廓", "视觉签名", "识别轮廓"}


def _looks_like_canvas_only_support(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if _has_any(text, IN_WORLD_CARRIER_TERMS):
        return False
    return any(term.lower() == lowered or term in text for term in CANVAS_ONLY_SUPPORT_TERMS)


def _has_any(text: str, values: Sequence[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(value or "").lower() in lowered for value in values if str(value or ""))


def _read_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),)


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


__all__ = [
    "CONTENT_ACTION_CARRIER_TYPES",
    "SceneAnchorAffordances",
    "anchor_identity_from_profile",
    "contains_forbidden_overlay_language",
    "infer_scene_anchor_affordances",
    "is_content_bound_carrier_type",
    "is_scene_bound_anchor_candidate",
    "sanitize_provider_anchor_clause",
]
