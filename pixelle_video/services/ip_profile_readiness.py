from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

IP_GENERATION_READINESS_ERROR = (
    "当前 IP 形象缺少身份锚点，无法接入正式 Z-Image 生成。"
    "请先在 IP 设计工作台补全 identity_lock 或 identity_anchors。"
)


def ensure_ip_profile_ready_for_generation(ip_profile: Any | None) -> None:
    if ip_profile is None:
        raise ValueError("ip_profile is required when series_visual_signature_enabled=True")
    if not ip_generation_identity_terms(ip_profile):
        raise ValueError(IP_GENERATION_READINESS_ERROR)


def ip_generation_identity_terms(ip_profile: Any) -> tuple[str, ...]:
    return _unique_text(
        [
            *_read_text_sequence(_read_field(ip_profile, "identity_lock")),
            *_read_text_sequence(_read_field(ip_profile, "identity_anchors")),
        ]
    )


def _read_field(source: Any, field_name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(field_name, ())
    return getattr(source, field_name, ())


def _read_text_sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, Iterable):
        return ()
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            items.append(cleaned)
    return tuple(items)


def _unique_text(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)
    return tuple(result)

