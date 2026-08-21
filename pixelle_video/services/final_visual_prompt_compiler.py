from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)
from pixelle_video.models.content_bound_ip import (
    ContentBoundIPPresencePlan,
    IPParticipationMechanism,
)
from pixelle_video.models.final_visual_prompt_bundle import FinalVisualPromptBundle
from pixelle_video.models.final_visual_prompt_contract_v45 import (
    FinalVisualPromptContractV45,
)
from pixelle_video.models.final_visual_prompt_contract_v46 import (
    FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA,
    FinalVisualPromptContractV46,
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
    assert_mandatory_content_bound_final_prompt,
    assert_series_visual_signature_final_prompt,
)
from pixelle_video.services.series_visual_signature_prompt_presence import (
    prompt_contains_term,
)
from pixelle_video.services.series_visual_signature_rendering import (
    rendered_identity_clause,
    rendered_identity_traits,
    rendered_provider_action_verb,
    rendered_provider_participation_text,
)
from pixelle_video.services.visible_text_prompt_rewriter import (
    NO_VISIBLE_TEXT_DRAWING_CLAUSE,
    NO_VISIBLE_TEXT_NEGATIVE_PROMPT,
    rewrite_for_no_visible_text,
    rewrite_visible_text_drawing_risks,
)

MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS = 1200
MAX_Z_IMAGE_NEGATIVE_PROMPT_CHARS = 800
MAX_MAIN_AND_SUBJECT_CHARS = 400
MAX_RENDERED_IDENTITY_CHARS = 400
# Public compatibility alias. The persisted canonical clause remains an audit
# source, while provider-facing rendering now uses a deduplicated clause.
MAX_CANONICAL_IDENTITY_CHARS = MAX_RENDERED_IDENTITY_CHARS
MAX_PLACEMENT_AND_FUSION_CHARS = 300
MAX_ROLE_AND_ACTION_CHARS = 200
MAX_INSTANCE_CONTROL_CHARS = 240
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
        if _is_v46_contract(final_contract):
            return self._compile_v46(
                final_contract=final_contract,
                base_negative_prompt=base_negative_prompt,
            )
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

        placement = _placement_contract(final_contract, contract)
        fusion = _fusion_contract(final_contract, contract)
        prompt_budget: dict[str, Any] | None = None
        if signature.enabled:
            main_visual = _first_non_empty(
                diagram.get("visual_metaphor"),
                contract.get("visual_concretization_summary"),
                anchor.get("anchor_claim"),
                "one clear explanation visual",
            )
            optional_visual_details = _optional_visual_details(
                main_visual,
                contract.get("visual_concretization_summary"),
                anchor.get("anchor_claim"),
            )
            if visible_text_policy == "no_visible_text":
                main_visual = rewrite_for_no_visible_text(main_visual)
                optional_visual_details = _optional_visual_details(
                    main_visual,
                    *(
                        rewrite_visible_text_drawing_risks(detail)
                        for detail in optional_visual_details
                    ),
                )
            prompt_sections, prompt_budget = _signature_prompt_sections(
                main_visual=main_visual,
                optional_visual_details=optional_visual_details,
                required_subjects=required_subjects,
                signature=signature,
                placement=placement,
                fusion=fusion,
                render=render,
            )
            positive_prompt = _join_sections(prompt_sections.values())
        else:
            main_visual = _first_non_empty(
                diagram.get("visual_metaphor"),
                anchor.get("anchor_claim"),
                contract.get("visual_concretization_summary"),
                "one clear explanation visual",
            )
            if visible_text_policy == "no_visible_text":
                main_visual = rewrite_for_no_visible_text(main_visual)
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
                "instance_control",
                "role",
                "placement",
                "scene_fusion",
                "subject_protection",
            }
        )
        metadata = {
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
        }
        if prompt_budget is not None:
            metadata["prompt_budget"] = prompt_budget
        return FinalVisualPromptBundle(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            locked_constraints=locked_constraints,
            metadata=metadata,
        )

    def _compile_v46(
        self,
        *,
        final_contract: Any,
        base_negative_prompt: str | None,
    ) -> FinalVisualPromptBundle:
        contract = FinalVisualPromptContractV46.from_mapping(final_contract)
        mandatory = contract.mandatory_anchor_contract
        plan = mandatory.participation_plan
        profile = mandatory.identity_contract.profile
        if profile is None:
            raise ValueError("V4.6 mandatory anchor identity profile is missing")

        main_scene = mandatory.final_scene_description
        if contract.visible_text_policy == "no_visible_text":
            main_scene = rewrite_for_no_visible_text(main_scene)
        main_content = _v46_main_content(
            main_scene=main_scene,
            content_claim=mandatory.content_claim,
            required_subjects=mandatory.required_subject_labels,
        )
        identity = _v46_identity_clause(
            display_name=profile.display_name,
            traits=rendered_identity_traits(profile),
            anchor_subject_overlap=mandatory.anchor_subject_overlap,
        )
        participation = _v46_participation_clause(plan)
        spatial = _v46_spatial_clause(mandatory.placement)
        fusion = _v46_fusion_clause(mandatory.scene_fusion)
        instance_control = (
            "全画面所有动作均由同一个指定角色的一副身体、一个头部和一个位置完成；"
            "无副本、倒影或主体替代"
        )
        style = _bounded_style_clause(contract.diagram_render)
        sections = {
            "main_content": main_content,
            "identity": identity,
            "participation": participation,
            "instance_control": instance_control,
            "placement": spatial,
            "scene_fusion": fusion,
            "style": style,
        }
        paragraphs = _v46_prompt_paragraphs(
            sections,
            anchor_subject_overlap=mandatory.anchor_subject_overlap,
        )
        positive_prompt = "\n".join(paragraphs)
        if len(positive_prompt) > 800:
            sections.pop("style")
            paragraphs = _v46_prompt_paragraphs(
                sections,
                anchor_subject_overlap=mandatory.anchor_subject_overlap,
            )
            positive_prompt = "\n".join(paragraphs)
        main_chars = len(
            "；".join((sections["participation"], sections["main_content"]))
        )
        identity_chars = len(
            "；".join((sections["identity"], sections["instance_control"]))
        )
        content_chars = main_chars
        if content_chars / len(positive_prompt) < 0.35 and "style" in sections:
            sections.pop("style")
            paragraphs = _v46_prompt_paragraphs(
                sections,
                anchor_subject_overlap=mandatory.anchor_subject_overlap,
            )
            positive_prompt = "\n".join(paragraphs)
        if len(positive_prompt) > 800:
            raise ValueError(
                "protected visual prompt semantics exceed V4.6 800 character prompt budget"
            )

        main_section_chars = len(sections["main_content"])
        negative_parts = _split_negative_prompt(base_negative_prompt)
        negative_parts.extend(mandatory.forbidden_compositions)
        if contract.visible_text_policy == "no_visible_text":
            negative_parts.append(NO_VISIBLE_TEXT_NEGATIVE_PROMPT)
        negative_prompt = ", ".join(_dedupe_text(negative_parts))
        if len(negative_prompt) > 800:
            raise ValueError("final negative prompt exceeds 800 characters")

        assert_mandatory_content_bound_final_prompt(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            contract=mandatory,
            main_content_chars=main_chars,
            identity_chars=identity_chars,
        )
        prompt_budget = {
            "positive_prompt_chars": len(positive_prompt),
            "positive_prompt_limit": 800,
            "main_content_chars": main_chars,
            "main_content_section_chars": main_section_chars,
            "content_bound_action_chars": len(sections["participation"]),
            "main_content_ratio": round(main_chars / len(positive_prompt), 4),
            "main_content_min_ratio": 0.35,
            "identity_chars": identity_chars,
            "identity_ratio": round(identity_chars / len(positive_prompt), 4),
            "identity_max_ratio": 0.30,
            "hard_truncated": False,
        }
        return FinalVisualPromptBundle(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            locked_constraints=paragraphs,
            metadata={
                "schema_version": FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA,
                "contract_id": contract.contract_id,
                "frame_id": contract.frame_id,
                "contract_version": contract.contract_version,
                "contract_content_sha256": contract.contract_content_sha256,
                "mandatory_anchor_contract_sha256": (
                    mandatory.contract_content_sha256
                ),
                "identity_content_sha256": profile.identity_content_sha256,
                "compiler": "FinalVisualPromptCompiler",
                "required_subjects": list(mandatory.required_subject_labels),
                "prompt_sections": sections,
                "prompt_paragraphs": list(paragraphs),
                "prompt_budget": prompt_budget,
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
    optional_visual_details: Sequence[str],
    required_subjects: Sequence[str],
    signature: SeriesVisualSignatureContract,
    placement: VisualEntityPlacement | None,
    fusion: VisualEntitySceneFusion | None,
    render: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    profile = signature.profile
    if profile is None:
        raise ValueError("enabled series visual signature requires a profile")
    if placement is None:
        raise ValueError("enabled series visual signature requires entity_placement")
    if fusion is None:
        raise ValueError("enabled series visual signature requires scene_fusion")

    subject_protection = _subject_protection_clause(required_subjects)
    fitted_main_visual, main_visual_audit = _fit_main_visual(
        main_visual=main_visual,
        subject_protection=subject_protection,
    )
    sections = {
        "main_content": f"Main scene: {fitted_main_visual}",
        "main_detail": "",
        "subject_protection": subject_protection,
        "fixed_identity": rendered_identity_clause(profile),
        "instance_control": _single_instance_clause(),
        "role": (
            "This same identity keeps its original character form; "
            f"role {signature.role.value}; {placement.action}"
        ),
        "placement": _placement_clause(placement),
        "scene_fusion": _fusion_clause(fusion),
        "style": _bounded_style_clause(render),
    }
    _assert_section_budget(
        "main content and required subjects",
        _join_sections(
            (
                sections["main_content"],
                sections["subject_protection"],
            )
        ),
        MAX_MAIN_AND_SUBJECT_CHARS,
    )
    _assert_section_budget(
        "rendered identity",
        sections["fixed_identity"],
        MAX_RENDERED_IDENTITY_CHARS,
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
    _assert_section_budget(
        "single instance control",
        sections["instance_control"],
        MAX_INSTANCE_CONTROL_CHARS,
    )
    _assert_section_budget("style", sections["style"], MAX_STYLE_CHARS)

    protected_positive_prompt = _join_sections(sections.values())
    if len(protected_positive_prompt) > MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS:
        raise ValueError(
            "protected visual prompt semantics exceed product prompt budget"
        )

    detail, detail_audit = _fit_optional_visual_details(
        candidates=optional_visual_details,
        main_group_chars=len(
            _join_sections(
                (sections["main_content"], sections["subject_protection"])
            )
        ),
        protected_prompt_chars=len(protected_positive_prompt),
    )
    sections["main_detail"] = detail
    main_group_chars = len(
        _join_sections(
            (
                sections["main_content"],
                sections["main_detail"],
                sections["subject_protection"],
            )
        )
    )
    _assert_section_budget(
        "main content and required subjects",
        _join_sections(
            (
                sections["main_content"],
                sections["main_detail"],
                sections["subject_protection"],
            )
        ),
        MAX_MAIN_AND_SUBJECT_CHARS,
    )
    final_positive_chars = len(_join_sections(sections.values()))
    if final_positive_chars > MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS:
        raise RuntimeError(
            "optional visual detail exceeded the positive prompt budget"
        )
    if not detail:
        sections.pop("main_detail")
    return sections, {
        "positive_prompt_chars": final_positive_chars,
        "positive_prompt_limit": MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS,
        "main_and_subject_chars": main_group_chars,
        "main_and_subject_limit": MAX_MAIN_AND_SUBJECT_CHARS,
        "rendered_identity_chars": len(sections["fixed_identity"]),
        "rendered_identity_limit": MAX_RENDERED_IDENTITY_CHARS,
        # Compatibility aliases for persisted trace readers.
        "canonical_identity_chars": len(sections["fixed_identity"]),
        "canonical_identity_limit": MAX_RENDERED_IDENTITY_CHARS,
        "single_instance_control_chars": len(sections["instance_control"]),
        "single_instance_control_limit": MAX_INSTANCE_CONTROL_CHARS,
        "main_visual": main_visual_audit,
        "placement_and_fusion_chars": len(
            _join_sections((sections["placement"], sections["scene_fusion"]))
        ),
        "placement_and_fusion_limit": MAX_PLACEMENT_AND_FUSION_CHARS,
        "role_and_action_chars": len(sections["role"]),
        "role_and_action_limit": MAX_ROLE_AND_ACTION_CHARS,
        "style_chars": len(sections["style"]),
        "style_limit": MAX_STYLE_CHARS,
        "optional_visual_detail": detail_audit,
    }


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
        f"Same identity: {placement.horizontal_position.value}/"
        f"{placement.depth_position.value}/{placement.relative_size.value.replace('_', '-')}; "
        f"{placement.spatial_relation} {placement.relation_target}; "
        f"{placement.support_relation}; {placement.orientation}; "
        f"{placement.visible_extent.value.replace('_', '-')}; "
        "defining traits visible"
    )


def _single_instance_clause() -> str:
    return (
        "Exactly one recurring identity exists in the whole frame: one body, "
        "one head, one location; it stays visually subordinate to the main content"
    )


def _fit_main_visual(
    *,
    main_visual: str,
    subject_protection: str,
) -> tuple[str, dict[str, Any]]:
    prefix = "Main scene: "
    separator_chars = 2 if subject_protection else 0
    available = (
        MAX_MAIN_AND_SUBJECT_CHARS
        - len(prefix)
        - len(subject_protection)
        - separator_chars
    )
    if available <= 0:
        raise ValueError(
            "protected main content and required subjects exceed product prompt budget"
        )
    source = " ".join(str(main_visual or "").split())
    protected_suffix = ""
    compactable_source = source
    if NO_VISIBLE_TEXT_DRAWING_CLAUSE in source:
        compactable_source = source.replace(NO_VISIBLE_TEXT_DRAWING_CLAUSE, "")
        compactable_source = compactable_source.strip(" ;,.")
        protected_suffix = f"; {NO_VISIBLE_TEXT_DRAWING_CLAUSE}"
    compactable_limit = available - len(protected_suffix)
    if compactable_limit <= 0:
        raise ValueError(
            "protected no-visible-text drawing clause cannot fit product prompt budget"
        )
    fitted = _shorten_optional(compactable_source, compactable_limit)
    if protected_suffix:
        fitted = f"{fitted}{protected_suffix}"
    if not fitted:
        raise ValueError("protected main visual cannot fit product prompt budget")
    return fitted, {
        "source_chars": len(source),
        "included_chars": len(fitted),
        "compacted": fitted != source,
    }


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
        isinstance(value, FinalVisualPromptContractV46)
        or payload.get("schema_version") == FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA
    ):
        return FinalVisualPromptContractV46.from_mapping(payload).to_dict()
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
    labels: list[Any] = []
    for item in value:
        if isinstance(item, Mapping):
            labels.append(item.get("label") or item.get("source_phrase") or "")
        else:
            labels.append(item)
    return _dedupe_text(labels)


def _is_v46_contract(value: Any) -> bool:
    if isinstance(value, FinalVisualPromptContractV46):
        return True
    if isinstance(value, Mapping):
        return (
            value.get("schema_version") == FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA
            or value.get("contract_version") == "final_visual_prompt_contract.v4_6"
        )
    return False


def _v46_main_content(
    *,
    main_scene: str,
    content_claim: str,
    required_subjects: Sequence[str],
) -> str:
    parts = ["文案主画面：" + " ".join(str(main_scene).split())]
    if content_claim and not prompt_contains_term(parts[0], content_claim):
        parts.append("画面主张是" + content_claim)
    missing = [
        subject
        for subject in required_subjects
        if not prompt_contains_term("；".join(parts), subject)
    ]
    if missing:
        parts.append("必须完整保留并清晰显示" + "、".join(missing))
    return "；".join(parts)


def _v46_identity_clause(
    *,
    display_name: str,
    traits: Sequence[str],
    anchor_subject_overlap: bool,
) -> str:
    if anchor_subject_overlap:
        clause = "该原文主体同时保持指定角色身份"
    else:
        clause = f"画面必须清晰出现且仅出现一个{display_name}"
    if traits:
        clause += "，可见特征为" + "、".join(traits)
    return clause


def _v46_participation_clause(plan: ContentBoundIPPresencePlan) -> str:
    provider_action_verb = rendered_provider_action_verb(
        plan.action_verb,
        participation_mechanism=plan.participation_mechanism,
        interaction_target=plan.interaction_target,
        physical_metaphor=plan.physical_metaphor,
        user_overrode_action=(
            "mandatory_anchor_action_verb" in plan.user_override_fields
        ),
    )

    def render_plan_text(value: str) -> str:
        return rendered_provider_participation_text(
            value,
            action_verb=plan.action_verb,
            provider_action_verb=provider_action_verb,
        )

    singular_conflict_pose = ""
    if (
        plan.participation_mechanism
        is IPParticipationMechanism.CONFLICT_PARTICIPANT
        and provider_action_verb != plan.action_verb
    ):
        singular_conflict_pose = (
            "一个指定角色面向对比图，以同一个身体和一只前爪完成指示动作；"
        )
    return (
        singular_conflict_pose
        + f"指定角色执行{provider_action_verb}，动作目标是{plan.interaction_target}；"
        + f"{render_plan_text(plan.action_result)}；"
        + f"{render_plan_text(plan.semantic_necessity)}；"
        + render_plan_text(plan.scene_binding)
    )


def _v46_spatial_clause(placement: VisualEntityPlacement) -> str:
    horizontal = {
        "left": "画面左侧",
        "center": "画面中央",
        "right": "画面右侧",
        "cross_frame": "跨越画面",
    }[placement.horizontal_position.value]
    depth = {
        "foreground": "前部空间",
        "midground": "中部空间",
        "background": "后部空间",
        "full_frame": "全画面空间",
    }[placement.depth_position.value]
    extent = {
        "full_body": "全身可见",
        "half_body": "半身可见",
        "partial": "局部但身份可识别",
        "distant_silhouette": "远景轮廓且身份可识别",
        "headshot": "头肩特写",
        "recognizable_detail": "身份特征细节清晰可见",
    }[placement.visible_extent.value]
    relative_size = {
        "small": "在画面中保持小体量",
        "medium_small": "在画面中保持中小体量",
        "medium": "在画面中保持中等体量",
        "large": "在画面中保持较大体量",
        "full_frame": "覆盖画面主体区域",
    }[placement.relative_size.value]
    return (
        f"该指定角色位于{horizontal}的{depth}，{relative_size}；"
        f"{_natural_spatial_fact(placement.support_relation)}；"
        f"身体和视线朝向{placement.relation_target}；{extent}"
    )


def _v46_fusion_clause(fusion: VisualEntitySceneFusion) -> str:
    facts = [fusion.occlusion_relation, fusion.style_relation]
    if fusion.scene_type is VisualSceneType.PHYSICAL_SCENE:
        facts.extend(
            (
                fusion.perspective_relation,
                fusion.contact_relation,
                fusion.lighting_relation,
                fusion.shadow_relation,
            )
        )
    return "场景融合：" + "；".join(_natural_fusion_fact(value) for value in facts)


def _v46_prompt_paragraphs(
    sections: Mapping[str, str],
    *,
    anchor_subject_overlap: bool,
) -> tuple[str, ...]:
    identity_first = (
        "；".join(
            (
                sections["identity"],
                sections["instance_control"],
                sections["placement"],
            )
        ),
        "；".join((sections["participation"], sections["main_content"])),
    )
    content_first = tuple(reversed(identity_first))
    paragraphs = (
        *(content_first if anchor_subject_overlap else identity_first),
        sections["scene_fusion"],
        sections.get("style", ""),
    )
    return tuple(paragraph for paragraph in paragraphs if paragraph)


def _natural_spatial_fact(value: str) -> str:
    replacements = {
        "feet on existing ground": "双脚与既有地面稳定接触",
        "at node or path": "身体稳定连接既有节点或路径",
    }
    return replacements.get(value, value)


def _natural_fusion_fact(value: str) -> str:
    replacements = {
        "unobscured single identity": "身份特征与必要主体无遮挡",
        "same line/material/texture/realism": "线条、材质、纹理和真实程度统一",
        "same diagram linework/material/texture": "线条、材质和纹理与图解统一",
        "scene perspective": "尺寸和地平线服从场景透视",
        "feet on existing ground": "双脚稳定接地",
        "matches scene light": "受光方向和色温匹配场景",
        "scene-soft contact shadow": "落点保留自然接触阴影",
        "diagram links pass behind body, not core traits": "图解连线从身体后方经过且不遮挡身份特征",
    }
    return replacements.get(value, value)


def _optional_visual_details(main_visual: str, *values: Any) -> tuple[str, ...]:
    main_key = " ".join(str(main_visual or "").strip().split()).casefold()
    details: list[str] = []
    seen: set[str] = set()
    for value in values:
        detail = " ".join(str(value or "").strip().split())
        key = detail.casefold()
        if not detail or key == main_key or key in seen:
            continue
        seen.add(key)
        details.append(detail)
    return tuple(details)


def _fit_optional_visual_details(
    *,
    candidates: Sequence[str],
    main_group_chars: int,
    protected_prompt_chars: int,
) -> tuple[str, dict[str, Any]]:
    normalized = _dedupe_text(candidates)
    source = _join_sections(normalized)
    audit = {
        "candidate_count": len(normalized),
        "source_chars": len(source),
        "included_chars": 0,
        "included": False,
        "compacted": False,
    }
    if not source:
        return "", audit

    # Adding a new non-empty prompt section costs one ". " separator in both
    # the 400-character main group and the 1200-character final prompt.
    available = min(
        MAX_MAIN_AND_SUBJECT_CHARS - main_group_chars,
        MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS - protected_prompt_chars,
    )
    section_limit = available - 2
    prefix = "Visual detail: "
    if section_limit <= len(prefix):
        audit["compacted"] = True
        return "", audit

    fitted = _shorten_optional(source, section_limit - len(prefix))
    if not fitted:
        audit["compacted"] = True
        return "", audit
    detail = prefix + fitted
    audit.update(
        {
            "included_chars": len(detail),
            "included": True,
            "compacted": fitted != source,
        }
    )
    return detail, audit


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
    return _fit_complete_phrases(text, limit)


def _shorten_optional(text: str, limit: int) -> str:
    """Fit optional details by dropping whole phrases, never slicing facts."""

    return _fit_complete_phrases(text, limit)


def _fit_complete_phrases(text: str, limit: int) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if limit <= 0 or not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    phrases = tuple(
        phrase.strip()
        for phrase in re.findall(r"[^。；;.!?！？]+[。；;.!?！？]?", normalized)
        if phrase.strip()
    )
    included: list[str] = []
    for phrase in phrases:
        candidate = " ".join((*included, phrase))
        if len(candidate) > limit:
            break
        included.append(phrase)
    return " ".join(included)


__all__ = [
    "FinalVisualPromptCompiler",
    "MAX_CANONICAL_IDENTITY_CHARS",
    "MAX_INSTANCE_CONTROL_CHARS",
    "MAX_MAIN_AND_SUBJECT_CHARS",
    "MAX_PLACEMENT_AND_FUSION_CHARS",
    "MAX_RENDERED_IDENTITY_CHARS",
    "MAX_STYLE_CHARS",
    "MAX_Z_IMAGE_NEGATIVE_PROMPT_CHARS",
    "MAX_Z_IMAGE_POSITIVE_PROMPT_CHARS",
    "SERIES_VISUAL_SIGNATURE_NEGATIVE_PROTECTIONS",
]
