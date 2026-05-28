from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


CANVAS_OVERLAY_TERMS: tuple[str, ...] = (
    "画面角落",
    "画面边角",
    "画布角落",
    "画布边角",
    "右上角",
    "左上角",
    "右下角",
    "左下角",
    "角标",
    "水印",
    "logo",
    "Logo",
    "LOGO",
    "UI层",
    "UI badge",
    "ui badge",
    "ui layer",
    "贴纸",
    "漂浮",
    "悬浮",
    "浮在",
    "corner logo",
    "corner bug",
    "canvas corner",
    "canvas corners",
    "screen corner",
    "screen corners",
    "lower right",
    "upper right",
    "lower left",
    "upper left",
    "watermark",
    "floating sticker",
    "sticker",
    "overlay",
)

CANVAS_ONLY_SUPPORT_TERMS: tuple[str, ...] = (
    "画面",
    "画布",
    "镜头",
    "边缘",
    "角落",
    "屏幕角落",
    "canvas",
    "frame",
    "corner",
)

IN_WORLD_CARRIER_TERMS: tuple[str, ...] = (
    "书",
    "书页",
    "纸",
    "纸张",
    "封面",
    "书签",
    "藏书票",
    "印章",
    "压印",
    "纹章",
    "徽章",
    "胸针",
    "吊坠",
    "地图",
    "图例",
    "卡片",
    "相框",
    "照片",
    "桌",
    "桌面",
    "木板",
    "长椅",
    "椅子",
    "墙",
    "墙面",
    "壁画",
    "黑板",
    "白板",
    "讲解板",
    "海报",
    "路牌",
    "招牌",
    "门牌",
    "家具",
    "窗台",
    "地毯",
    "衣物",
    "衣服",
    "刺绣",
    "屏幕中的",
    "节目内容",
    "电视柜",
    "地面",
    "地表",
    "场景空间",
    "主体层空间",
    "in-world",
    "book",
    "page",
    "paper",
    "cover",
    "bookmark",
    "stamp",
    "emboss",
    "engraved",
    "emblem",
    "map",
    "card",
    "desk",
    "table",
    "wall",
    "mural",
    "poster",
    "sign",
    "prop",
    "surface",
    "fabric",
    "ground",
    "floor",
)

MATERIAL_BINDING_TERMS: tuple[str, ...] = (
    "表面",
    "纸面",
    "木纹",
    "墙面",
    "刺绣",
    "雕刻",
    "压印",
    "印刷",
    "印在",
    "刻在",
    "绣在",
    "画在",
    "放在",
    "挂在",
    "嵌入",
    "贴合",
    "融入",
    "接触",
    "站在",
    "落在",
    "resting",
    "standing",
    "attached",
    "mounted",
    "painted",
    "engraved",
    "printed",
    "embossed",
    "embroidered",
)

ANCHOR_INTERNAL_TERMS: tuple[str, ...] = (
    "视觉锚点",
    "visual anchor",
    "IP角色",
    "IP role",
    "IP",
    "support_anchor",
    "placement_zone",
    "carrier_type",
    "anchor_function",
    "prominence",
)


@dataclass(frozen=True)
class SceneAnchorAffordances:
    """Scene-bound carrier opportunities for a recurring visual signature."""

    carriers: tuple[str, ...]
    forbidden_zones: tuple[str, ...]
    notes: tuple[str, ...]


def anchor_identity_from_profile(anchor_profile: Any) -> str:
    """Return the smallest recognizable visual kernel, not a full protagonist description."""

    raw_parts = [
        getattr(anchor_profile, "name", ""),
        getattr(anchor_profile, "visual_summary", ""),
        *_read_sequence(getattr(anchor_profile, "identity_lock", ())),
        *_read_sequence(getattr(anchor_profile, "minimal_traits", ())),
        *_read_sequence(getattr(anchor_profile, "identity_anchors", ())),
    ]
    raw = "，".join(str(part or "").strip() for part in raw_parts if str(part or "").strip())
    if "兔" in raw:
        return "蓝领结白兔轮廓"
    if "麻雀" in raw:
        return "红嘴小麻雀轮廓"
    return "频道识别轮廓"


