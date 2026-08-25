from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.services.reference_image_visual_context_adapter import (
    current_reference_image_visual_story_context_patch,
    merge_ip_profile_from_reference_patch,
)
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
    select_series_visual_signature_identity_traits,
    validate_series_visual_signature_identity_name,
)

IP_GENERATION_READINESS_ERROR = (
    "当前 IP 形象缺少身份锚点，无法接入正式 Z-Image 生成。"
    "请先在 IP 设计工作台补全 identity_lock、minimal_traits 或 identity_anchors。"
)
IP_GENERATION_IDENTITY_VALIDATION_ERROR = "当前 IP 形象未通过生成前身份安全校验"
IP_GENERATION_IDENTITY_CONTRACT_VALIDATION_ERROR = (
    "当前 IP 形象的固定身份、配色或授权文字合同无效"
)


def ensure_ip_profile_ready_for_generation(ip_profile: Any | None) -> Any:
    resolved_profile = merge_ip_profile_from_reference_patch(
        ip_profile,
        current_reference_image_visual_story_context_patch(),
    )
    resolved_profile = ensure_visual_signature_identity_ready(
        resolved_profile
    )

    profile_id = str(
        _read_field(resolved_profile, "series_visual_signature_profile_id") or ""
    ).strip()
    try:
        SeriesVisualSignatureProfileSnapshotBuilder().build(
            request=SeriesVisualSignatureRequest(
                enabled=True,
                profile_id=profile_id,
                asset_bible_id="generation-readiness",
            ),
            ip_profile=resolved_profile,
        )
    except ValueError as exc:
        raise ValueError(
            f"{IP_GENERATION_IDENTITY_CONTRACT_VALIDATION_ERROR}: {exc}"
        ) from exc
    return resolved_profile


def ensure_visual_signature_identity_ready(ip_profile: Any | None) -> Any:
    if ip_profile is None:
        raise ValueError("ip_profile is required when series_visual_signature_enabled=True")

    try:
        validate_series_visual_signature_identity_name(
            _read_field(ip_profile, "name")
        )
        identity_terms = ip_generation_identity_terms(ip_profile)
    except ValueError as exc:
        raise ValueError(
            f"{IP_GENERATION_IDENTITY_VALIDATION_ERROR}: {exc}"
        ) from exc

    if not identity_terms:
        raise ValueError(IP_GENERATION_READINESS_ERROR)
    return ip_profile


def ip_generation_identity_terms(ip_profile: Any) -> tuple[str, ...]:
    return select_series_visual_signature_identity_traits(ip_profile)


def _read_field(source: Any, field_name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(field_name)
    return getattr(source, field_name, None)


__all__ = [
    "IP_GENERATION_IDENTITY_VALIDATION_ERROR",
    "IP_GENERATION_READINESS_ERROR",
    "IP_GENERATION_IDENTITY_CONTRACT_VALIDATION_ERROR",
    "ensure_visual_signature_identity_ready",
    "ensure_ip_profile_ready_for_generation",
    "ip_generation_identity_terms",
]
