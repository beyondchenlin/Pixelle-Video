from __future__ import annotations

import re
from collections.abc import Sequence

from pixelle_video.models.mandatory_content_bound_visual_anchor import (
    MandatoryContentBoundVisualAnchorContract,
)
from pixelle_video.models.series_visual_signature import (
    FORBIDDEN_TEXT_CHARACTER_ROLES,
    SeriesVisualSignatureContract,
)
from pixelle_video.models.visual_entity_placement import (
    VisualEntityPlacement,
    VisualEntitySceneFusion,
    VisualSceneType,
)
from pixelle_video.services.series_visual_signature_prompt_presence import (
    normalize_prompt_text,
    prompt_contains_term,
    prompt_term_count,
)
from pixelle_video.services.series_visual_signature_rendering import (
    rendered_identity_terms,
    rendered_provider_action_verb,
    rendered_provider_participation_text,
)


class SeriesVisualSignatureFinalPromptGateError(ValueError):
    """Raised when a compiled provider prompt loses protected visual semantics."""


_DUPLICATE_IDENTITY_POSITIVE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:copy|clone|reflection|reflected copy|mirror image|poster|statue|toy)\s+of\s+(?:the\s+)?(?:same|recurring)\s+identity\b",
        r"\b(?:second|another|duplicate|duplicated|cloned|reflected|mirrored)\s+(?:copy\s+of\s+)?(?:the\s+)?(?:same|recurring)\s+identity\b",
        r"\b(?:two|multiple|several|a pair of)\s+(?:the\s+)?(?:same|recurring)\s+identit(?:y|ies)\b",
        r"\b(?:same|recurring)\s+identity\b.{0,64}\b(?:appears|is shown|is visible|is depicted)\s+(?:again|twice)\b",
    )
)


