from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTENT_STAGE_PROMPT_VERSION = "visual_anchor_content_stage.v14"
FUSION_STAGE_PROMPT_VERSION = "visual_anchor_fusion_stage.v12"
GENERATION_REQUEST_VERSION = "visual_anchor_generation_request.v5"
ContentStagePromptVersion = Literal[
    "visual_anchor_content_stage.v5",
    "visual_anchor_content_stage.v6",
    "visual_anchor_content_stage.v7",
    "visual_anchor_content_stage.v8",
    "visual_anchor_content_stage.v9",
    "visual_anchor_content_stage.v10",
    "visual_anchor_content_stage.v11",
    "visual_anchor_content_stage.v12",
    "visual_anchor_content_stage.v13",
    CONTENT_STAGE_PROMPT_VERSION,
]
FusionStagePromptVersion = Literal[
    "visual_anchor_fusion_stage.v4",
    "visual_anchor_fusion_stage.v5",
    "visual_anchor_fusion_stage.v6",
    "visual_anchor_fusion_stage.v7",
    "visual_anchor_fusion_stage.v8",
    "visual_anchor_fusion_stage.v9",
    "visual_anchor_fusion_stage.v10",
    "visual_anchor_fusion_stage.v11",
    FUSION_STAGE_PROMPT_VERSION,
]

