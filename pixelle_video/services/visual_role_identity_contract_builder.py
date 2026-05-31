from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.visual_role_identity import VisualRoleIdentityContract


_DEFAULT_FORBIDDEN_IDENTITY_LOSS_RULES = (
    "Do not turn the IP into a logo, watermark, sticker, corner badge, floating icon, or UI overlay.",
    "Do not hide, suppress, replace, or genericize the configured IP identity.",
)


@dataclass(frozen=True)
class VisualRoleIdentityContractBuilder:
    def build(self, ip_profile: IPProfile) -> VisualRoleIdentityContract:
        metadata = dict(ip_profile.metadata or {})
        required_values: list[tuple[str, str]] = []
        _extend_with_source(required_values, ip_profile.identity_lock, "identity_lock")
        _extend_with_source(required_values, ip_profile.minimal_traits, "minimal_traits")
        _extend_with_source(
            required_values,
            metadata.get("required_identity_traits"),
            "metadata.required_identity_traits",
        )
        _extend_with_source(
            required_values,
            metadata.get("identity_anchors_required"),
            "metadata.identity_anchors_required",
        )

        required_traits, required_sources = _dedupe_with_sources(required_values)
        if not required_traits:
            fallback_values: list[tuple[str, str]] = []
            _extend_with_source(fallback_values, ip_profile.identity_anchors, "identity_anchors")
            _extend_with_source(fallback_values, ip_profile.name, "name")
            _extend_with_source(fallback_values, ip_profile.visual_summary, "visual_summary")
            required_traits, required_sources = _dedupe_with_sources(fallback_values)

        important_traits = _dedupe(
            [
                *ip_profile.identity_anchors,
                *_sequence_from_metadata(metadata, "important_identity_traits"),
            ]
        )
        optional_appearance_traits = _dedupe(
            [
                *([ip_profile.visual_summary] if ip_profile.visual_summary else []),
                *([ip_profile.style_hint] if ip_profile.style_hint else []),
                *([ip_profile.world_hint] if ip_profile.world_hint else []),
                *ip_profile.role_presets,
                *_sequence_from_metadata(metadata, "optional_appearance_traits"),
            ]
        )
        forbidden_rules = _dedupe(
            [
                *_DEFAULT_FORBIDDEN_IDENTITY_LOSS_RULES,
                *ip_profile.forbidden_elements,
                *ip_profile.identity_suppression_rules,
                *ip_profile.negative_constraints,
                *_sequence_from_metadata(metadata, "forbidden_identity_loss_rules"),
                *_sequence_from_metadata(metadata, "forbidden_role_forms"),
            ]
        )
        reference_assets = _dedupe(_sequence_from_metadata(metadata, "reference_assets"))

        return VisualRoleIdentityContract(
            canonical_identity_name=ip_profile.name,
            required_identity_traits=tuple(required_traits),
            important_identity_traits=tuple(important_traits),
            optional_appearance_traits=tuple(optional_appearance_traits),
            forbidden_identity_loss_rules=tuple(forbidden_rules),
            reference_assets=tuple(reference_assets),
            metadata={
                "source": "IPProfile",
                "builder_version": "visual_role_identity_contract_builder.v4_2",
                "ip_profile_id": ip_profile.ip_profile_id,
                "required_trait_sources": required_sources,
            },
        )


def _extend_with_source(target: list[tuple[str, str]], value: Any, source: str) -> None:
    for text in _as_text_list(value):
        target.append((text, source))


def _sequence_from_metadata(metadata: Mapping[str, Any], key: str) -> list[str]:
    return _as_text_list(metadata.get(key))


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: list[str] = []
        for item in value:
            result.extend(_as_text_list(item))
        return result
    text = str(value).strip()
    return [text] if text else []


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


def _dedupe_with_sources(values: Sequence[tuple[str, str]]) -> tuple[list[str], dict[str, str]]:
    result: list[str] = []
    sources: dict[str, str] = {}
    seen: set[str] = set()
    for value, source in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        sources[text] = source
    return result, sources


__all__ = ["VisualRoleIdentityContractBuilder"]
