from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTENT_STAGE_PROMPT_VERSION = "visual_anchor_content_stage.v2"
FUSION_STAGE_PROMPT_VERSION = "visual_anchor_fusion_stage.v2"
PREFLIGHT_REVIEW_PROMPT_VERSION = "visual_anchor_preflight_review.v2"
GENERATION_REQUEST_VERSION = "visual_anchor_generation_request.v2"

ReviewDecision = Literal["pass", "fail"]

_FORBIDDEN_IMAGE_PROMPT_TERMS = (
    "视觉锚点",
    "知识产权角色",
    "受保护事实",
    "融合方案",
    "必须",
    "禁止",
    "候选方案",
    "未选方案",
    "分析过程",
    "修改理由",
    "审查结论",
    "自检结论",
    "失败项",
    "唯一实例核对",
    "连续场景核对",
    "非核心重构摘要",
    "方案一",
    "方案二",
    "或者",
    "也可以",
    "另一种形式",
    "可选择",
    "同时还可以",
    "visual anchor",
    "protected fact",
    "fusion option",
    "final manifestation",
    "identity trait checks",
    "single instance prompt evidence",
    "candidate option",
    "unselected option",
    "analysis process",
    "review result",
    "content_stage",
    "fusion_stage",
    "preflight_review",
    "protected_facts",
    "adjustable_non_core_content",
    "selected_fusion_method",
    "final_manifestation",
    "non_core_reconstruction_summary",
    "unselected_candidate_summaries",
    "protected_fact_checks",
    "identity_trait_checks",
    "final_prompt_evidence",
    "single_instance_prompt_evidence",
    "identity_core_traits",
    "target_visual_anchor_instance_count",
    "other_scene_elements_inherit_identity_features",
    "inherited_existing_fusion_decision",
    "continuity_change_reason",
    "self_check",
    "review_feedback",
    "alternatively",
    "another option",
    "could also",
    "or it could",
)
_SINGLE_INSTANCE_PROMPT_TERMS = (
    "只有一个",
    "仅有一个",
    "唯一一个",
    "只有一只",
    "仅有一只",
    "唯一一只",
    "只有一名",
    "仅有一名",
    "唯一一名",
    "exactly one",
    "only one",
    "a single",
)


def _contains_forbidden_term(value: str, term: str) -> bool:
    """Match planning terms without treating English word fragments as hits."""

    if term.isascii() and any(character.isalnum() for character in term):
        return re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
            value,
            flags=re.IGNORECASE,
        ) is not None
    return term.casefold() in value.casefold()


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return " ".join(value.split())


def _text_list(values: list[str], field_name: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value, field_name)
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


class ProtectedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str
    category: Literal[
        "person",
        "animal",
        "object",
        "product",
        "place",
        "era",
        "quantity",
        "action",
        "causality",
        "spatial_relation",
        "event",
        "theme",
        "other",
    ]
    statement: str
    source_evidence: str
    pure_content_prompt_evidence: str

    @field_validator(
        "fact_id",
        "statement",
        "source_evidence",
        "pure_content_prompt_evidence",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)