def assert_series_visual_signature_final_prompt(
    *,
    positive_prompt: str,
    negative_prompt: str,
    required_subjects: Sequence[str],
    signature: SeriesVisualSignatureContract,
    visible_text_policy: str,
    placement: VisualEntityPlacement | None = None,
    scene_fusion: VisualEntitySceneFusion | None = None,
    frame_id: str = "",
) -> None:
    positive = normalize_prompt_text(positive_prompt)
    negative = normalize_prompt_text(negative_prompt).lower()
    if not positive:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final visual prompt gate failed: positive prompt is empty"
        )
    if len(positive_prompt) > 1200:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final visual prompt gate failed: positive prompt exceeds 1200 characters"
        )
    if len(negative_prompt) > 800:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final visual prompt gate failed: negative prompt exceeds 800 characters"
        )

    for subject_index, subject in enumerate(required_subjects):
        token = normalize_prompt_text(subject)
        if token and not prompt_contains_term(positive, token):
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: required subject missing from positive prompt "
                f"at index {subject_index}"
            )

    if signature.enabled:
        resolved_frame_id = str(frame_id or getattr(placement, "frame_id", "unknown"))
        if signature.role in FORBIDDEN_TEXT_CHARACTER_ROLES:
            raise SeriesVisualSignatureFinalPromptGateError(
                f"frame {resolved_frame_id}: series_visual_signature.role is incompatible with a text character"
            )
        profile = signature.profile
        if profile is None:
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: enabled signature has no profile"
            )
        _assert_no_duplicate_identity_semantics(positive, profile.display_name)
        for term_index, term in enumerate(rendered_identity_terms(profile)):
            count = prompt_term_count(positive, term)
            if count == 0:
                if term_index == 0:
                    raise SeriesVisualSignatureFinalPromptGateError(
                        "final visual prompt gate failed: visual signature display name missing"
                    )
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: visual signature identity trait missing "
                    f"at index {term_index - 1}"
                )
            if count != 1:
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: rendered visual identity fact must "
                    f"appear exactly once at index {term_index}"
                )
        for required_control in (
            "Exactly one recurring identity exists in the whole frame",
            "one body",
            "one head",
            "one location",
            "visually subordinate to the main content",
        ):
            if not prompt_contains_term(positive, required_control):
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: positive single-instance control missing"
                )
        if not prompt_contains_term(positive, signature.role.value):
            raise SeriesVisualSignatureFinalPromptGateError(
                f"frame {resolved_frame_id}: series_visual_signature.role missing from positive prompt"
            )
        if placement is None:
            raise SeriesVisualSignatureFinalPromptGateError(
                f"frame {resolved_frame_id}: entity_placement is missing"
            )
        if scene_fusion is None:
            raise SeriesVisualSignatureFinalPromptGateError(
                f"frame {resolved_frame_id}: scene_fusion is missing"
            )
        placement_terms = (
            "Same identity:",
            placement.horizontal_position.value,
            placement.depth_position.value,
            placement.relative_size.value.replace("_", "-"),
            placement.relation_target,
            placement.spatial_relation,
            placement.support_relation,
            placement.action,
            placement.orientation,
            placement.visible_extent.value.replace("_", "-"),
        )
        for field_index, term in enumerate(placement_terms):
            if not prompt_contains_term(positive, term):
                raise SeriesVisualSignatureFinalPromptGateError(
                    f"frame {resolved_frame_id}: entity_placement prompt fact missing at index {field_index}"
                )
        if not prompt_contains_term(positive, "defining traits visible"):
            raise SeriesVisualSignatureFinalPromptGateError(
                f"frame {resolved_frame_id}: entity_placement visible-trait control "
                "missing from positive prompt"
            )
        if scene_fusion.scene_type is VisualSceneType.PHYSICAL_SCENE:
            for field_path in (
                "occlusion_relation",
                "perspective_relation",
                "contact_relation",
                "lighting_relation",
                "shadow_relation",
                "style_relation",
            ):
                fact = getattr(scene_fusion, field_path)
                if not prompt_contains_term(positive, fact):
                    raise SeriesVisualSignatureFinalPromptGateError(
                        f"frame {resolved_frame_id}: scene_fusion.{field_path} missing from positive prompt"
                    )
        else:
            if "not_applicable" in positive.casefold():
                raise SeriesVisualSignatureFinalPromptGateError(
                    f"frame {resolved_frame_id}: abstract scene positive prompt exposes not_applicable"
                )
            for field_path in ("occlusion_relation", "style_relation"):
                fact = getattr(scene_fusion, field_path)
                if not prompt_contains_term(positive, fact):
                    raise SeriesVisualSignatureFinalPromptGateError(
                        f"frame {resolved_frame_id}: scene_fusion.{field_path} missing from positive prompt"
                    )
            for physical_token in ("contact shadow", "ground plane", "feet on"):
                if physical_token in positive.casefold():
                    raise SeriesVisualSignatureFinalPromptGateError(
                        f"frame {resolved_frame_id}: abstract scene positive prompt contains "
                        f"physical-only fact: {physical_token}"
                    )

        for forbidden in (
            "sticker",
            "corner badge",
            "logo",
            "watermark",
            "floating",
            "mismatched style",
            "centered or oversized",
            "unrelated display platform",
        ):
            if forbidden not in negative:
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: visual signature negative protection missing: "
                    f"{forbidden}"
                )
        if "duplicate recurring visual signature" not in negative:
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: duplicate visual signature protection missing"
            )
        for forbidden_index, forbidden_trait in enumerate(profile.forbidden_traits):
            if not prompt_contains_term(negative, forbidden_trait):
                raise SeriesVisualSignatureFinalPromptGateError(
                    "final visual prompt gate failed: configured forbidden identity trait missing "
                    f"at index {forbidden_index}"
                )
        for composition_index, forbidden_composition in enumerate(
            scene_fusion.forbidden_compositions
        ):
            if not prompt_contains_term(negative, forbidden_composition):
                raise SeriesVisualSignatureFinalPromptGateError(
                    f"frame {resolved_frame_id}: scene_fusion.forbidden_compositions "
                    f"missing from negative prompt at index {composition_index}"
                )

    if str(visible_text_policy or "").strip() == "no_visible_text":
        if "readable text" not in negative:
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: no-visible-text negative protection missing"
            )


