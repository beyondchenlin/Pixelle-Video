from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)
from pixelle_video.models.final_visual_prompt_bundle import FinalVisualPromptBundle
from pixelle_video.models.series_visual_signature import (
    SERIES_VISUAL_SIGNATURE_NATURAL_ROLE_MAP,
    SeriesVisualSignatureContract,
)
from pixelle_video.models.z_image_prompt_bundle import ZImagePromptBundle
from pixelle_video.services.series_visual_signature_final_prompt_gate import (
    assert_series_visual_signature_final_prompt,
)
from pixelle_video.services.visible_text_prompt_rewriter import (
    NO_VISIBLE_TEXT_NEGATIVE_PROMPT,
    rewrite_for_no_visible_text,
)

# Product-level semantic budget. Provider adapters may impose a stricter limit,
# but this compiler never truncates required subjects or identity semantics.
_MAX_POSITIVE_PROMPT_CHARS = 1200


class FinalVisualPromptCompiler:
    """Compile a provider- and media-neutral final visual prompt."""

    def compile(
        self,
        *,
        final_contract: Any,
        base_negative_prompt: str | None = None,
    ) -> FinalVisualPromptBundle:
        contract = _to_mapping(final_contract)
        reject_deprecated_signature_fields(contract, context="final contract")
        concretization = dict(contract.get("article_concretization") or {})
        anchor = dict(concretization.get("anchor") or {})
        diagram = dict(concretization.get("diagram") or {})
        render = dict(contract.get("diagram_render") or concretization.get("render") or {})
        signature = _signature_contract(final_contract, contract)
        required_subjects = _required_subjects(contract.get("required_subjects"))
        visible_text_policy = str(
            contract.get("visible_text_policy")
            or diagram.get("visible_text_policy")
            or "no_visible_text"
        )

        main_visual = _first_non_empty(
            diagram.get("visual_metaphor"),
            anchor.get("anchor_claim"),
            contract.get("visual_concretization_summary"),
            "one clear explanation visual",
        )
        if visible_text_policy == "no_visible_text":
            main_visual = rewrite_for_no_visible_text(main_visual)

        diagram_clause = _diagram_clause(diagram)
        required_subjects_clause = _required_subjects_clause(required_subjects)
        signature_clause = _signature_clause(signature)
        style_clause = _style_clause(render)
        positive_prompt = _compose_budgeted_prompt(
            main_visual=main_visual,
            diagram_clause=diagram_clause,
            required_subjects_clause=required_subjects_clause,
            signature_clause=signature_clause,
            style_clause=style_clause,
            limit=_MAX_POSITIVE_PROMPT_CHARS,
        )

        negative_parts = _split_negative_prompt(base_negative_prompt)
        if signature.enabled:
            negative_parts.extend(
                (
                    "recurring visual signature rendered as a photorealistic mascot",
                    "recurring visual signature rendered as a sticker overlay",
                    "recurring visual signature rendered as a logo overlay",
                    "recurring visual signature rendered as a watermark",
                    "duplicate recurring visual signature instances",
                )
            )
            if signature.profile is not None:
                negative_parts.extend(signature.profile.forbidden_traits)
        if visible_text_policy == "no_visible_text":
            negative_parts.append(NO_VISIBLE_TEXT_NEGATIVE_PROMPT)

        locked_constraints: list[str] = []
        if required_subjects:
            locked_constraints.append(
                "Keep every required source subject visible and primary; the recurring visual signature must not replace, merge with, or hide them."
            )
        if signature.enabled and signature.profile is not None:
            locked_constraints.append(
                "Keep the recurring visual identity scene-bound and recognizable by every configured identity trait; never render it as a sticker, logo, watermark, or corner badge."
            )
        if visible_text_policy == "no_visible_text":
            locked_constraints.append(
                "Use no visible readable text; use blank marks and unlabeled nodes only."
            )

        negative_prompt = ", ".join(_dedupe_text(negative_parts))
        assert_series_visual_signature_final_prompt(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            required_subjects=required_subjects,
            signature=signature,
            visible_text_policy=visible_text_policy,
        )

        return FinalVisualPromptBundle(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            locked_constraints=tuple(locked_constraints),
            metadata={
                "schema_version": "v4.5-signature",
                "contract_id": contract.get("contract_id"),
                "frame_id": contract.get("frame_id"),
                "compiler": "FinalVisualPromptCompiler",
                "required_subjects": list(required_subjects),
                "series_visual_signature": signature.to_dict(),
            },
        )

    def compile_for_z_image(self, *, final_contract: Any) -> ZImagePromptBundle:
        """Compatibility/provider adapter entry point for Z-Image only."""

        bundle = self.compile(final_contract=final_contract)
        metadata = bundle.to_dict()["metadata"]
        metadata["target_provider"] = "z_image"
        return ZImagePromptBundle(
            positive_prompt=bundle.positive_prompt,
            negative_prompt=bundle.negative_prompt,
            locked_constraints=bundle.locked_constraints,
            metadata=metadata,
        )


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    raise ValueError("final_contract must be a mapping or expose to_dict()")


