from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)
from pixelle_video.models.final_visual_prompt_bundle import FinalVisualPromptBundle
from pixelle_video.models.final_visual_prompt_contract_v45 import (
    FinalVisualPromptContractV45,
)
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract
from pixelle_video.models.visual_entity_placement import (
    DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
    VisualEntityPlacement,
    VisualEntitySceneFusion,
    VisualSceneType,
)
from pixelle_video.models.z_image_prompt_bundle import ZImagePromptBundle
from pixelle_video.services.series_visual_signature_final_prompt_gate import (
    assert_series_visual_signature_final_prompt,
)
from pixelle_video.services.visible_text_prompt_rewriter import (
    NO_VISIBLE_TEXT_NEGATIVE_PROMPT,
    rewrite_for_no_visible_text,
)

MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS = 1200
MAX_Z_IMAGE_NEGATIVE_PROMPT_CHARS = 800
MAX_MAIN_AND_SUBJECT_CHARS = 400
MAX_CANONICAL_IDENTITY_CHARS = 400
MAX_PLACEMENT_AND_FUSION_CHARS = 300
MAX_ROLE_AND_ACTION_CHARS = 200
MAX_STYLE_CHARS = 100

SERIES_VISUAL_SIGNATURE_NEGATIVE_PROTECTIONS = (
    "duplicate recurring visual signature instances or extra copies",
    "recurring visual signature rendered as a mascot in a mismatched style",
    *DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
    "recurring visual signature floating or missing support contact",
    "recurring visual signature with mismatched style, lighting, or perspective",
    "non-human recurring identity with human anatomy, human clothing, or mascot costume",
)


class FinalVisualPromptCompiler:
    """Compile one provider-neutral contract into one bounded prompt pair."""

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

        placement = _placement_contract(final_contract, contract)
        fusion = _fusion_contract(final_contract, contract)
        if signature.enabled:
            prompt_sections = _signature_prompt_sections(
                main_visual=main_visual,
                required_subjects=required_subjects,
                signature=signature,
                placement=placement,
                fusion=fusion,
                render=render,
            )
            positive_prompt = _join_sections(prompt_sections.values())
        else:
            prompt_sections = _unsigned_prompt_sections(
                main_visual=main_visual,
                diagram=diagram,
                required_subjects=required_subjects,
                render=render,
            )
            positive_prompt = _compose_unsigned_prompt(prompt_sections)

        negative_parts = _split_negative_prompt(base_negative_prompt)
        if signature.enabled:
            negative_parts.extend(SERIES_VISUAL_SIGNATURE_NEGATIVE_PROTECTIONS)
            if fusion is not None:
                negative_parts.extend(fusion.forbidden_compositions)
            if str(render.get("render_style") or "").strip() in {
                "xiaohei_handdrawn",
                "clean_vector",
                "editorial_diagram",
            }:
                negative_parts.append("photorealistic mascot in a non-photographic scene")
            if signature.profile is not None:
                negative_parts.extend(signature.profile.forbidden_traits)
        if visible_text_policy == "no_visible_text":
            negative_parts.append(NO_VISIBLE_TEXT_NEGATIVE_PROMPT)
        negative_prompt = ", ".join(_dedupe_text(negative_parts))
        if len(negative_prompt) > MAX_Z_IMAGE_NEGATIVE_PROMPT_CHARS:
            raise ValueError(
                "final negative prompt exceeds 800 characters after deterministic deduplication"
            )
        if len(positive_prompt) > MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS:
            raise ValueError("final positive prompt exceeds 1200 characters")

        assert_series_visual_signature_final_prompt(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            required_subjects=required_subjects,
            signature=signature,
            visible_text_policy=visible_text_policy,
            placement=placement,
            scene_fusion=fusion,
            frame_id=str(contract.get("frame_id") or ""),
        )

        profile = signature.profile
        locked_constraints = tuple(
            section
            for key, section in prompt_sections.items()
            if key
            in {
                "main_content",
                "fixed_identity",
                "role",
                "placement",
                "scene_fusion",
                "subject_protection",
            }
        )
        return FinalVisualPromptBundle(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            locked_constraints=locked_constraints,
            metadata={
                "schema_version": "v4.5-signature",
                "contract_id": contract.get("contract_id"),
                "frame_id": contract.get("frame_id"),
                "contract_version": contract.get("contract_version"),
                "contract_content_sha256": contract.get("contract_content_sha256"),
                "identity_content_sha256": (
                    profile.identity_content_sha256 if profile is not None else None
                ),
                "compiler": "FinalVisualPromptCompiler",
                "required_subjects": list(required_subjects),
                "series_visual_signature": signature.to_dict(),
                "prompt_sections": prompt_sections,
            },
        )

    def compile_for_z_image(
        self,
        *,
        final_contract: Any,
        base_negative_prompt: str | None = None,
    ) -> ZImagePromptBundle:
        bundle = self.compile(
            final_contract=final_contract,
            base_negative_prompt=base_negative_prompt,
        )
        metadata = bundle.to_dict()["metadata"]
        metadata["target_provider"] = "z_image"
        return ZImagePromptBundle(
            positive_prompt=bundle.positive_prompt,
            negative_prompt=bundle.negative_prompt,
            locked_constraints=bundle.locked_constraints,
            metadata=metadata,
        )


