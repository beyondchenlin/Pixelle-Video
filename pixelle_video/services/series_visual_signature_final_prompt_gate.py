from __future__ import annotations

from collections.abc import Sequence

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract


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
    positive = " ".join(str(positive_prompt or "").split())
    negative = " ".join(str(negative_prompt or "").split()).lower()
    if not positive:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final visual prompt gate failed: positive prompt is empty"
        )

    for subject in required_subjects:
        token = " ".join(str(subject or "").strip().split())
        if token and token.casefold() not in positive.casefold():
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: required subject missing from positive prompt: "
                f"{token}"
            )

    if signature.enabled:
        profile = signature.profile
        if profile is None:
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: enabled signature has no profile"
            )
        if profile.display_name.casefold() not in positive.casefold():
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: visual signature display name missing"
            )
        for trait in profile.identity_traits[:3]:
            if trait.casefold() not in positive.casefold():
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: visual signature identity trait missing: "
                    f"{trait}"
                )
        for forbidden in ("sticker", "logo", "watermark"):
            if forbidden not in negative:
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: visual signature negative protection missing: "
                    f"{forbidden}"
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