class ContentStageInput(BaseModel):
    """Identity-free input boundary for the content-only language-model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    original_storyboard_text: str
    article_context: str
    previous_frame_summary: str
    next_frame_summary: str
    target_visual_style: str
    target_image_prompt_language: str
    prompt_version: Literal[CONTENT_STAGE_PROMPT_VERSION] = CONTENT_STAGE_PROMPT_VERSION

    @field_validator("*", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info):
        if info.field_name == "prompt_version":
            return value
        return _text(value, info.field_name)


class ContentStageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    core_claim: str
    protected_facts: list[ProtectedFact] = Field(min_length=1)
    adjustable_non_core_content: list[str] = Field(default_factory=list)
    pure_content_prompt: str
    self_check: ReviewDecision
    self_check_failures: list[str] = Field(default_factory=list)

    @field_validator("core_claim", "pure_content_prompt", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("adjustable_non_core_content", "self_check_failures")
    @classmethod
    def _validate_list(cls, value: list[str], info) -> list[str]:
        return _text_list(value, info.field_name)

    @model_validator(mode="after")
    def _validate_result(self) -> "ContentStageOutput":
        fact_ids = [fact.fact_id for fact in self.protected_facts]
        if len(set(fact_ids)) != len(fact_ids):
            raise ValueError("protected fact ids must be unique")
        if self.self_check == "pass" and self.self_check_failures:
            raise ValueError("a passed content-stage result cannot contain failures")
        if self.self_check == "fail" and not self.self_check_failures:
            raise ValueError("a failed content-stage result must contain failures")
        return self


class VisualAnchorIdentityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    display_name: str
    core_identity_traits: list[str] = Field(min_length=1)
    supporting_identity_traits: list[str] = Field(default_factory=list)
    forbidden_traits: list[str] = Field(default_factory=list)
    source_asset_ids: list[str] = Field(min_length=1)
    identity_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_resource_version: str

    @field_validator("profile_id", "display_name", "identity_resource_version", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator(
        "core_identity_traits",
        "supporting_identity_traits",
        "forbidden_traits",
        "source_asset_ids",
    )
    @classmethod
    def _validate_lists(cls, value: list[str], info) -> list[str]:
        return _text_list(value, info.field_name)

    @model_validator(mode="after")
    def _validate_resource_version(self) -> "VisualAnchorIdentityProfile":
        expected = f"identity:{self.profile_id}:{self.identity_content_sha256}"
        if self.identity_resource_version != expected:
            raise ValueError(
                "identity resource version must match the profile id and identity digest"
            )
        return self


class IdentityReferenceCondition(BaseModel):
    """Immutable condition that must be bound to the first image workflow call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    workflow_asset_relative_path: str
    mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    byte_size: int = Field(gt=0)
    resource_version: str
    workflow_parameter: Literal["reference_image"]
    workflow_node_id: str
    workflow_node_class_type: Literal["LoadImage"]
    workflow_node_input_field: Literal["image"]
    conditioning_node_id: str
    conditioning_node_class_type: Literal["TextEncodeZImageOmni"]
    sampler_node_id: str
    sampler_node_class_type: Literal["KSampler"]
    binding_path_node_ids: list[str] = Field(min_length=4, max_length=4)

    @field_validator(
        "workflow_asset_relative_path",
        "mime_type",
        "resource_version",
        "workflow_parameter",
        "workflow_node_id",
        "workflow_node_class_type",
        "workflow_node_input_field",
        "conditioning_node_id",
        "conditioning_node_class_type",
        "sampler_node_id",
        "sampler_node_class_type",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("workflow_asset_relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        path = value.replace("\\", "/")
        if path.startswith("/") or ":" in path or ".." in path.split("/"):
            raise ValueError("workflow asset path must be task-relative")
        return path

    @field_validator("binding_path_node_ids")
    @classmethod
    def _validate_binding_path(cls, value: list[str]) -> list[str]:
        return _text_list(value, "binding_path_node_ids")

    @model_validator(mode="after")
    def _validate_binding_path_endpoints(self) -> "IdentityReferenceCondition":
        expected_resource_version = f"reference-image:{self.asset_sha256}"
        if self.resource_version != expected_resource_version:
            raise ValueError(
                "identity reference resource version must match its immutable digest"
            )
        if self.binding_path_node_ids[0] != self.workflow_node_id:
            raise ValueError("binding path must start at the workflow input node")
        if self.binding_path_node_ids[2] != self.conditioning_node_id:
            raise ValueError(
                "binding path must pass through one scale node before the conditioning node"
            )
        if self.binding_path_node_ids[-1] != self.sampler_node_id:
            raise ValueError("binding path must end at the sampler node")
        return self


class ContinuousSceneContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: str
    previous_frame_summary: str
    next_frame_summary: str
    continuity_anchors: list[str] = Field(default_factory=list)
    existing_fusion_decision: str
    existing_selected_fusion_method: str | None = None
    existing_final_manifestation: str | None = None
    existing_spatial_contact_and_lighting_relation: str | None = None

    @field_validator(
        "scene_id",
        "previous_frame_summary",
        "next_frame_summary",
        "existing_fusion_decision",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator(
        "existing_selected_fusion_method",
        "existing_final_manifestation",
        "existing_spatial_contact_and_lighting_relation",
        mode="before",
    )
    @classmethod
    def _validate_optional_text(cls, value: object, info) -> str | None:
        if value is None:
            return None
        return _text(value, info.field_name)

    @model_validator(mode="after")
    def _validate_existing_decision_shape(self) -> "ContinuousSceneContext":
        parts = (
            self.existing_selected_fusion_method,
            self.existing_final_manifestation,
            self.existing_spatial_contact_and_lighting_relation,
        )
        if any(part is not None for part in parts) and any(
            part is None for part in parts
        ):
            raise ValueError(
                "existing fusion decision fields must be all present or all absent"
            )
        return self

    @field_validator("continuity_anchors")
    @classmethod
    def _validate_anchors(cls, value: list[str]) -> list[str]:
        return _text_list(value, "continuity_anchors")


class FusionStageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    original_storyboard_text: str
    content_stage_output: ContentStageOutput
    identity_profile: VisualAnchorIdentityProfile
    identity_reference_condition: IdentityReferenceCondition
    continuous_scene_context: ContinuousSceneContext
    target_visual_style: str
    target_image_prompt_language: str
    review_feedback: list[str] = Field(default_factory=list)
    prompt_version: Literal[FUSION_STAGE_PROMPT_VERSION] = FUSION_STAGE_PROMPT_VERSION

    @field_validator(
        "frame_id",
        "original_storyboard_text",
        "target_visual_style",
        "target_image_prompt_language",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("review_feedback")
    @classmethod
    def _validate_feedback(cls, value: list[str]) -> list[str]:
        return _text_list(value, "review_feedback")

    @model_validator(mode="after")
    def _require_passed_content(self) -> "FusionStageInput":
        if self.content_stage_output.self_check != "pass":
            raise ValueError("content stage must pass before fusion")
        if (
            self.identity_reference_condition.resource_version
            not in self.identity_profile.source_asset_ids
        ):
            raise ValueError(
                "identity profile must be explicitly bound to the real reference resource"
            )
        return self


class ProtectedFactCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str
    preserved: bool
    final_image_evidence: str

    @field_validator("fact_id", "final_image_evidence", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)


class IdentityTraitCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trait: str
    preserved: bool
    final_prompt_evidence: str

    @field_validator("trait", "final_prompt_evidence", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)


class UnselectedCandidateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifestation: str
    audit_summary: str

    @field_validator("manifestation", "audit_summary", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)


class FusionStageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_fusion_method: str
    unselected_candidate_summaries: list[UnselectedCandidateSummary] = Field(
        min_length=1
    )
    content_stage_deviations: list[str] = Field(default_factory=list)
    non_core_reconstruction_summary: list[str] = Field(min_length=1)
    protected_fact_checks: list[ProtectedFactCheck] = Field(min_length=1)
    identity_trait_checks: list[IdentityTraitCheck] = Field(min_length=1)
    final_manifestation: str
    target_visual_anchor_instance_count: Literal[1]
    other_scene_elements_inherit_identity_features: Literal[False]
    single_instance_prompt_evidence: str
    spatial_contact_and_lighting_relation: str
    inherited_existing_fusion_decision: bool
    continuity_change_reason: str
    final_positive_prompt: str
    final_negative_prompt: str
    self_check: ReviewDecision
    self_check_failures: list[str] = Field(default_factory=list)

    @field_validator(
        "selected_fusion_method",
        "final_manifestation",
        "single_instance_prompt_evidence",
        "spatial_contact_and_lighting_relation",
        "continuity_change_reason",
        "final_positive_prompt",
        "final_negative_prompt",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator(
        "non_core_reconstruction_summary",
        "content_stage_deviations",
        "self_check_failures",
    )
    @classmethod
    def _validate_lists(cls, value: list[str], info) -> list[str]:
        return _text_list(value, info.field_name)

    @model_validator(mode="after")
    def _validate_result(self) -> "FusionStageOutput":
        candidate_manifestations = [
            candidate.manifestation.casefold()
            for candidate in self.unselected_candidate_summaries
        ]
        if len(set(candidate_manifestations)) != len(candidate_manifestations):
            raise ValueError(
                "unselected candidate manifestations must be unique"
            )
        selected_values = {
            self.selected_fusion_method.casefold(),
            self.final_manifestation.casefold(),
        }
        if any(
            manifestation in selected_values
            for manifestation in candidate_manifestations
        ):
            raise ValueError(
                "an unselected candidate cannot equal the selected fusion result"
            )
        if self.self_check == "pass" and self.self_check_failures:
            raise ValueError("a passed fusion result cannot contain failures")
        if self.self_check == "fail" and not self.self_check_failures:
            raise ValueError("a failed fusion result must contain failures")
        return self


class PreflightReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    original_storyboard_text: str
    content_stage_output: ContentStageOutput
    identity_profile: VisualAnchorIdentityProfile
    identity_reference_condition: IdentityReferenceCondition
    continuous_scene_context: ContinuousSceneContext
    fusion_stage_output: FusionStageOutput
    negative_prompt_supported: bool
    prompt_version: Literal[PREFLIGHT_REVIEW_PROMPT_VERSION] = PREFLIGHT_REVIEW_PROMPT_VERSION

    @field_validator("frame_id", "original_storyboard_text", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @model_validator(mode="after")
    def _validate_review_inputs(self) -> "PreflightReviewInput":
        if self.content_stage_output.self_check != "pass":
            raise ValueError("preflight review requires a passed content stage")
        if self.fusion_stage_output.self_check != "pass":
            raise ValueError("preflight review requires a passed fusion stage")
        if (
            self.identity_reference_condition.resource_version
            not in self.identity_profile.source_asset_ids
        ):
            raise ValueError(
                "preflight identity profile must remain bound to the real reference resource"
            )
        return self


class PreflightReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: ReviewDecision
    failures: list[str] = Field(default_factory=list)
    allowed_final_positive_prompt: str
    allowed_final_negative_prompt: str

    @field_validator("failures")
    @classmethod
    def _validate_failures(cls, value: list[str]) -> list[str]:
        return _text_list(value, "failures")

    @model_validator(mode="after")
    def _validate_result(self) -> "PreflightReviewOutput":
        positive = self.allowed_final_positive_prompt.strip()
        negative = self.allowed_final_negative_prompt.strip()
        object.__setattr__(self, "allowed_final_positive_prompt", positive)
        object.__setattr__(self, "allowed_final_negative_prompt", negative)
        if self.decision == "pass":
            if self.failures:
                raise ValueError("a passed preflight review cannot contain failures")
            if not positive:
                raise ValueError("a passed preflight review must allow a positive prompt")
        else:
            if not self.failures:
                raise ValueError("a failed preflight review must contain failures")
            if positive or negative:
                raise ValueError("a failed preflight review cannot allow prompts")
        return self


class ImageWorkflowExecutionContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    model_files: list[str] = Field(min_length=1)
    steps: int = Field(gt=0)
    cfg: float = Field(ge=0)
    sampler_name: str
    scheduler: str
    denoise: float = Field(gt=0, le=1)

    @field_validator("model_files")
    @classmethod
    def _validate_model_files(cls, value: list[str]) -> list[str]:
        result = _text_list(value, "model_files")
        if not result:
            raise ValueError("model_files must not be empty")
        return sorted(result)

    @field_validator("sampler_name", "scheduler", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)


class VisualAnchorImageGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_version: Literal[GENERATION_REQUEST_VERSION] = GENERATION_REQUEST_VERSION
    task_id: str
    frame_id: str
    generation_attempt: Literal[1] = 1
    random_seed: int = Field(ge=1, le=2**64 - 1)
    target_visual_anchor_instance_count: Literal[1] = 1
    selected_fusion_method: str
    final_manifestation: str
    protected_fact_checks: list[ProtectedFactCheck] = Field(min_length=1)
    identity_trait_checks: list[IdentityTraitCheck] = Field(min_length=1)
    single_instance_prompt_evidence: str
    final_positive_prompt: str
    final_negative_prompt: str
    identity_profile_id: str
    identity_display_name: str
    identity_core_traits: list[str] = Field(min_length=1)
    identity_resource_version: str
    identity_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_reference_condition: IdentityReferenceCondition
    content_stage_prompt_version: Literal[CONTENT_STAGE_PROMPT_VERSION]
    fusion_stage_prompt_version: Literal[FUSION_STAGE_PROMPT_VERSION]
    preflight_review_prompt_version: Literal[PREFLIGHT_REVIEW_PROMPT_VERSION]
    preflight_review_decision: Literal["pass"]
    workflow_key: str
    workflow_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_execution: ImageWorkflowExecutionContract

    @field_validator(
        "task_id",
        "frame_id",
        "selected_fusion_method",
        "final_manifestation",
        "single_instance_prompt_evidence",
        "final_positive_prompt",
        "identity_profile_id",
        "identity_display_name",
        "identity_resource_version",
        "workflow_key",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("final_negative_prompt", mode="before")
    @classmethod
    def _validate_optional_negative_prompt(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("final_negative_prompt must be a string")
        return " ".join(value.split())

    @field_validator("identity_core_traits")
    @classmethod
    def _validate_identity_core_traits(cls, value: list[str]) -> list[str]:
        result = _text_list(value, "identity_core_traits")
        if not result:
            raise ValueError("identity_core_traits must not be empty")
        return result

    @model_validator(mode="after")
    def _validate_image_model_boundary(self) -> "VisualAnchorImageGenerationRequest":
        prompt_boundary = (
            f"{self.final_positive_prompt}\n{self.final_negative_prompt}"
        ).casefold()
        if any(
            _contains_forbidden_term(prompt_boundary, term)
            for term in _FORBIDDEN_IMAGE_PROMPT_TERMS
        ):
            raise ValueError(
                "image generation prompts cannot contain candidate or planning language"
            )
        normalized_positive = " ".join(self.final_positive_prompt.split()).casefold()
        if any(not check.preserved for check in self.protected_fact_checks):
            raise ValueError(
                "image generation request cannot contain an unpreserved protected fact"
            )
        for check in self.protected_fact_checks:
            evidence = " ".join(check.final_image_evidence.split()).casefold()
            if evidence not in normalized_positive:
                raise ValueError(
                    "protected-fact evidence must be present in the image prompt"
                )
        trait_names = [check.trait.casefold() for check in self.identity_trait_checks]
        expected_trait_names = [trait.casefold() for trait in self.identity_core_traits]
        if (
            len(set(trait_names)) != len(trait_names)
            or set(trait_names) != set(expected_trait_names)
            or len(trait_names) != len(expected_trait_names)
        ):
            raise ValueError(
                "image generation request identity-trait checks must exactly cover the identity profile"
            )
        identity_evidence_values: list[str] = []
        normalized_identity_name = self.identity_display_name.casefold()
        for check in self.identity_trait_checks:
            if not check.preserved:
                raise ValueError(
                    "image generation request cannot drop a core identity trait"
                )
            evidence = " ".join(check.final_prompt_evidence.split()).casefold()
            if (
                evidence == normalized_identity_name
                or evidence not in normalized_positive
            ):
                raise ValueError(
                    "identity-trait evidence must be present in the image prompt"
                )
            identity_evidence_values.append(evidence)
        if len(set(identity_evidence_values)) != len(identity_evidence_values):
            raise ValueError(
                "each identity trait must have distinct visible prompt evidence"
            )
        instance_evidence = " ".join(
            self.single_instance_prompt_evidence.split()
        ).casefold()
        if instance_evidence not in normalized_positive or not any(
            _contains_forbidden_term(instance_evidence, term)
            for term in _SINGLE_INSTANCE_PROMPT_TERMS
        ):
            raise ValueError(
                "image generation request must explicitly describe exactly one identity instance"
            )
        if not _contains_forbidden_term(
            instance_evidence,
            normalized_identity_name,
        ):
            raise ValueError(
                "image generation request single-instance evidence must identify the selected identity"
            )
        expected_reference_version = (
            f"reference-image:{self.identity_reference_condition.asset_sha256}"
        )
        if self.identity_reference_condition.resource_version != expected_reference_version:
            raise ValueError(
                "identity reference resource version must match its immutable digest"
            )
        return self


class VisualAnchorTwoStageFrameResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    content_stage_input: ContentStageInput
    content_stage_output: ContentStageOutput
    fusion_stage_input: FusionStageInput
    fusion_stage_output: FusionStageOutput
    preflight_review_input: PreflightReviewInput
    preflight_review_output: PreflightReviewOutput
    generation_request: VisualAnchorImageGenerationRequest
    fusion_attempt_count: int = Field(ge=1, le=2)

    @field_validator("frame_id", mode="before")
    @classmethod
    def _validate_frame_id(cls, value: object) -> str:
        return _text(value, "frame_id")

    @model_validator(mode="after")
    def _validate_cross_stage_contract(self) -> "VisualAnchorTwoStageFrameResult":
        frame_ids = {
            self.frame_id,
            self.content_stage_input.frame_id,
            self.fusion_stage_input.frame_id,
            self.preflight_review_input.frame_id,
            self.generation_request.frame_id,
        }
        if len(frame_ids) != 1:
            raise ValueError("all visual-anchor stages must use the same frame id")
        original_texts = {
            self.content_stage_input.original_storyboard_text,
            self.fusion_stage_input.original_storyboard_text,
            self.preflight_review_input.original_storyboard_text,
        }
        if len(original_texts) != 1:
            raise ValueError(
                "all visual-anchor stages must preserve the exact storyboard text"
            )
        if self.fusion_stage_input.content_stage_output != self.content_stage_output:
            raise ValueError("fusion input must contain the exact content-stage output")
        if self.preflight_review_input.content_stage_output != self.content_stage_output:
            raise ValueError("preflight input must contain the exact content-stage output")
        if self.preflight_review_input.fusion_stage_output != self.fusion_stage_output:
            raise ValueError("preflight input must contain the exact fusion-stage output")
        if (
            self.preflight_review_input.continuous_scene_context
            != self.fusion_stage_input.continuous_scene_context
        ):
            raise ValueError("continuous-scene context must remain identical")
        if (
            self.fusion_stage_input.identity_profile
            != self.preflight_review_input.identity_profile
        ):
            raise ValueError("identity profile must remain identical across later stages")
        reference_condition = self.fusion_stage_input.identity_reference_condition
        if (
            reference_condition
            != self.preflight_review_input.identity_reference_condition
            or reference_condition
            != self.generation_request.identity_reference_condition
        ):
            raise ValueError("identity reference condition must remain identical")
        if self.preflight_review_output.decision != "pass":
            raise ValueError("generation request requires a passed preflight review")
        expected_negative_prompt = (
            self.fusion_stage_output.final_negative_prompt
            if self.preflight_review_input.negative_prompt_supported
            else ""
        )
        if (
            self.preflight_review_output.allowed_final_positive_prompt
            != self.fusion_stage_output.final_positive_prompt
            or self.preflight_review_output.allowed_final_negative_prompt
            != expected_negative_prompt
        ):
            raise ValueError("preflight review cannot modify the fusion prompts")
        if (
            self.preflight_review_output.allowed_final_positive_prompt
            != self.generation_request.final_positive_prompt
            or self.preflight_review_output.allowed_final_negative_prompt
            != self.generation_request.final_negative_prompt
        ):
            raise ValueError("generation prompts must exactly match preflight output")
        if (
            self.fusion_stage_output.target_visual_anchor_instance_count
            != self.generation_request.target_visual_anchor_instance_count
        ):
            raise ValueError("fusion and generation instance counts must match")
        if (
            self.generation_request.selected_fusion_method
            != self.fusion_stage_output.selected_fusion_method
            or self.generation_request.final_manifestation
            != self.fusion_stage_output.final_manifestation
            or self.generation_request.protected_fact_checks
            != self.fusion_stage_output.protected_fact_checks
            or self.generation_request.identity_trait_checks
            != self.fusion_stage_output.identity_trait_checks
            or self.generation_request.single_instance_prompt_evidence
            != self.fusion_stage_output.single_instance_prompt_evidence
        ):
            raise ValueError(
                "generation request must preserve the selected fusion, fact, identity, and single-instance evidence"
            )
        identity = self.fusion_stage_input.identity_profile
        if (
            self.generation_request.identity_profile_id != identity.profile_id
            or self.generation_request.identity_display_name != identity.display_name
            or self.generation_request.identity_core_traits
            != identity.core_identity_traits
            or self.generation_request.identity_resource_version
            != identity.identity_resource_version
            or self.generation_request.identity_content_sha256
            != identity.identity_content_sha256
        ):
            raise ValueError("generation identity version must match the fusion input")
        return self
