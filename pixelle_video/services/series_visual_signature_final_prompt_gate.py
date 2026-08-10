from __future__ import annotations

from collections.abc import Sequence

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract
from pixelle_video.services.series_visual_signature_prompt_presence import (
    normalize_prompt_text,
    prompt_contains_term,
)


class SeriesVisualSignatureFinalPromptGateError(ValueError):
    """Raised when a compiled provider prompt loses protected visual semantics."""


def assert_series_visual_signature_final_prompt(
    *,
    positive_prompt: str,
    negative_prompt: str,
    required_subjects: Sequence[str],
    signature: SeriesVisualSignatureContract,
    visible_text_policy: str,
) -> None:
    positive = normalize_prompt_text(positive_prompt)
    negative = normalize_prompt_text(negative_prompt).lower()
    if not positive:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final visual prompt gate failed: positive prompt is empty"
        )

    for subject_index, subject in enumerate(required_subjects):
        token = normalize_prompt_text(subject)
        if token and not prompt_contains_term(positive, token):
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: required subject missing from positive prompt "
                f"at index {subject_index}"
            )

    if signature.enabled:
        profile = signature.profile
        if profile is None:
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: enabled signature has no profile"
            )
        if not prompt_contains_term(positive, profile.display_name):
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: visual signature display name missing"
            )
        for trait_index, trait in enumerate(profile.identity_traits):
            if not prompt_contains_term(positive, trait):
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: visual signature identity trait missing "
                    f"at index {trait_index}"
                )
        for forbidden in ("sticker", "logo", "watermark"):
            if forbidden not in negative:
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: visual signature negative protection missing: "
                    f"{forbidden}"
                )
        if "duplicate recurring visual signature" not in negative:
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: duplicate visual signature protection missing"
            )

    if str(visible_text_policy or "").strip() == "no_visible_text":
        if "readable text" not in negative:
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: no-visible-text negative protection missing"
            )


__all__ = [
    "SeriesVisualSignatureFinalPromptGateError",
    "assert_series_visual_signature_final_prompt",
]