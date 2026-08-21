from __future__ import annotations

from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.services.series_visual_signature_prompt_presence import (
    normalize_prompt_text,
    prompt_contains_term,
    remove_prompt_term,
)

_NON_DESCRIPTIVE_REMAINDERS = frozenset(
    {
        "a",
        "an",
        "the",
        "one",
        "a dog",
        "the dog",
        "dog",
        "一只",
        "一个",
        "一位",
        "一种",
    }
)


def rendered_identity_traits(
    profile: VisualSignatureProfileSnapshot,
) -> tuple[str, ...]:
    """Return visible traits without repeating the rendered entity name."""

    display_name = normalize_prompt_text(profile.display_name)
    seen = {display_name.casefold()}
    result: list[str] = []
    for raw_trait in profile.identity_traits:
        trait = normalize_prompt_text(raw_trait)
        if not trait:
            continue
        rendered = _remove_display_name(trait, display_name)
        key = rendered.casefold()
        if (
            not rendered
            or key in seen
            or key in _NON_DESCRIPTIVE_REMAINDERS
        ):
            continue
        seen.add(key)
        result.append(rendered)
    return tuple(
        trait
        for trait in result
        if not any(
            other.casefold() != trait.casefold()
            and len(other) > len(trait)
            and prompt_contains_term(other, trait)
            for other in result
        )
    )


def rendered_identity_terms(
    profile: VisualSignatureProfileSnapshot,
) -> tuple[str, ...]:
    return (normalize_prompt_text(profile.display_name), *rendered_identity_traits(profile))


def rendered_identity_clause(profile: VisualSignatureProfileSnapshot) -> str:
    """Build one provider-facing mention while preserving stored profile hashes."""

    display_name, *traits = rendered_identity_terms(profile)
    clause = f"The single recurring identity is {display_name}"
    if traits:
        clause += ", visibly defined by " + ", ".join(traits)
    return clause


def _remove_display_name(trait: str, display_name: str) -> str:
    if trait.casefold() == display_name.casefold():
        return ""
    rendered = remove_prompt_term(trait, display_name)
    return " ".join(rendered.strip(" ,.;:，。；：+-").split())


__all__ = [
    "rendered_identity_clause",
    "rendered_identity_terms",
    "rendered_identity_traits",
]
