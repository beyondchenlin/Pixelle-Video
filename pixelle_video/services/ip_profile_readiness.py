from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    select_series_visual_signature_identity_traits,
    validate_series_visual_signature_identity_name,
)

IP_GENERATION_READINESS_ERROR = (
    "当前 IP 形象缺少身份锚点，无法接入正式 Z-Image 生成。"
    "请先在 IP 设计工作台补全 identity_lock、minimal_traits 或 identity_anchors。"
)
IP_GENERATION_IDENTITY_VALIDATION_ERROR = "当前 IP 形象未通过生成前身份安全校验"


def ensure_ip_profile_ready_for_generation(ip_profile: Any | None) -> None:
    if ip_profile is None:
        raise ValueError("ip_profile is required when series_visual_signature_enabled=True")

    try:
        validate_series_visual_signature_identity_name(_read_field(ip_profile, "name"))
        identity_terms = ip_generation_identity_terms(ip_profile)
    except ValueError as exc:
        raise ValueError(
            f"{IP_GENERATION_IDENTITY_VALIDATION_ERROR}: {exc}"
        ) from exc

    if not identity_terms:
        raise ValueError(IP_GENERATION_READINESS_ERROR)


def ip_generation_identity_terms(ip_profile: Any) -> tuple[str, ...]:
    return select_series_visual_signature_identity_traits(ip_profile)


def _read_field(source: Any, field_name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(field_name)
    return getattr(source, field_name, None)


__all__ = [
    "IP_GENERATION_IDENTITY_VALIDATION_ERROR",
    "IP_GENERATION_READINESS_ERROR",
    "ensure_ip_profile_ready_for_generation",
    "ip_generation_identity_terms",
]
