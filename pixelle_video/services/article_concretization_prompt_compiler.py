from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract
from pixelle_video.models.z_image_prompt_bundle import ZImagePromptBundle
from pixelle_video.services.visible_text_prompt_rewriter import (
    NO_VISIBLE_TEXT_NEGATIVE_PROMPT,
    rewrite_for_no_visible_text,
)


class ArticleConcretizationPromptCompiler:
    """Compile the normalized final contract into a Z-Image friendly prompt bundle."""

    def compile_for_z_image(self, *, final_contract: Any) -> ZImagePromptBundle:
        contract = _to_mapping(final_contract)
        reject_deprecated_signature_fields(contract, context="final contract")
        concretization = dict(contract.get("article_concretization") or {})
        anchor = dict(concretization.get("anchor") or {})
        diagram = dict(concretization.get("diagram") or {})
        render = dict(contract.get("diagram_render") or concretization.get("render") or {})
        signature = _signature_contract(final_contract, contract)
        visible_text_policy = str(contract.get("visible_text_policy") or diagram.get("visible_text_policy") or "no_visible_text")

        main_visual = _first_non_empty(
            diagram.get("visual_metaphor"),
            anchor.get("anchor_claim"),
            contract.get("visual_concretization_summary"),
            "one clear explanation visual",
        )
        diagram_clause = _diagram_clause(diagram)
        style_clause = _style_clause(render)
        signature_clause = _signature_clause(signature)
        positive_parts = [main_visual, diagram_clause, signature_clause, style_clause]
        positive_prompt = ". ".join(part for part in positive_parts if part)
        negative_parts = ["photorealistic mascot, sticker, logo, watermark, dense messy diagram"]
        locked_constraints = [
            "provider adapter must receive only ZImagePromptBundle",
            "series visual signature must not replace required subjects",
        ]
        if visible_text_policy == "no_visible_text":
            positive_prompt = rewrite_for_no_visible_text(positive_prompt)
            negative_parts.append(NO_VISIBLE_TEXT_NEGATIVE_PROMPT)
            locked_constraints.append("no visible text: use blank marks and unlabeled nodes only")
        metadata = {
            "schema_version": "v4.5-signature",
            "contract_id": contract.get("contract_id"),
            "frame_id": contract.get("frame_id"),
            "compiler": "ArticleConcretizationPromptCompiler",
            "target_provider": "z_image",
            "series_visual_signature": signature.to_dict(),
        }
        return ZImagePromptBundle(
            positive_prompt=_shorten(positive_prompt, 1000),
            negative_prompt=", ".join(part for part in negative_parts if part),
            locked_constraints=tuple(locked_constraints),
            metadata=metadata,
        )


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    raise ValueError("final_contract must be a mapping or expose to_dict()")


def _signature_contract(original_contract: Any, contract_payload: Mapping[str, Any]) -> SeriesVisualSignatureContract:
    candidate = getattr(original_contract, "series_visual_signature", None)
    if isinstance(candidate, SeriesVisualSignatureContract):
        return candidate
    raw = contract_payload.get("series_visual_signature")
    if isinstance(raw, SeriesVisualSignatureContract):
        return raw
    return SeriesVisualSignatureContract.disabled()


def _diagram_clause(diagram: Mapping[str, Any]) -> str:
    grammar = str(diagram.get("grammar") or "single_explanation_image")
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
    traits = ", ".join(profile.identity_traits[:3]) if profile else "recurring visual signature"
    return (
        f"A small supporting series visual signature appears as {signature.role.value}, "
        f"using these short traits: {traits}. Same flat style as the scene, max {int(signature.max_area_ratio * 100)}% image area, "
        "not a sticker, not a logo, not photorealistic"
    )


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return " ".join(value.strip().split())
    return ""


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
