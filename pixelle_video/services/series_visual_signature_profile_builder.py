from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.services.series_visual_signature_identity_contract_builder import (
    SeriesVisualSignatureIdentityContractBuilder,
)


class SeriesVisualSignatureProfileError(ValueError):
    pass


_DEFAULT_FORBIDDEN_ROLE_FORMS = (
    "角标",
    "水印",
    "贴纸",
    "logo",
    "corner badge",
    "watermark",
    "sticker",
    "overlay",
    "UI overlay",
    "floating icon",
    "无意义装饰",
)
_SUPPORTING_ROLE_AFFORDANCES = (
    "讲解者",
    "观察者",
    "导览者",
    "操作员",
    "展板图像",
    "投影图像",
    "桌面摆件",
    "墙面照片",
    "商品演示者",
    "信息图指示物",
    "环境品牌装置",
)


@dataclass(frozen=True)
class SeriesVisualSignatureProfileBuilder:
    def build(self, ip_profile: IPProfile | None) -> SeriesVisualSignatureProfile:
        if ip_profile is None:
            raise SeriesVisualSignatureProfileError("IPProfile is required to build SeriesVisualSignatureProfile")

        identity_kernel = _identity_kernel(ip_profile)
        if not identity_kernel:
            raise SeriesVisualSignatureProfileError("identity kernel is required")

        ip_kind = _infer_ip_kind(ip_profile)
        identity_contract = SeriesVisualSignatureIdentityContractBuilder().build(ip_profile)
        return SeriesVisualSignatureProfile(
            profile_id=ip_profile.series_visual_signature_profile_id,
            display_name=ip_profile.name,
            identity_kernel=identity_kernel,
            appearance_traits=_appearance_traits(ip_profile),
            action_affordances=_action_affordances(ip_profile, ip_kind=ip_kind),
            primary_role_affordances=_primary_role_affordances(ip_profile, ip_kind=ip_kind),
            supporting_role_affordances=_supporting_role_affordances(ip_profile),
            forbidden_role_forms=_forbidden_role_forms(ip_profile),
            reference_assets=_reference_assets(ip_profile),
            identity_contract=identity_contract,
            metadata={
                "source": "IPProfile",
                "ip_type": ip_profile.ip_type,
                "inferred_ip_kind": ip_kind,
                "builder_version": "series_visual_signature_profile_builder.v4_2",
            },
            version="series_visual_signature_profile.v4_2",
        )


def _identity_kernel(ip_profile: IPProfile) -> tuple[str, ...]:
    values: list[str] = []
    for name in (
        "identity_lock",
        "minimal_traits",
        "identity_anchors",
        "name",
        "visual_summary",
        "style_hint",
        "world_hint",
        "logline",
    ):
        _extend(values, getattr(ip_profile, name, None))
    tokens: list[str] = []
    for value in values:
        tokens.extend(_tokens(value))
    return tuple(_dedupe(tokens))


def _appearance_traits(ip_profile: IPProfile) -> tuple[str, ...]:
    values: list[str] = []
    for name in ("visual_summary", "minimal_traits", "identity_anchors", "style_hint"):
        _extend(values, getattr(ip_profile, name, None))
    return tuple(_dedupe(values)) or _identity_kernel(ip_profile)


def _action_affordances(ip_profile: IPProfile, *, ip_kind: str) -> tuple[str, ...]:
    explicit = _collect_from_metadata(ip_profile, "action_affordances")
    if explicit:
        return tuple(explicit)
    if ip_kind == "human":
        return ("讲解", "观察", "引导", "演示", "操作")
    if ip_kind == "animal":
        return ("观察", "引导", "互动", "搬运", "指示")
    if ip_kind == "vehicle":
        return ("穿行", "运输", "引导视线", "作为场景中心运动物")
    if ip_kind == "object":
        return ("承载信息", "作为隐喻主体", "作为展品", "作为场景支点")
    return ("作为环境品牌装置", "作为展板图像", "作为投影图像", "作为信息图指示元素")