ContentSubjectCategory = Literal[
    "person",
    "animal",
    "object",
    "product",
    "place",
    "event",
]
ContentFactCategory = Literal[
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


def _optional_text(value: object, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return " ".join(value.split())


class TargetVisualStyle(BaseModel):
    """The single global style contract shared by both prompt stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str
    required_final_prompt_fragments: list[str] = Field(default_factory=list)
    required_negative_prompt_fragments: list[str] = Field(default_factory=list)

    @field_validator("description", mode="before")
    @classmethod
    def _validate_description(cls, value: object) -> str:
        return _text(value, "description")

    @field_validator(
        "required_final_prompt_fragments",
        "required_negative_prompt_fragments",
    )
    @classmethod
    def _validate_fragments(cls, value: list[str], info) -> list[str]:
        return _text_list(value, info.field_name)


class VisibleTextPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suppress_visible_text: bool = False
    required_positive_prompt_fragment: str = ""
    required_negative_prompt_fragment: str = ""

    @model_validator(mode="after")
    def _validate_policy(self) -> "VisibleTextPolicy":
        positive = " ".join(self.required_positive_prompt_fragment.split())
        negative = " ".join(self.required_negative_prompt_fragment.split())
        object.__setattr__(self, "required_positive_prompt_fragment", positive)
        object.__setattr__(self, "required_negative_prompt_fragment", negative)
        if self.suppress_visible_text and (not positive or not negative):
            raise ValueError(
                "visible-text suppression requires positive and negative prompt fragments"
            )
        if not self.suppress_visible_text and (positive or negative):
            raise ValueError(
                "visible-text prompt fragments require suppression to be enabled"
            )
        return self


class ContentFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ContentFactCategory
    statement: str

    @model_validator(mode="before")
    @classmethod
    def _discard_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        for field_name in (
            "fact_id",
            "subject_ids",
            "source_evidence",
            "pure_content_prompt_evidence",
        ):
            normalized.pop(field_name, None)
        return normalized

    @field_validator("statement", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)


_FLATTENED_CONTENT_FACT_FIELDS = (
    "category",
    "statement",
)


def _decode_flattened_content_facts(value: object) -> object:
    """Decode only complete key-value fact groups emitted by JSON-mode LLMs."""

    if not isinstance(value, list) or not value:
        return value
    if not all(isinstance(item, str) for item in value):
        return value
    if len(value) % len(_FLATTENED_CONTENT_FACT_FIELDS) != 0:
        return value

    decoded: list[dict[str, str]] = []
    group_size = len(_FLATTENED_CONTENT_FACT_FIELDS)
    for offset in range(0, len(value), group_size):
        group = value[offset : offset + group_size]
        fact: dict[str, str] = {}
        for item in group:
            field_name, separator, field_value = item.partition(":")
            normalized_field_name = field_name.strip()
            if (
                not separator
                or normalized_field_name not in _FLATTENED_CONTENT_FACT_FIELDS
                or normalized_field_name in fact
                or not field_value.strip()
            ):
                return value
            fact[normalized_field_name] = field_value.strip()
        if set(fact) != set(_FLATTENED_CONTENT_FACT_FIELDS):
            return value
        decoded.append(fact)
    return decoded


class ContentStageSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ContentSubjectCategory
    name: str
    identity: str
    quantity: int = Field(gt=0)
    action: str

    @model_validator(mode="before")
    @classmethod
    def _discard_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        for field_name in (
            "subject_id",
            "role",
            "source_evidence",
            "pure_content_prompt_evidence",
            "protected_facts",
        ):
            normalized.pop(field_name, None)
        return normalized

    @field_validator("name", "identity", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("action", mode="before")
    @classmethod
    def _validate_action(cls, value: object) -> str:
        return _optional_text(value, "action")


class ContentSubject(ContentStageSubject):
    """Compatibility name for persisted subjects without server-owned fields."""


class ContentCompositionPlan(BaseModel):
    """Concrete single-frame composition choices owned by the content stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shot_scale_and_camera: str
    foreground: str
    midground: str
    background: str
    visual_focus: str

    @field_validator("*", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)


class ContentStageModelOutput(BaseModel):
    """Identifier-free response contract for the content-stage model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    core_claim: str
    shot_purpose: str
    visual_evidence: list[str] = Field(min_length=1)
    frozen_moment: str
    primary_subject: ContentStageSubject
    secondary_subjects: list[ContentStageSubject] = Field(default_factory=list)
    subject_interaction: str
    composition_plan: ContentCompositionPlan
    adjacent_frame_difference: str
    scene_facts: list[ContentFact] = Field(
        default_factory=list,
        description=(
            "只保存 pure_content_prompt 直接呈现的跨主体或全场景事实对象数组；"
            "抽象事实若已转换成结果、隐喻或氛围且原事实不再直接出现，必须省略；"
            "每项必须是 ContentFact 对象，不能是字符串"
        ),
    )
    adjustable_non_core_content: list[str] = Field(default_factory=list)
    pure_content_prompt: str

    @model_validator(mode="before")
    @classmethod
    def _discard_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        legacy_facts = normalized.pop("protected_facts", None)
        if "scene_facts" not in normalized and isinstance(legacy_facts, (list, tuple)):
            normalized["scene_facts"] = [
                dict(fact)
                for fact in legacy_facts
                if isinstance(fact, Mapping)
            ]
        normalized.pop("self_check", None)
        normalized.pop("self_check_failures", None)
        return normalized

    @field_validator(
        "core_claim",
        "shot_purpose",
        "frozen_moment",
        "subject_interaction",
        "adjacent_frame_difference",
        "pure_content_prompt",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("visual_evidence")
    @classmethod
    def _validate_visual_evidence(cls, value: list[str]) -> list[str]:
        result = _text_list(value, "visual_evidence")
        if not result:
            raise ValueError("visual_evidence must not be empty")
        return result

    @field_validator("scene_facts", mode="before")
    @classmethod
    def _decode_scene_facts(cls, value: object) -> object:
        return _decode_flattened_content_facts(value)

    @field_validator("adjustable_non_core_content")
    @classmethod
    def _validate_list(cls, value: list[str], info) -> list[str]:
        return _text_list(value, info.field_name)

class ContentStageInput(BaseModel):
    """Identity-free input boundary for the content-only language-model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    original_storyboard_text: str
    article_context: str
    previous_frame_summary: str
    next_frame_summary: str
    target_visual_style: TargetVisualStyle
    target_image_prompt_language: str
    prompt_version: ContentStagePromptVersion = CONTENT_STAGE_PROMPT_VERSION

    @field_validator("*", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info):
        if info.field_name in {"prompt_version", "target_visual_style"}:
            return value
        return _text(value, info.field_name)


class ContentStageOutput(ContentStageModelOutput):
    """Persisted content-stage result with the same contract as the model output."""


class VisualAnchorIdentityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    display_name: str
    core_identity_traits: list[str] = Field(min_length=1)
    supporting_identity_traits: list[str] = Field(default_factory=list)
    forbidden_traits: list[str] = Field(default_factory=list)
    source_asset_ids: list[str] = Field(default_factory=list)
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
    identity_conditioning_mode: Literal["text_profile", "reference_image"]
    identity_reference_condition: IdentityReferenceCondition | None = None
    workflow_identity_condition_summary: str
    continuous_scene_context: ContinuousSceneContext
    target_visual_style: TargetVisualStyle
    visible_text_policy: VisibleTextPolicy = Field(default_factory=VisibleTextPolicy)
    negative_prompt_supported: bool
    target_image_prompt_language: str
    prompt_version: FusionStagePromptVersion = FUSION_STAGE_PROMPT_VERSION

    @model_validator(mode="before")
    @classmethod
    def _discard_legacy_review_feedback(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        normalized.pop("review_feedback", None)
        normalized.pop("required_single_instance_prompt_fragment", None)
        return normalized

    @field_validator(
        "frame_id",
        "original_storyboard_text",
        "workflow_identity_condition_summary",
        "target_image_prompt_language",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @model_validator(mode="after")
    def _validate_identity_conditioning(self) -> "FusionStageInput":
        if self.identity_conditioning_mode == "reference_image":
            if self.identity_reference_condition is None:
                raise ValueError(
                    "reference-image conditioning requires a real reference condition"
                )
            if (
                self.identity_reference_condition.resource_version
                not in self.identity_profile.source_asset_ids
            ):
                raise ValueError(
                    "identity profile must be explicitly bound to the real reference resource"
                )
        elif self.identity_reference_condition is not None:
            raise ValueError(
                "text-profile conditioning cannot include a reference-image condition"
            )
        return self


class FusionStageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_fusion_method: str
    final_manifestation: str
    identity_prompt_clause: str
    relative_scale_and_visual_weight: str
    carrier_and_material_relation: str
    scene_interaction: str
    spatial_contact_and_lighting_relation: str
    inherited_existing_fusion_decision: bool
    continuity_change_reason: str
    final_positive_prompt: str
    final_negative_prompt: str

    @model_validator(mode="before")
    @classmethod
    def _discard_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        for field_name in (
            "unselected_candidate_summaries",
            "content_stage_deviations",
            "non_core_reconstruction_summary",
            "protected_fact_checks",
            "primary_subject_preserved",
            "primary_subject_final_prompt_evidence",
            "visual_anchor_replaces_primary_subject",
            "identity_trait_checks",
            "target_visual_anchor_instance_count",
            "other_scene_elements_inherit_identity_features",
            "single_instance_prompt_evidence",
            "self_check",
            "self_check_failures",
        ):
            normalized.pop(field_name, None)
        return normalized

    @field_validator(
        "selected_fusion_method",
        "final_manifestation",
        "identity_prompt_clause",
        "relative_scale_and_visual_weight",
        "carrier_and_material_relation",
        "scene_interaction",
        "spatial_contact_and_lighting_relation",
        "final_positive_prompt",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("continuity_change_reason", mode="before")
    @classmethod
    def _validate_optional_continuity_change_reason(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("continuity_change_reason must be a string")
        return " ".join(value.split())

    @field_validator("final_negative_prompt", mode="before")
    @classmethod
    def _validate_optional_negative_prompt(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("final_negative_prompt must be a string")
        return " ".join(value.split())

    @model_validator(mode="after")
    def _validate_identity_prompt_clause(self) -> "FusionStageOutput":
        if self.identity_prompt_clause not in self.final_positive_prompt:
            raise ValueError(
                "identity_prompt_clause must appear verbatim in final_positive_prompt"
            )
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
    selected_fusion_method: str
    final_manifestation: str
    final_positive_prompt: str
    final_negative_prompt: str
    identity_profile_id: str
    identity_display_name: str
    identity_core_traits: list[str] = Field(min_length=1)
    identity_resource_version: str
    identity_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_conditioning_mode: Literal["text_profile", "reference_image"]
    identity_reference_condition: IdentityReferenceCondition | None = None
    target_visual_style: TargetVisualStyle
    visible_text_policy: VisibleTextPolicy = Field(default_factory=VisibleTextPolicy)
    content_stage_prompt_version: ContentStagePromptVersion
    fusion_stage_prompt_version: FusionStagePromptVersion
    negative_prompt_supported: bool
    workflow_key: str
    workflow_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_execution: ImageWorkflowExecutionContract

    @model_validator(mode="before")
    @classmethod
    def _discard_legacy_review_fields(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        normalized.pop("preflight_review_prompt_version", None)
        normalized.pop("preflight_review_decision", None)
        for field_name in (
            "target_visual_anchor_instance_count",
            "protected_fact_checks",
            "primary_subject_name",
            "primary_subject_preserved",
            "primary_subject_final_prompt_evidence",
            "visual_anchor_replaces_primary_subject",
            "identity_trait_checks",
            "single_instance_prompt_evidence",
        ):
            normalized.pop(field_name, None)
        if normalized.get("request_version") in {
            "visual_anchor_generation_request.v3",
            "visual_anchor_generation_request.v4",
        }:
            normalized["request_version"] = GENERATION_REQUEST_VERSION
        return normalized

    @field_validator(
        "task_id",
        "frame_id",
        "selected_fusion_method",
        "final_manifestation",
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


def _upgrade_legacy_content_stage_output(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    normalized = dict(value)
    pure_prompt = str(normalized.get("pure_content_prompt") or "").strip()
    core_claim = str(normalized.get("core_claim") or pure_prompt).strip()
    legacy_detail = pure_prompt or core_claim or "旧契约未记录完整画面"
    facts = normalized.get("scene_facts")
    visible_facts = (
        [
            str(fact.get("statement") or "").strip()
            for fact in facts
            if isinstance(fact, Mapping)
        ]
        if isinstance(facts, (list, tuple))
        else []
    )
    visible_facts = [fact for fact in visible_facts if fact]
    normalized.setdefault("shot_purpose", core_claim or legacy_detail)
    normalized.setdefault("visual_evidence", visible_facts or [legacy_detail])
    normalized.setdefault("frozen_moment", legacy_detail)
    normalized.setdefault(
        "subject_interaction",
        f"旧契约未单独记录互动关系；完整关系见纯内容提示词：{legacy_detail}",
    )
    legacy_composition = (
        f"旧契约未单独记录该构图字段；完整构图见纯内容提示词：{legacy_detail}"
    )
    normalized.setdefault(
        "composition_plan",
        {
            "shot_scale_and_camera": legacy_composition,
            "foreground": legacy_composition,
            "midground": legacy_composition,
            "background": legacy_composition,
            "visual_focus": legacy_composition,
        },
    )
    normalized.setdefault(
        "adjacent_frame_difference",
        "旧契约未单独记录相邻镜头差异",
    )
    return normalized


def _upgrade_legacy_fusion_stage_output(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    normalized = dict(value)
    final_prompt = str(normalized.get("final_positive_prompt") or "").strip()
    manifestation = str(normalized.get("final_manifestation") or "").strip()
    spatial_relation = str(
        normalized.get("spatial_contact_and_lighting_relation") or ""
    ).strip()
    normalized.setdefault("identity_prompt_clause", final_prompt)
    normalized.setdefault(
        "relative_scale_and_visual_weight",
        f"旧契约未单独记录相对尺度与视觉权重；表现形态：{manifestation}",
    )
    normalized.setdefault(
        "carrier_and_material_relation",
        f"旧契约未单独记录载体与材质关系；表现形态：{manifestation}",
    )
    normalized.setdefault(
        "scene_interaction",
        f"旧契约未单独记录场景互动关系；空间关系：{spatial_relation}",
    )
    return normalized


class VisualAnchorTwoStageFrameResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    content_stage_input: ContentStageInput
    content_stage_output: ContentStageOutput
    fusion_stage_input: FusionStageInput
    fusion_stage_output: FusionStageOutput
    generation_request: VisualAnchorImageGenerationRequest

    @model_validator(mode="before")
    @classmethod
    def _discard_legacy_review_fields(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        normalized.pop("preflight_review_input", None)
        normalized.pop("preflight_review_output", None)
        normalized.pop("content_attempt_count", None)
        normalized.pop("content_retry_validation_codes", None)
        normalized.pop("fusion_attempt_count", None)
        content_input = normalized.get("content_stage_input")
        content_version = (
            content_input.get("prompt_version")
            if isinstance(content_input, Mapping)
            else None
        )
        fusion_input = normalized.get("fusion_stage_input")
        fusion_version = (
            fusion_input.get("prompt_version")
            if isinstance(fusion_input, Mapping)
            else None
        )
        if content_version != CONTENT_STAGE_PROMPT_VERSION:
            normalized["content_stage_output"] = _upgrade_legacy_content_stage_output(
                normalized.get("content_stage_output")
            )
            if isinstance(fusion_input, Mapping):
                normalized_fusion_input = dict(fusion_input)
                normalized_fusion_input["content_stage_output"] = (
                    _upgrade_legacy_content_stage_output(
                        normalized_fusion_input.get("content_stage_output")
                    )
                )
                normalized["fusion_stage_input"] = normalized_fusion_input
        if fusion_version != FUSION_STAGE_PROMPT_VERSION:
            normalized["fusion_stage_output"] = _upgrade_legacy_fusion_stage_output(
                normalized.get("fusion_stage_output")
            )
        return normalized

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
            self.generation_request.frame_id,
        }
        if len(frame_ids) != 1:
            raise ValueError("all visual-anchor stages must use the same frame id")
        original_texts = {
            self.content_stage_input.original_storyboard_text,
            self.fusion_stage_input.original_storyboard_text,
        }
        if len(original_texts) != 1:
            raise ValueError(
                "all visual-anchor stages must preserve the exact storyboard text"
            )
        if (
            self.generation_request.content_stage_prompt_version
            != self.content_stage_input.prompt_version
            or self.generation_request.fusion_stage_prompt_version
            != self.fusion_stage_input.prompt_version
        ):
            raise ValueError(
                "generation request prompt versions must match their stage inputs"
            )
        if self.fusion_stage_input.content_stage_output != self.content_stage_output:
            raise ValueError("fusion input must contain the exact content-stage output")
        if (
            self.fusion_stage_input.identity_conditioning_mode
            != self.generation_request.identity_conditioning_mode
        ):
            raise ValueError("identity conditioning mode must remain identical")
        reference_condition = self.fusion_stage_input.identity_reference_condition
        if (
            reference_condition
            != self.generation_request.identity_reference_condition
        ):
            raise ValueError("identity reference condition must remain identical")
        if (
            self.fusion_stage_output.final_positive_prompt
            != self.generation_request.final_positive_prompt
            or self.fusion_stage_output.final_negative_prompt
            != self.generation_request.final_negative_prompt
        ):
            raise ValueError("generation prompts must exactly match fusion output")
        if (
            self.generation_request.selected_fusion_method
            != self.fusion_stage_output.selected_fusion_method
            or self.generation_request.final_manifestation
            != self.fusion_stage_output.final_manifestation
        ):
            raise ValueError(
                "generation request must preserve the selected fusion result"
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
        if (
            self.fusion_stage_input.target_visual_style
            != self.generation_request.target_visual_style
            or self.fusion_stage_input.visible_text_policy
            != self.generation_request.visible_text_policy
        ):
            raise ValueError(
                "style and visible-text policies must remain identical across later stages"
            )
        return self