def _signature_prompt_sections(
    *,
    main_visual: str,
    required_subjects: Sequence[str],
    signature: SeriesVisualSignatureContract,
    placement: VisualEntityPlacement | None,
    fusion: VisualEntitySceneFusion | None,
    render: Mapping[str, Any],
) -> dict[str, str]:
    profile = signature.profile
    if profile is None:
        raise ValueError("enabled series visual signature requires a profile")
    if placement is None:
        raise ValueError("enabled series visual signature requires entity_placement")
    if fusion is None:
        raise ValueError("enabled series visual signature requires scene_fusion")

    sections = {
        "main_content": f"Main scene: {main_visual}",
        "subject_protection": _subject_protection_clause(required_subjects),
        "fixed_identity": profile.canonical_identity_clause,
        "role": (
            "It keeps its original character form; "
            f"role {signature.role.value}; {placement.action}"
        ),
        "placement": _placement_clause(placement),
        "scene_fusion": _fusion_clause(fusion),
        "style": _bounded_style_clause(render),
    }
    _assert_section_budget(
        "main content and required subjects",
        _join_sections(
            (sections["main_content"], sections["subject_protection"])
        ),
        MAX_MAIN_AND_SUBJECT_CHARS,
    )
    _assert_section_budget(
        "canonical identity",
        sections["fixed_identity"],
        MAX_CANONICAL_IDENTITY_CHARS,
    )
    _assert_section_budget(
        "placement and scene fusion",
        _join_sections(
            (sections["placement"], sections["scene_fusion"])
        ),
        MAX_PLACEMENT_AND_FUSION_CHARS,
    )
    _assert_section_budget(
        "role and action",
        sections["role"],
        MAX_ROLE_AND_ACTION_CHARS,
    )
    _assert_section_budget("style", sections["style"], MAX_STYLE_CHARS)
    return sections


def _unsigned_prompt_sections(
    *,
    main_visual: str,
    diagram: Mapping[str, Any],
    required_subjects: Sequence[str],
    render: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "main_content": main_visual,
        "composition": _diagram_clause(diagram),
        "style": _bounded_style_clause(render),
        "subject_protection": _subject_protection_clause(required_subjects),
    }


def _compose_unsigned_prompt(sections: Mapping[str, str]) -> str:
    protected = sections["subject_protection"]
    if len(protected) > MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS:
        raise ValueError(
            "protected visual prompt semantics exceed product prompt budget"
        )
    parts: list[str] = []
    remaining = MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS - len(protected)
    for key in ("main_content", "composition", "style"):
        value = sections[key]
        separator = 2 if parts else 0
        available = remaining - separator
        if available <= 0:
            break
        fitted = _shorten(value, available)
        if fitted:
            parts.append(fitted)
            remaining -= len(fitted) + separator
    if protected:
        parts.append(protected)
    return _join_sections(parts)


def _placement_clause(
    placement: VisualEntityPlacement,
) -> str:
    return (
        f"One; {placement.horizontal_position.value}/"
        f"{placement.depth_position.value}/{placement.relative_size.value.replace('_', '-')}; "
        f"{placement.spatial_relation} {placement.relation_target}; "
        f"{placement.support_relation}; {placement.orientation}; "
        f"{placement.visible_extent.value.replace('_', '-')}; shows "
        + " + ".join(placement.visible_core_traits)
    )


