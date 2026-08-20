from __future__ import annotations

from collections.abc import Sequence

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
        if not prompt_contains_term(positive, profile.canonical_identity_clause):
            raise SeriesVisualSignatureFinalPromptGateError(
                "final visual prompt gate failed: canonical visual identity clause missing"
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
            "One;",
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
        visible_clause = "shows " + " + ".join(placement.visible_core_traits)
        if not prompt_contains_term(positive, visible_clause):
            raise SeriesVisualSignatureFinalPromptGateError(
                f"frame {resolved_frame_id}: entity_placement.visible_core_traits "
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


__all__ = [
    "SeriesVisualSignatureFinalPromptGateError",
    "assert_series_visual_signature_final_prompt",
]