def _signature_contract(
    original_contract: Any,
    contract_payload: Mapping[str, Any],
) -> SeriesVisualSignatureContract:
    candidate = getattr(original_contract, "series_visual_signature", None)
    if isinstance(candidate, SeriesVisualSignatureContract):
        return candidate
    raw = contract_payload.get("series_visual_signature")
    if isinstance(raw, SeriesVisualSignatureContract):
        return raw
    if isinstance(raw, Mapping):
        return SeriesVisualSignatureContract.from_mapping(raw)
    if raw is None:
        return SeriesVisualSignatureContract.disabled()
    raise ValueError("series_visual_signature must be a contract or mapping")


def _required_subjects(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, Sequence):
        raise ValueError("required_subjects must be a sequence of strings")
    return _dedupe_text(value)


def _required_subjects_clause(required_subjects: Sequence[str]) -> str:
    if not required_subjects:
        return ""
    return (
        "Required source subjects stay visible and primary: "
        + ", ".join(required_subjects)
        + ". Do not replace, merge, hide, or transform them into the recurring visual identity."
    )


def _diagram_clause(diagram: Mapping[str, Any]) -> str:
    grammar = str(diagram.get("grammar") or "single_explanation_image")
    if grammar == "plain_scene":
        return "Preserve the base scene action, composition, and subject hierarchy"
    if grammar == "relationship_map":
        return "Show an unlabeled relationship map with nodes, distance, and clean connection lines"
    if grammar == "process_flow":
        return "Show a simple left-to-right process flow with one bottleneck and one resolved path"
    if grammar == "metaphor_scene":
        return "Show a single physical metaphor scene with one memorable object relationship"
    if grammar == "contrast_board":
        return "Show a split contrast board with two clear sides"
    if grammar == "structure_map":
        return "Show a clean structure map with grouped containers and simple links"
    return "Show one focused explanation image with a single main idea"


def _style_clause(render: Mapping[str, Any]) -> str:
    style = str(render.get("render_style") or "auto")
    if style == "preserve_base":
        return "Preserve the base scene visual style, camera, lighting, and surface treatment"
    if style == "xiaohei_handdrawn":
        return "White background, flat monochrome hand-drawn line art, simple black marker lines, low detail, clean composition"
    if style == "clean_vector":
        return "Clean vector diagram, simple shapes, precise spacing, low texture"
    if style == "editorial_diagram":
        return "Editorial explanatory diagram, clear hierarchy, restrained annotation marks"
    return "Clean explanatory visual, simple composition, low clutter"


def _signature_clause(signature: SeriesVisualSignatureContract) -> str:
    if not signature.enabled:
        return ""
    profile = signature.profile
    if profile is None:
        raise ValueError("enabled series visual signature requires a profile")
    traits = ", ".join(profile.identity_traits)
    role_text = _natural_signature_role(signature.role.value)
    return (
        f"Recurring visual identity {profile.display_name} appears in the scene, recognizable by every configured identity trait: {traits}. "
        f"It works as {role_text}, physically bound to a real diagram element, prop, surface, or supporting action. "
        f"Keep it clear but subordinate, within about {int(signature.max_area_ratio * 100)}% of the frame area, matching the scene style and never replacing required source subjects."
    )


def _natural_signature_role(role: str) -> str:
    return SERIES_VISUAL_SIGNATURE_NATURAL_ROLE_MAP.get(
        str(role or ""), "a scene-bound participant"
    )


def _compose_budgeted_prompt(
    *,
    main_visual: str,
    diagram_clause: str,
    required_subjects_clause: str,
    signature_clause: str,
    style_clause: str,
    limit: int,
) -> str:
    protected_parts = [part for part in (required_subjects_clause, signature_clause) if part]
    protected_text = ". ".join(protected_parts)
    if len(protected_text) > limit:
        raise ValueError(
            "protected visual prompt semantics exceed product prompt budget; "
            "reduce required subjects or identity verbosity before generation"
        )

    optional_budget = limit - len(protected_text) - (2 if protected_text else 0)
    optional_parts: list[str] = []
    for candidate in (main_visual, diagram_clause, style_clause):
        text = " ".join(str(candidate or "").split())
        if not text or optional_budget <= 0:
            continue
        separator_cost = 2 if optional_parts else 0
        available = optional_budget - separator_cost
        if available <= 0:
            break
        fitted = _shorten(text, available)
        if not fitted:
            continue
        optional_parts.append(fitted)
        optional_budget -= len(fitted) + separator_cost

    ordered: list[str] = []
    if optional_parts:
        ordered.extend(optional_parts[:2])
    ordered.extend(protected_parts)
    if len(optional_parts) > 2:
        ordered.extend(optional_parts[2:])
    prompt = ". ".join(part for part in ordered if part)
    if len(prompt) > limit:
        raise ValueError("final prompt budget accounting failed")
    return prompt


def _split_negative_prompt(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _dedupe_text(values: Sequence[Any]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").strip().split())
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return " ".join(value.strip().split())
    return ""


def _shorten(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return text[: limit - 1].rstrip() + "…"


__all__ = ["FinalVisualPromptCompiler"]