def _fusion_clause(fusion: VisualEntitySceneFusion) -> str:
    if fusion.scene_type is VisualSceneType.ABSTRACT_DIAGRAM:
        return "; ".join((fusion.occlusion_relation, fusion.style_relation))
    return "; ".join(
        (
            fusion.occlusion_relation,
            fusion.perspective_relation,
            fusion.lighting_relation,
            fusion.shadow_relation,
            fusion.style_relation,
        )
    )


def _subject_protection_clause(required_subjects: Sequence[str]) -> str:
    if not required_subjects:
        return "Keep the existing main subject visible, primary, unobscured, and unreplaced"
    return (
        "Required subjects stay visible, primary, unobscured, and unreplaced: "
        + ", ".join(required_subjects)
    )


def _diagram_clause(diagram: Mapping[str, Any]) -> str:
    grammar = str(diagram.get("grammar") or "single_explanation_image")
    if grammar == "plain_scene":
        return "Preserve the base scene action, composition, and subject hierarchy"
    if grammar == "relationship_map":
        return "Show an unlabeled relationship map with clear nodes and connections"
    if grammar == "process_flow":
        return "Show a simple process flow with one bottleneck and one resolved path"
    if grammar == "metaphor_scene":
        return "Show a single physical metaphor with one memorable object relationship"
    if grammar == "contrast_board":
        return "Show a split contrast board with two clear sides"
    if grammar == "structure_map":
        return "Show a clean structure map with grouped containers and simple links"
    return "Show one focused explanation image with a single main idea"


def _bounded_style_clause(render: Mapping[str, Any]) -> str:
    if bool(render.get("style_already_projected")):
        return "Preserve the established whole-frame style, material, lighting, and texture"
    style = str(render.get("render_style") or "auto")
    clauses = {
        "preserve_base": "Preserve the established whole-frame style, material, lighting, and texture",
        "xiaohei_handdrawn": "Flat monochrome hand-drawn line art, simple marker lines, low detail",
        "clean_vector": "Clean vector forms, precise spacing, low texture",
        "editorial_diagram": "Editorial explanatory diagram, clear hierarchy, restrained marks",
    }
    return clauses.get(style, "Clean explanatory visual, coherent material, simple composition, low clutter")


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        payload = dict(value)
    elif hasattr(value, "to_dict"):
        serialized = value.to_dict()
        if not isinstance(serialized, Mapping):
            raise ValueError("final_contract.to_dict() must return a mapping")
        payload = dict(serialized)
    else:
        raise ValueError("final_contract must be a mapping or expose to_dict()")
    if (
        isinstance(value, FinalVisualPromptContractV45)
        or payload.get("schema_version") == "v4.5-signature"
    ):
        return FinalVisualPromptContractV45.from_mapping(payload).to_dict()
    return payload


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


def _placement_contract(
    original_contract: Any,
    contract_payload: Mapping[str, Any],
) -> VisualEntityPlacement | None:
    candidate = getattr(original_contract, "entity_placement", None)
    if candidate is None:
        candidate = contract_payload.get("entity_placement")
    if candidate is None:
        return None
    return VisualEntityPlacement.from_mapping(candidate)


def _fusion_contract(
    original_contract: Any,
    contract_payload: Mapping[str, Any],
) -> VisualEntitySceneFusion | None:
    candidate = getattr(original_contract, "scene_fusion", None)
    if candidate is None:
        candidate = contract_payload.get("scene_fusion")
    if candidate is None:
        return None
    return VisualEntitySceneFusion.from_mapping(candidate)


def _required_subjects(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, Sequence):
        raise ValueError("required_subjects must be a sequence of strings")
    return _dedupe_text(value)


def _assert_section_budget(label: str, value: str, limit: int) -> None:
    if len(value) > limit:
        raise ValueError(
            f"protected {label} exceeds {limit} character prompt budget"
        )


def _join_sections(values: Sequence[str] | Any) -> str:
    return ". ".join(str(value).strip().rstrip(".") for value in values if str(value).strip())


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


__all__ = [
    "FinalVisualPromptCompiler",
    "MAX_CANONICAL_IDENTITY_CHARS",
    "MAX_MAIN_AND_SUBJECT_CHARS",
    "MAX_PLACEMENT_AND_FUSION_CHARS",
    "MAX_STYLE_CHARS",
    "MAX_Z_IMAGE_NEGATIVE_PROMPT_CHARS",
    "MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS",
    "SERIES_VISUAL_SIGNATURE_NEGATIVE_PROTECTIONS",
]