def assert_mandatory_content_bound_final_prompt(
    *,
    positive_prompt: str,
    negative_prompt: str,
    contract: MandatoryContentBoundVisualAnchorContract,
    main_content_chars: int,
    identity_chars: int,
) -> None:
    positive = normalize_prompt_text(positive_prompt)
    if not positive:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final V4.6 visual prompt gate failed: positive prompt is empty"
        )
    if len(positive_prompt) > 800:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final V4.6 visual prompt gate failed: positive prompt exceeds 800 characters"
        )
    if len(negative_prompt) > 800:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final V4.6 visual prompt gate failed: negative prompt exceeds 800 characters"
        )
    if main_content_chars / len(positive_prompt) < 0.35:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final V4.6 visual prompt gate failed: main content ratio is below 35 percent "
            f"({main_content_chars}/{len(positive_prompt)})"
        )
    if identity_chars / len(positive_prompt) > 0.30:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final V4.6 visual prompt gate failed: identity ratio exceeds 30 percent"
        )
    for index, subject in enumerate(contract.required_subjects):
        if not prompt_contains_term(positive, subject.label):
            raise SeriesVisualSignatureFinalPromptGateError(
                "final V4.6 visual prompt gate failed: required subject missing "
                f"at index {index}"
            )
    profile = contract.identity_contract.profile
    if profile is None:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final V4.6 visual prompt gate failed: identity profile is missing"
        )
    _assert_no_duplicate_identity_semantics(positive, profile.display_name)
    for index, term in enumerate(rendered_identity_terms(profile)):
        if prompt_term_count(positive, term) != 1:
            raise SeriesVisualSignatureFinalPromptGateError(
                "final V4.6 visual prompt gate failed: identity fact must appear exactly once "
                f"at index {index}"
            )
    plan = contract.participation_plan
    provider_action_verb = rendered_provider_action_verb(
        plan.action_verb,
        participation_mechanism=plan.participation_mechanism,
    )
    for field_name, value in (
        ("action_verb", provider_action_verb),
        ("interaction_target", plan.interaction_target),
        (
            "action_result",
            rendered_provider_participation_text(
                plan.action_result,
                action_verb=plan.action_verb,
                provider_action_verb=provider_action_verb,
            ),
        ),
    ):
        if not prompt_contains_term(positive, value):
            raise SeriesVisualSignatureFinalPromptGateError(
                f"final V4.6 visual prompt gate failed: {field_name} is missing"
            )
    forbidden_tokens = {
        "silent_witness",
        "midground",
        "foreground",
        "background",
        "medium_small",
        "full_body",
        "half_body",
        "not_applicable",
        "content_bound_ip_presence_plan",
        "series_visual_signature",
        "entity_placement",
        "scene_fusion",
    }
    leaked = sorted(token for token in forbidden_tokens if token in positive.casefold())
    if leaked:
        raise SeriesVisualSignatureFinalPromptGateError(
            "final V4.6 visual prompt gate failed: internal control token leaked: "
            + ", ".join(leaked)
        )


def _assert_no_duplicate_identity_semantics(
    positive_prompt: str,
    display_name: str,
) -> None:
    for pattern in _DUPLICATE_IDENTITY_POSITIVE_PATTERNS:
        if pattern.search(positive_prompt):
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: positive prompt introduces duplicate identity semantics"
            )

    normalized_name = normalize_prompt_text(display_name)
    if not normalized_name:
        return
    escaped_name = re.escape(normalized_name)
    quantified_name = re.compile(
        rf"\b(?:two|multiple|several|a pair of|second|another|duplicate|duplicated|cloned|reflected|mirrored)\s+(?:identical\s+)?{escaped_name}(?:s)?\b",
        re.IGNORECASE,
    )
    if quantified_name.search(positive_prompt):
        raise SeriesVisualSignatureFinalPromptGateError(
            "final visual prompt gate failed: positive prompt quantifies the recurring identity as multiple instances"
        )


__all__ = [
    "SeriesVisualSignatureFinalPromptGateError",
    "assert_series_visual_signature_final_prompt",
    "assert_mandatory_content_bound_final_prompt",
]