def _primary_role_affordances(ip_profile: IPProfile, *, ip_kind: str) -> tuple[str, ...]:
    explicit = _collect_from_metadata(ip_profile, "primary_role_affordances")
    if explicit:
        return tuple(explicit)
    if ip_kind == "human":
        return ("固定主持人", "人物主角", "讲解主角", "演示者")
    if ip_kind == "animal":
        return ("故事行动者", "角色主角", "导览者", "互动角色")
    if ip_kind == "vehicle":
        return ("运动主体", "交通主角", "任务执行者", "场景中心物")
    if ip_kind == "object":
        return ("隐喻主体", "展品主体", "信息承载主体", "场景支点")
    return ("视觉主角", "品牌化主体", "符号主体")


def _supporting_role_affordances(ip_profile: IPProfile) -> tuple[str, ...]:
    explicit = _collect_from_metadata(ip_profile, "supporting_role_affordances")
    return tuple(_dedupe([*explicit, *_SUPPORTING_ROLE_AFFORDANCES]))


def _forbidden_role_forms(ip_profile: IPProfile) -> tuple[str, ...]:
    values: list[str] = [*_DEFAULT_FORBIDDEN_ROLE_FORMS]
    _extend(values, ip_profile.forbidden_elements)
    _extend(values, ip_profile.identity_suppression_rules)
    _extend(values, ip_profile.negative_constraints)
    _extend(values, _collect_from_metadata(ip_profile, "forbidden_role_forms"))
    return tuple(_dedupe(values))


def _reference_assets(ip_profile: IPProfile) -> tuple[str, ...]:
    assets = _collect_from_metadata(ip_profile, "reference_assets")
    return tuple(_dedupe(assets))


def _infer_ip_kind(ip_profile: IPProfile) -> str:
    text = " ".join(
        str(value or "")
        for value in (
            ip_profile.ip_type,
            ip_profile.name,
            ip_profile.visual_summary,
            ip_profile.style_hint,
            ip_profile.world_hint,
            " ".join(ip_profile.identity_anchors),
            " ".join(ip_profile.minimal_traits),
        )
    ).lower()
    if any(token in text for token in ("human", "person", "host", "主持", "人物", "人类", "数字人")):
        return "human"
    if any(token in text for token in ("sparrow", "bird", "rabbit", "animal", "麻雀", "鸟", "兔", "动物", "吉祥物")):
        return "animal"
    if any(token in text for token in ("airplane", "plane", "vehicle", "飞机", "车辆", "汽车", "飞行器")):
        return "vehicle"
    if any(token in text for token in ("stone", "rock", "object", "石头", "岩石", "物件", "物体")):
        return "object"
    return "symbolic"


def _collect_from_metadata(ip_profile: IPProfile, key: str) -> list[str]:
    metadata = ip_profile.metadata or {}
    values: list[str] = []
    if isinstance(metadata, dict):
        _extend(values, metadata.get(key))
    return _dedupe(values)


def _extend(target: list[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if value.strip():
            target.append(value.strip())
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            _extend(target, item)
        return
    text = str(value).strip()
    if text:
        target.append(text)


_GENERIC = {"ip", "角色", "形象", "视觉", "签名", "视觉签名", "频道", "识别", "元素", "style", "identity", "visual", "signature", "character"}


def _tokens(text: str) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []
    result = [text] if 2 <= len(text) <= 80 else []
    for part in re.split(r"[\s,，。.;；:：/、|]+", text):
        cleaned = part.strip(" ，,。.;；:：()（）[]【】<>《》\"'")
        if len(cleaned) >= 2 and cleaned.lower() not in _GENERIC:
            result.append(cleaned)
    return _dedupe(result)


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


__all__ = ["SeriesVisualSignatureProfileBuilder", "SeriesVisualSignatureProfileError"]