def infer_scene_anchor_affordances(
    *,
    base_prompt: str,
    main_subjects: Sequence[str] = (),
    key_props: Sequence[str] = (),
) -> SceneAnchorAffordances:
    """Infer physical in-scene carriers before any prompt is projected to an image model."""

    text = " ".join([str(base_prompt or ""), " ".join(str(item or "") for item in key_props)])
    carriers: list[str] = []
    notes: list[str] = []

    for prop in key_props:
        prop_text = str(prop or "").strip()
        if prop_text and not _looks_like_canvas_only_support(prop_text):
            carriers.append(f"{prop_text}的表面或附属小物件")

    if _has_any(text, ("书页", "书本", "打开的书", "书", "阅读", "纸页")):
        carriers.extend(("打开的书页纸面", "书封内侧藏书票", "夹在书页里的书签"))
    if _has_any(text, ("地图", "迷宫", "图表", "示意图", "卷轴")):
        carriers.extend(("地图图例栏", "纸面边栏纹章", "卷轴纸面压印"))
    if _has_any(text, ("卡片", "文件", "档案", "信件", "笔记", "便签")):
        carriers.extend(("纸张抬头纹章", "文件夹封面压印", "卡片纸面印记"))
    if _has_any(text, ("讲解板", "黑板", "白板", "板书")):
        carriers.extend(("讲解板板面装饰纹章", "黑板木框雕刻", "白板磁贴小物件"))
    if _has_any(text, ("桌", "桌面", "书桌", "办公桌", "茶几")):
        carriers.extend(("桌面上的书签", "桌面上的低存在感小徽章", "桌面木纹浅雕刻"))
    if _has_any(text, ("墙", "墙面", "壁画", "相框", "海报")):
        carriers.extend(("墙面壁画细节", "相框边框雕刻", "海报纸面纹章"))
    if _has_any(text, ("城市", "街道", "广场", "高楼", "店铺", "路牌", "招牌")):
        carriers.extend(("街道路牌图案", "背景墙面涂鸦", "店铺招牌的装饰纹章"))
    if _has_any(text, ("电视", "屏幕", "显示器")):
        carriers.extend(("电视柜上的小摆件", "屏幕内容中的道具表面纹章", "画面内海报纸面图案"))
    if _has_any(text, ("衣服", "制服", "外套", "书包", "帽子")) and not _has_named_source_subject(main_subjects):
        carriers.extend(("衣物刺绣小徽章", "背包挂件"))

    carriers = _dedupe(carriers)
    if not carriers and main_subjects:
        notes.append("本帧已有明确主体但缺少自然载体，允许视觉签名不出现")
    elif not carriers:
        notes.append("缺少明确实物载体时，优先隐藏而不是追加角标")

    forbidden_zones = (
        "画布四角",
        "画面边缘悬浮层",
        "UI层、水印层、logo层",
        "主体脸部、胸前关键标志和主要动作区域",
    )
    notes.append("视觉签名必须绑定真实场景物体；没有载体时隐藏")
    return SceneAnchorAffordances(
        carriers=tuple(carriers),
        forbidden_zones=forbidden_zones,
        notes=tuple(_dedupe(notes)),
    )


def is_scene_bound_anchor_candidate(
    *,
    image_prompt_clause: str,
    support_anchor: str,
    placement: str = "",
    contact_relation: str = "",
    carrier_type: Any = "",
    policy: VisualSignaturePolicy | None = None,
) -> bool:
    """Hard gate for visible anchor candidates.

    A visible signature must be physically attached to an in-world carrier. Canvas overlays,
    stickers, watermarks, corner bugs, and unsupported floating marks fail closed.
    """

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
    if not _has_any(combined, IN_WORLD_CARRIER_TERMS):
        return False
    if _has_any(combined, ("漂浮", "悬浮", "浮在", "floating")):
        return False
    if not _has_any(combined, MATERIAL_BINDING_TERMS):
        return False
    return True


def contains_forbidden_overlay_language(
    text: str,
    *,
    policy: VisualSignaturePolicy | None = None,
) -> bool:
    value = str(text or "")
    local_terms = CANVAS_OVERLAY_TERMS
    if _has_any(value, local_terms):
        return True
    if policy is None:
        policy = load_visual_signature_policy()
    return policy.contains_forbidden_overlay_text(value)


def sanitize_provider_anchor_clause(text: str) -> str:
    """Remove internal planning terms from an already validated image-facing clause."""

    cleaned = " ".join(str(text or "").split())
    for term in ANCHOR_INTERNAL_TERMS:
        cleaned = cleaned.replace(term, "")
    return " ".join(cleaned.split()).strip()


def _looks_like_canvas_only_support(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if _has_any(text, IN_WORLD_CARRIER_TERMS):
        return False
    return any(term.lower() == lowered or term in text for term in CANVAS_ONLY_SUPPORT_TERMS)


def _has_named_source_subject(main_subjects: Sequence[str]) -> bool:
    text = " ".join(str(subject or "") for subject in main_subjects)
    return _has_any(text, ("奥特曼", "超人", "Superman", "Ultraman", "名人", "历史人物", "角色"))


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
    "SceneAnchorAffordances",
    "anchor_identity_from_profile",
    "contains_forbidden_overlay_language",
    "infer_scene_anchor_affordances",
    "is_scene_bound_anchor_candidate",
    "sanitize_provider_anchor_clause",
]
