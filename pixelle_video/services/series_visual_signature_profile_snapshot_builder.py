from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.series_visual_signature import (
    MAX_TRAIT_CHARS,
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile

_IDENTITY_TRAIT_FIELDS = (
    "identity_lock",
    "minimal_traits",
    "identity_anchors",
)
_INSTRUCTION_LIKE_IDENTITY_TERMS = (
    "ignore previous",
    "ignore all",
    "system message",
    "system prompt",
    "assistant message",
    "user message",
    "developer message",
    "follow these instructions",
    "follow my instructions",
    "must render",
    "must show",
    "must include",
    "should render",
    "should show",
    "do not follow",
    "override instructions",
    "jailbreak",
    "忽略之前",
    "忽略以上",
    "忽略所有",
    "系统消息",
    "系统提示",
    "助手消息",
    "用户消息",
    "开发者消息",
    "遵循这些指令",
    "遵循我的指令",
    "必须渲染",
    "必须显示",
    "必须包含",
    "应该渲染",
    "应该显示",
    "不要遵循",
    "覆盖指令",
    "越狱",
)


class SeriesVisualSignatureProfileSnapshotBuilder:
    """Build the canonical runtime profile without inventing identity facts.

    The Asset Bible/IPProfile remains the persisted source. This builder only
    selects explicit identity fields and never derives identity from a profile id,
    display name, world hint, style hint, or free-form prompt paragraph.
    """

    def build(
        self,
        *,
        request: SeriesVisualSignatureRequest,
        ip_profile: Any = None,
        legacy_profile: SeriesVisualSignatureProfile | None = None,
    ) -> VisualSignatureProfileSnapshot:
        if not request.enabled:
            raise ValueError(
                "disabled series visual signature does not require a profile snapshot"
            )
        if request.profile_id is None:
            raise ValueError("enabled series visual signature requires profile_id")

        if legacy_profile is not None:
            return self._from_legacy_profile(request, legacy_profile)
        if ip_profile is not None:
            return self._from_ip_profile(request, ip_profile)
        raise ValueError(
            "enabled series visual signature requires a resolved Asset Bible IPProfile"
        )

    def _from_ip_profile(
        self,
        request: SeriesVisualSignatureRequest,
        ip_profile: Any,
    ) -> VisualSignatureProfileSnapshot:
        profile_id = _text(_read_field(ip_profile, "series_visual_signature_profile_id"))
        if profile_id != request.profile_id:
            raise ValueError("resolved IPProfile does not match request profile_id")

        display_name = validate_series_visual_signature_identity_name(
            _read_field(ip_profile, "name")
        )
        identity_traits = select_series_visual_signature_identity_traits(ip_profile)
        if not identity_traits:
            raise ValueError(
                "resolved IPProfile must provide explicit identity_lock, minimal_traits, "
                "or identity_anchors; identity cannot be inferred from prose"
            )

        forbidden_traits = _safe_forbidden_traits(
            _read_field(ip_profile, "forbidden_elements"),
        )
        source_asset_ids = _source_asset_ids(_read_field(ip_profile, "metadata"))
        return VisualSignatureProfileSnapshot(
            profile_id=profile_id,
            display_name=display_name,
            identity_traits=identity_traits,
            style_safe_traits=(),
            forbidden_traits=forbidden_traits,
            source_asset_ids=source_asset_ids,
        )

    def _from_legacy_profile(
        self,
        request: SeriesVisualSignatureRequest,
        profile: SeriesVisualSignatureProfile,
    ) -> VisualSignatureProfileSnapshot:
        if profile.profile_id != request.profile_id:
            raise ValueError(
                "resolved SeriesVisualSignatureProfile does not match request profile_id"
            )
        display_name = validate_series_visual_signature_identity_name(profile.display_name)
        identity_traits = validate_series_visual_signature_identity_traits(
            profile.identity_contract.required_identity_traits
            or profile.identity_kernel
        )
        if not identity_traits:
            raise ValueError("resolved legacy profile has no explicit identity traits")
        return VisualSignatureProfileSnapshot(
            profile_id=profile.profile_id,
            display_name=display_name,
            identity_traits=identity_traits,
            style_safe_traits=(),
            forbidden_traits=(),
            source_asset_ids=tuple(profile.reference_assets),
        )


def validate_series_visual_signature_identity_name(value: Any) -> str:
    text = _validated_identity_phrase(
        value,
        field_label="visual signature display name",
    )
    if not text:
        raise ValueError("resolved IPProfile must provide a display name")
    return text


def select_series_visual_signature_identity_traits(source: Any) -> tuple[str, ...]:
    for field_name in _IDENTITY_TRAIT_FIELDS:
        values = _read_field(source, field_name)
        if _has_non_empty_text(values):
            return validate_series_visual_signature_identity_traits(values)
    return ()


def validate_series_visual_signature_identity_traits(
    values: Any,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(_sequence(values)):
        text = _validated_identity_phrase(
            value,
            field_label=f"visual signature identity trait at index {index}",
        )
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _validated_identity_phrase(value: Any, *, field_label: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "\n" in raw or "\r" in raw or ";" in raw or "；" in raw:
        raise ValueError(
            f"{field_label} must be a short visual noun phrase without line breaks or instructions"
        )
    text = _text(raw)
    if len(text) > MAX_TRAIT_CHARS:
        raise ValueError(
            f"{field_label} exceeds {MAX_TRAIT_CHARS} characters"
        )
    lowered = text.casefold()
    if any(term.casefold() in lowered for term in _INSTRUCTION_LIKE_IDENTITY_TERMS):
        raise ValueError(
            f"{field_label} must be a visual noun phrase, not model instructions"
        )
    return text


def _has_non_empty_text(value: Any) -> bool:
    return any(str(item or "").strip() for item in _sequence(value))


def _safe_forbidden_traits(values: Any) -> tuple[str, ...]:
    """Keep short appearance nouns only; instruction-like negatives stay upstream."""

    result: list[str] = []
    for value in _sequence(values):
        text = _text(value)
        if not text or len(text) > MAX_TRAIT_CHARS:
            continue
        lowered = text.casefold()
        if any(
            token in lowered
            for token in (
                "do ",
                "don't",
                "must ",
                "should ",
                "never ",
                "always ",
                "prompt",
                "instruction",
                "system message",
            )
        ):
            continue
        result.append(text)
    return _dedupe(result)


def _source_asset_ids(metadata: Any) -> tuple[str, ...]:
    if not isinstance(metadata, Mapping):
        return ()
    for key in ("source_asset_ids", "reference_asset_ids", "reference_assets"):
        value = metadata.get(key)
        result = _dedupe(value)
        if result:
            return result
    return ()


def _read_field(source: Any, field_name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(field_name)
    return getattr(source, field_name, None)


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _dedupe(value: Any) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in _sequence(value):
        text = _text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


__all__ = [
    "SeriesVisualSignatureProfileSnapshotBuilder",
    "select_series_visual_signature_identity_traits",
    "validate_series_visual_signature_identity_name",
    "validate_series_visual_signature_identity_traits",
]
