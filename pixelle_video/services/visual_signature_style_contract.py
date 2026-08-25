from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.visual_anchor_two_stage import VisualSignatureStyleContract

_RENDERING_STYLE_FRAGMENT = {
    "photorealistic_human": "photorealistic human rendering",
    "stylized_character": "stylized character rendering",
    "flat_illustration": "flat illustration rendering",
}
_MAX_PALETTE_NODES = 256
_MAX_PALETTE_DEPTH = 8
_PROFILE_INTRINSIC_STYLE_FALLBACK = (
    "preserve the visual signature's profile-defined design, silhouette, colors, "
    "and material identity while following the narrative-scene rendering style"
)
_EXCLUSIVE_VISUAL_LAYER_RULE = (
    "only the visual signature may use this profile-defined rendering style"
)


def build_visual_signature_style_contract(
    *,
    ip_profile: Any,
    expected_profile_id: str,
) -> VisualSignatureStyleContract:
    """Build the only runtime style contract from persisted IP style facts."""

    if ip_profile is None:
        raise ValueError(
            "enabled visual signature requires its source profile for independent style"
        )
    profile_id = str(
        _profile_value(ip_profile, "series_visual_signature_profile_id") or ""
    ).strip()
    if profile_id != expected_profile_id:
        raise ValueError("visual signature style profile must match the identity profile")

    style_hint = str(_profile_value(ip_profile, "style_hint") or "").strip()
    rendering_style = _enum_value(
        _profile_value(ip_profile, "rendering_style") or "style_inherited"
    )
    source_style_scope = _enum_value(
        _profile_value(ip_profile, "style_scope") or "ip_character_only"
    )
    color_fragments = _palette_prompt_fragments(
        _profile_value(ip_profile, "color_palette") or {}
    )
    style_fragments = _dedupe_fragments(
        [
            style_hint,
            _RENDERING_STYLE_FRAGMENT.get(rendering_style, ""),
            *color_fragments,
        ]
    )
    if not style_fragments:
        # Historical profiles keep their identity facts while inheriting the
        # current scene's rendering style.
        style_fragments = [_PROFILE_INTRINSIC_STYLE_FALLBACK]

    boundary_rules = _profile_text_fragments(
        _profile_value(ip_profile, "style_boundary_rules") or ()
    )
    if _profile_value(ip_profile, "exclusive_visual_layer") is True:
        boundary_rules = _dedupe_fragments(
            [*boundary_rules, _EXCLUSIVE_VISUAL_LAYER_RULE]
        )
    negative_fragments = _dedupe_fragments(
        [
            *_profile_text_fragments(
                _profile_value(ip_profile, "negative_constraints") or ()
            ),
            *_profile_text_fragments(
                _profile_value(ip_profile, "identity_suppression_rules") or ()
            ),
        ]
    )
    return VisualSignatureStyleContract(
        profile_id=profile_id,
        style_fragments=style_fragments,
        negative_fragments=negative_fragments,
        rendering_style=rendering_style,
        source_style_scope=source_style_scope,
        boundary_rules=boundary_rules,
    )


def _profile_value(source: Any, field_name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(field_name)
    return getattr(source, field_name, None)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return " ".join(str(raw or "").split())


def _profile_text_fragments(value: Any) -> list[str]:
    if isinstance(value, str):
        return _dedupe_fragments([value])
    if isinstance(value, Sequence):
        return _dedupe_fragments(
            [item for item in value if isinstance(item, str)]
        )
    return []


def _palette_prompt_fragments(value: Any) -> list[str]:
    fragments: list[str] = []
    pending: list[tuple[Any, int]] = [(value, 0)]
    visited_nodes = 0
    while pending:
        current, depth = pending.pop()
        visited_nodes += 1
        if visited_nodes > _MAX_PALETTE_NODES:
            raise ValueError("visual signature color palette is too large")
        if depth > _MAX_PALETTE_DEPTH:
            raise ValueError("visual signature color palette is nested too deeply")
        if isinstance(current, Mapping):
            prompt = current.get("prompt")
            if isinstance(prompt, str):
                fragments.append(prompt)
            pending.extend(
                (nested, depth + 1)
                for key, nested in reversed(list(current.items()))
                if key != "prompt"
            )
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes)
        ):
            pending.extend((nested, depth + 1) for nested in reversed(current))
    return _dedupe_fragments(fragments)


def _dedupe_fragments(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value or "").split())
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


__all__ = ["build_visual_signature_style_contract"]
