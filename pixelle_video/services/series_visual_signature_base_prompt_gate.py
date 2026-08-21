from __future__ import annotations

from collections.abc import Sequence

from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.services.series_visual_signature_prompt_presence import (
    normalize_prompt_text,
    prompt_contains_term,
)
from pixelle_video.services.series_visual_signature_rendering import (
    rendered_identity_terms,
)


class SeriesVisualSignatureBasePromptGateError(ValueError):
    """Raised when content-only prompt generation leaks recurring identity facts."""


def assert_series_visual_signature_base_prompt_is_identity_isolated(
    *,
    base_prompt: str,
    required_subjects: Sequence[str],
    profile: VisualSignatureProfileSnapshot,
) -> None:
    """Enforce single ownership of recurring identity at the projection boundary.

    The base prompt and structured source-subject contract belong to article
    content. Recurring identity belongs to deterministic V4.5 projection. Any
    overlap is ambiguous and would let a provider interpret two mentions as two
    instances, so the frame fails closed instead of publishing a duplicate-prone
    prompt.
    """

    protected_terms = _dedupe_terms(
        (*profile.identity_traits, *rendered_identity_terms(profile))
    )
    sources = (base_prompt, *required_subjects)
    for source_index, source in enumerate(sources):
        for term_index, term in enumerate(protected_terms):
            if prompt_contains_term(source, term):
                raise SeriesVisualSignatureBasePromptGateError(
                    "signature-free base prompt gate failed: recurring identity fact "
                    f"found in content source {source_index} at protected term {term_index}"
                )


def _dedupe_terms(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_prompt_text(value)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


__all__ = [
    "SeriesVisualSignatureBasePromptGateError",
    "assert_series_visual_signature_base_prompt_is_identity_isolated",
]
