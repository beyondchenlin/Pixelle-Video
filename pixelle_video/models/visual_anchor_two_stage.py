from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTENT_STAGE_PROMPT_VERSION = "visual_anchor_content_stage.v15"
FUSION_STAGE_PROMPT_VERSION = "visual_anchor_fusion_stage.v13"
GENERATION_REQUEST_VERSION = "visual_anchor_generation_request.v6"
CONTENT_PROMPT_ASSEMBLY_VERSION = "visual_anchor_content_prompt_assembly.v1"
FUSION_PROMPT_ASSEMBLY_VERSION = "visual_anchor_fusion_prompt_assembly.v1"
_PLANNING_TEXT_MAX_LENGTH = 1200
_PROMPT_TEXT_MAX_LENGTH = 12000
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
    "visual_anchor_content_stage.v14",
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
    "visual_anchor_fusion_stage.v12",
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

    shot_scale_and_camera: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)
    foreground: str = Field(default="", max_length=_PLANNING_TEXT_MAX_LENGTH)
    midground: str = Field(default="", max_length=_PLANNING_TEXT_MAX_LENGTH)
    background: str = Field(default="", max_length=_PLANNING_TEXT_MAX_LENGTH)
    visual_focus: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)

    @field_validator("shot_scale_and_camera", "visual_focus", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("foreground", "midground", "background", mode="before")
    @classmethod
    def _validate_optional_layer(cls, value: object, info) -> str:
        return _optional_text(value, info.field_name)

    @model_validator(mode="after")
    def _validate_visible_layers(self) -> "ContentCompositionPlan":
        if not any((self.foreground, self.midground, self.background)):
            raise ValueError("composition_plan must contain at least one visible layer")
        return self


class _ContentStageCommonOutput(BaseModel):
    """Shared factual boundary for current and historical content outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    core_claim: str
    primary_subject: ContentStageSubject
    secondary_subjects: list[ContentStageSubject] = Field(
        default_factory=list,
        max_length=8,
    )
    scene_facts: list[ContentFact] = Field(
        default_factory=list,
        max_length=16,
        description=(
            "只保存纯内容画面直接呈现的跨主体或全场景事实对象数组；"
            "抽象事实若已转换成结果、隐喻或氛围且原事实不再直接出现，必须省略；"
            "每项必须是 ContentFact 对象，不能是字符串"
        ),
    )
    adjustable_non_core_content: list[str] = Field(
        default_factory=list,
        max_length=12,
    )

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

    @field_validator("core_claim", mode="before")
    @classmethod
    def _validate_core_claim(cls, value: object) -> str:
        return _text(value, "core_claim")

    @field_validator("scene_facts", mode="before")
    @classmethod
    def _decode_scene_facts(cls, value: object) -> object:
        return _decode_flattened_content_facts(value)

    @field_validator("adjustable_non_core_content")
    @classmethod
    def _validate_adjustable_content(cls, value: list[str]) -> list[str]:
        return _text_list(value, "adjustable_non_core_content")


class LegacyContentStageOutput(_ContentStageCommonOutput):
    """Historical pre-v14 output preserved without invented planning fields."""

    pure_content_prompt: str

    @field_validator("pure_content_prompt", mode="before")
    @classmethod
    def _validate_prompt(cls, value: object) -> str:
        return _text(value, "pure_content_prompt")


class LegacyContentStageOutputV14(_ContentStageCommonOutput):
    """Read-only v14 planning result kept truthful during regeneration."""

    shot_purpose: str
    visual_evidence: list[str] = Field(min_length=1)
    frozen_moment: str
    subject_interaction: str
    composition_plan: ContentCompositionPlan
    adjacent_frame_difference: str
    pure_content_prompt: str

    @field_validator(
        "shot_purpose",
        "frozen_moment",
        "subject_interaction",
        "adjacent_frame_difference",
        "pure_content_prompt",
        mode="before",
    )
    @classmethod
    def _validate_planning_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("visual_evidence")
    @classmethod
    def _validate_visual_evidence(cls, value: list[str]) -> list[str]:
        result = _text_list(value, "visual_evidence")
        if not result:
            raise ValueError("visual_evidence must not be empty")
        return result


class ContentStageModelOutput(_ContentStageCommonOutput):
    """Current model response: visual decisions only, without a free-form final prompt."""

    shot_purpose: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)
    renderable_story_beats: list[str] = Field(min_length=1, max_length=6)
    decisive_moment: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)
    content_subject_interaction: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)
    composition_plan: ContentCompositionPlan
    adjacent_shot_distinction: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)

    @field_validator(
        "shot_purpose",
        "decisive_moment",
        "content_subject_interaction",
        "adjacent_shot_distinction",
        mode="before",
    )
    @classmethod
    def _validate_planning_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("renderable_story_beats")
    @classmethod
    def _validate_renderable_story_beats(cls, value: list[str]) -> list[str]:
        result = _text_list(value, "renderable_story_beats")
        if not result:
            raise ValueError("renderable_story_beats must not be empty")
        return result


class ContentStageOutput(ContentStageModelOutput):
    """Persisted current result with a deterministic server-assembled prompt."""

    prompt_assembly_version: Literal[CONTENT_PROMPT_ASSEMBLY_VERSION]
    pure_content_prompt: str = Field(max_length=_PROMPT_TEXT_MAX_LENGTH)

    @field_validator("pure_content_prompt", mode="before")
    @classmethod
    def _validate_prompt(cls, value: object) -> str:
        return _text(value, "pure_content_prompt")


ReadableContentStageOutput = (
    ContentStageOutput | LegacyContentStageOutputV14 | LegacyContentStageOutput
)

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
    existing_identity_prompt_clause: str | None = None
    existing_relative_scale_and_visual_weight: str | None = None
    existing_support_carrier_and_material_relation: str | None = None
    existing_visual_identity_scene_interaction: str | None = None
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
        "existing_identity_prompt_clause",
        "existing_relative_scale_and_visual_weight",
        "existing_support_carrier_and_material_relation",
        "existing_visual_identity_scene_interaction",
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
        legacy_parts = (
            self.existing_selected_fusion_method,
            self.existing_final_manifestation,
            self.existing_spatial_contact_and_lighting_relation,
        )
        current_parts = (
            self.existing_identity_prompt_clause,
            self.existing_relative_scale_and_visual_weight,
            self.existing_support_carrier_and_material_relation,
            self.existing_visual_identity_scene_interaction,
        )
        if any(part is not None for part in legacy_parts) and any(
            part is None for part in legacy_parts
        ):
            raise ValueError(
                "legacy existing fusion decision fields must be all present or all absent"
            )
        if any(part is not None for part in current_parts) and any(
            part is None for part in current_parts
        ):
            raise ValueError(
                "current existing fusion decision fields must be all present or all absent"
            )
        if any(part is not None for part in current_parts) and any(
            part is None for part in legacy_parts
        ):
            raise ValueError("current existing fusion details require the base decision")
        return self

    @field_validator("continuity_anchors")
    @classmethod
    def _validate_anchors(cls, value: list[str]) -> list[str]:
        return _text_list(value, "continuity_anchors")


class FusionStageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    original_storyboard_text: str
    content_stage_output: ReadableContentStageOutput
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


class _FusionStageCommonOutput(BaseModel):
    """Fields shared by current and historical fusion-stage outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_fusion_method: str
    final_manifestation: str
    spatial_contact_and_lighting_relation: str
    inherited_existing_fusion_decision: bool
    continuity_change_reason: str

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
        "spatial_contact_and_lighting_relation",
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

class LegacyFusionStageOutput(_FusionStageCommonOutput):
    """Historical pre-v12 output preserved without fabricated manifestation data."""

    final_positive_prompt: str
    final_negative_prompt: str

    @field_validator("final_positive_prompt", mode="before")
    @classmethod
    def _validate_positive_prompt(cls, value: object) -> str:
        return _text(value, "final_positive_prompt")

    @field_validator("final_negative_prompt", mode="before")
    @classmethod
    def _validate_negative_prompt(cls, value: object) -> str:
        return _optional_text(value, "final_negative_prompt")


class LegacyFusionStageOutputV12(_FusionStageCommonOutput):
    """Read-only v12 output kept truthful during regeneration."""

    identity_prompt_clause: str
    relative_scale_and_visual_weight: str
    carrier_and_material_relation: str
    scene_interaction: str
    final_positive_prompt: str
    final_negative_prompt: str

    @field_validator(
        "identity_prompt_clause",
        "relative_scale_and_visual_weight",
        "carrier_and_material_relation",
        "scene_interaction",
        "final_positive_prompt",
        mode="before",
    )
    @classmethod
    def _validate_v12_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("final_negative_prompt", mode="before")
    @classmethod
    def _validate_negative_prompt(cls, value: object) -> str:
        return _optional_text(value, "final_negative_prompt")

    @model_validator(mode="after")
    def _validate_identity_prompt_clause(self) -> "LegacyFusionStageOutputV12":
        if self.identity_prompt_clause not in self.final_positive_prompt:
            raise ValueError(
                "identity_prompt_clause must appear verbatim in final_positive_prompt"
            )
        return self


class FusionStageModelOutput(_FusionStageCommonOutput):
    """Current model response: one manifestation decision plus prompt insertion context."""

    relative_scale_and_visual_weight: str = Field(
        max_length=_PLANNING_TEXT_MAX_LENGTH
    )
    support_carrier_and_material_relation: str = Field(
        max_length=_PLANNING_TEXT_MAX_LENGTH
    )
    visual_identity_scene_interaction: str = Field(
        max_length=_PLANNING_TEXT_MAX_LENGTH
    )
    final_scene_prompt_prefix: str = Field(max_length=_PROMPT_TEXT_MAX_LENGTH)
    final_scene_prompt_suffix: str = Field(default="", max_length=_PROMPT_TEXT_MAX_LENGTH)
    scene_negative_prompt: str = Field(default="", max_length=_PROMPT_TEXT_MAX_LENGTH)

    @field_validator(
        "relative_scale_and_visual_weight",
        "support_carrier_and_material_relation",
        "visual_identity_scene_interaction",
        "final_scene_prompt_prefix",
        mode="before",
    )
    @classmethod
    def _validate_current_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("final_scene_prompt_suffix", mode="before")
    @classmethod
    def _validate_optional_suffix(cls, value: object) -> str:
        return _optional_text(value, "final_scene_prompt_suffix")

    @field_validator("scene_negative_prompt", mode="before")
    @classmethod
    def _validate_scene_negative_prompt(cls, value: object) -> str:
        return _optional_text(value, "scene_negative_prompt")


class FusionStageOutput(FusionStageModelOutput):
    """Persisted current result with deterministic identity and prompt assembly."""

    prompt_assembly_version: Literal[FUSION_PROMPT_ASSEMBLY_VERSION]
    identity_prompt_clause: str = Field(max_length=_PROMPT_TEXT_MAX_LENGTH)
    final_positive_prompt: str = Field(max_length=_PROMPT_TEXT_MAX_LENGTH)
    final_negative_prompt: str = Field(default="", max_length=_PROMPT_TEXT_MAX_LENGTH)

    @field_validator("identity_prompt_clause", "final_positive_prompt", mode="before")
    @classmethod
    def _validate_assembled_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("final_negative_prompt", mode="before")
    @classmethod
    def _validate_final_negative_prompt(cls, value: object) -> str:
        return _optional_text(value, "final_negative_prompt")

    @model_validator(mode="after")
    def _validate_identity_prompt_clause(self) -> "FusionStageOutput":
        if self.identity_prompt_clause not in self.final_positive_prompt:
            raise ValueError(
                "identity_prompt_clause must appear verbatim in final_positive_prompt"
            )
        return self


ReadableFusionStageOutput = (
    FusionStageOutput | LegacyFusionStageOutputV12 | LegacyFusionStageOutput
)

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


class VisualAnchorPromptAssemblyTrace(BaseModel):
    """Exact current prompt decisions carried into generation and audit artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assembly_version: Literal[FUSION_PROMPT_ASSEMBLY_VERSION]
    final_scene_prompt_prefix: str
    identity_prompt_clause: str
    final_scene_prompt_suffix: str
    relative_scale_and_visual_weight: str
    support_carrier_and_material_relation: str
    visual_identity_scene_interaction: str
    spatial_contact_and_lighting_relation: str
    scene_negative_prompt: str = ""

    @field_validator(
        "final_scene_prompt_prefix",
        "identity_prompt_clause",
        "relative_scale_and_visual_weight",
        "support_carrier_and_material_relation",
        "visual_identity_scene_interaction",
        "spatial_contact_and_lighting_relation",
        mode="before",
    )
    @classmethod
    def _validate_required_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("final_scene_prompt_suffix", mode="before")
    @classmethod
    def _validate_suffix(cls, value: object) -> str:
        return _optional_text(value, "final_scene_prompt_suffix")

    @field_validator("scene_negative_prompt", mode="before")
    @classmethod
    def _validate_scene_negative_prompt(cls, value: object) -> str:
        return _optional_text(value, "scene_negative_prompt")


class VisualAnchorImageGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_version: Literal[GENERATION_REQUEST_VERSION] = GENERATION_REQUEST_VERSION
    task_id: str
    frame_id: str
    generation_attempt: Literal[1] = 1
    random_seed: int = Field(ge=1, le=2**64 - 1)
    selected_fusion_method: str
    final_manifestation: str
    prompt_assembly_trace: VisualAnchorPromptAssemblyTrace | None = None
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
            "visual_anchor_generation_request.v5",
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

    @model_validator(mode="after")
    def _validate_prompt_assembly_trace(self) -> "VisualAnchorImageGenerationRequest":
        if self.fusion_stage_prompt_version == FUSION_STAGE_PROMPT_VERSION:
            if self.prompt_assembly_trace is None:
                raise ValueError(
                    "current fusion prompt version requires prompt_assembly_trace"
                )
        if (
            self.prompt_assembly_trace is not None
            and self.prompt_assembly_trace.identity_prompt_clause
            not in self.final_positive_prompt
        ):
            raise ValueError(
                "generation request prompt must contain its identity prompt clause"
            )
        return self


def _join_prompt_fragments(values: list[str]) -> str:
    fragments: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value or "").split()).strip(" ，,；;")
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        fragments.append(normalized)
    return "；".join(fragments)


def assemble_content_stage_prompt(
    output: ContentStageModelOutput,
    *,
    target_visual_style: TargetVisualStyle,
) -> str:
    """Build the content prompt exclusively from validated visual decisions."""

    composition = output.composition_plan
    subject_fragments: list[str] = []
    for subject in (output.primary_subject, *output.secondary_subjects):
        subject_fragments.extend((subject.name, subject.identity, subject.action))
    return _join_prompt_fragments(
        [
            composition.shot_scale_and_camera,
            *subject_fragments,
            output.decisive_moment,
            output.content_subject_interaction,
            *output.renderable_story_beats,
            composition.foreground,
            composition.midground,
            composition.background,
            composition.visual_focus,
            target_visual_style.description,
            *target_visual_style.required_final_prompt_fragments,
        ]
    )


def assemble_identity_prompt_clause(
    output: FusionStageModelOutput,
    *,
    identity_profile: VisualAnchorIdentityProfile,
    target_image_prompt_language: str,
) -> str:
    """Build one prompt-ready manifestation clause from the chosen relationships."""

    normalized_language = target_image_prompt_language.casefold()
    single_instance = (
        f"整幅画只出现一个可识别的{identity_profile.display_name}视觉身份实例"
        if "中文" in normalized_language or "chinese" in normalized_language
        else (
            "exactly one recognizable visual identity instance of "
            f"{identity_profile.display_name} in the entire image"
        )
    )
    return _join_prompt_fragments(
        [
            output.final_manifestation,
            *identity_profile.core_identity_traits,
            output.relative_scale_and_visual_weight,
            output.support_carrier_and_material_relation,
            output.visual_identity_scene_interaction,
            output.spatial_contact_and_lighting_relation,
            single_instance,
        ]
    )


def assemble_fusion_positive_prompt(
    output: FusionStageModelOutput,
    *,
    identity_prompt_clause: str,
    identity_profile: VisualAnchorIdentityProfile,
    target_visual_style: TargetVisualStyle,
    visible_text_policy: VisibleTextPolicy,
    negative_prompt_supported: bool,
    target_image_prompt_language: str,
) -> str:
    """Insert the identity decision inside the scene and append deterministic policies."""

    return _join_prompt_fragments(
        [
            output.final_scene_prompt_prefix,
            identity_prompt_clause,
            output.final_scene_prompt_suffix,
            target_visual_style.description,
            *target_visual_style.required_final_prompt_fragments,
            visible_text_policy.required_positive_prompt_fragment,
            *(
                []
                if negative_prompt_supported
                else _positive_identity_avoidance_fragments(
                    identity_profile,
                    target_image_prompt_language=target_image_prompt_language,
                )
            ),
        ]
    )


def assemble_fusion_negative_prompt(
    output: FusionStageModelOutput,
    *,
    identity_profile: VisualAnchorIdentityProfile,
    target_visual_style: TargetVisualStyle,
    visible_text_policy: VisibleTextPolicy,
    negative_prompt_supported: bool,
) -> str:
    if not negative_prompt_supported:
        return ""
    return _join_prompt_fragments(
        [
            output.scene_negative_prompt,
            *identity_profile.forbidden_traits,
            *target_visual_style.required_negative_prompt_fragments,
            visible_text_policy.required_negative_prompt_fragment,
        ]
    )


def _positive_identity_avoidance_fragments(
    identity_profile: VisualAnchorIdentityProfile,
    *,
    target_image_prompt_language: str,
) -> list[str]:
    normalized_language = target_image_prompt_language.casefold()
    use_chinese = "中文" in normalized_language or "chinese" in normalized_language
    result: list[str] = []
    for trait in identity_profile.forbidden_traits:
        normalized = " ".join(trait.split())
        if not normalized:
            continue
        if use_chinese:
            result.append(
                normalized
                if normalized.startswith(("禁止", "不得", "避免"))
                else f"禁止出现{normalized}"
            )
        else:
            result.append(
                normalized
                if normalized.casefold().startswith(("avoid ", "no ", "do not "))
                else f"avoid {normalized}"
            )
    return result


def prompt_assembly_trace_from_fusion_output(
    output: FusionStageOutput,
) -> VisualAnchorPromptAssemblyTrace:
    return VisualAnchorPromptAssemblyTrace(
        assembly_version=FUSION_PROMPT_ASSEMBLY_VERSION,
        final_scene_prompt_prefix=output.final_scene_prompt_prefix,
        identity_prompt_clause=output.identity_prompt_clause,
        final_scene_prompt_suffix=output.final_scene_prompt_suffix,
        relative_scale_and_visual_weight=output.relative_scale_and_visual_weight,
        support_carrier_and_material_relation=(
            output.support_carrier_and_material_relation
        ),
        visual_identity_scene_interaction=(
            output.visual_identity_scene_interaction
        ),
        spatial_contact_and_lighting_relation=(
            output.spatial_contact_and_lighting_relation
        ),
        scene_negative_prompt=output.scene_negative_prompt,
    )


class VisualAnchorTwoStageFrameResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    content_stage_input: ContentStageInput
    content_stage_output: ReadableContentStageOutput
    fusion_stage_input: FusionStageInput
    fusion_stage_output: ReadableFusionStageOutput
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
        content_version = self.content_stage_input.prompt_version
        if content_version == CONTENT_STAGE_PROMPT_VERSION:
            if not isinstance(self.content_stage_output, ContentStageOutput):
                raise ValueError(
                    "current content prompt version requires current assembled output"
                )
            expected_content_prompt = assemble_content_stage_prompt(
                self.content_stage_output,
                target_visual_style=self.content_stage_input.target_visual_style,
            )
            if self.content_stage_output.pure_content_prompt != expected_content_prompt:
                raise ValueError(
                    "content prompt differs from deterministic planning assembly"
                )
        elif content_version == "visual_anchor_content_stage.v14":
            if not isinstance(self.content_stage_output, LegacyContentStageOutputV14):
                raise ValueError("v14 content prompt requires its historical output shape")
        elif not isinstance(self.content_stage_output, LegacyContentStageOutput):
            raise ValueError("historical content prompt requires its historical output shape")

        fusion_version = self.fusion_stage_input.prompt_version
        if fusion_version == FUSION_STAGE_PROMPT_VERSION:
            if not isinstance(self.fusion_stage_output, FusionStageOutput):
                raise ValueError(
                    "current fusion prompt version requires current assembled output"
                )
            identity_clause = assemble_identity_prompt_clause(
                self.fusion_stage_output,
                identity_profile=self.fusion_stage_input.identity_profile,
                target_image_prompt_language=(
                    self.fusion_stage_input.target_image_prompt_language
                ),
            )
            expected_positive_prompt = assemble_fusion_positive_prompt(
                self.fusion_stage_output,
                identity_prompt_clause=identity_clause,
                identity_profile=self.fusion_stage_input.identity_profile,
                target_visual_style=self.fusion_stage_input.target_visual_style,
                visible_text_policy=self.fusion_stage_input.visible_text_policy,
                negative_prompt_supported=(
                    self.fusion_stage_input.negative_prompt_supported
                ),
                target_image_prompt_language=(
                    self.fusion_stage_input.target_image_prompt_language
                ),
            )
            expected_negative_prompt = assemble_fusion_negative_prompt(
                self.fusion_stage_output,
                identity_profile=self.fusion_stage_input.identity_profile,
                target_visual_style=self.fusion_stage_input.target_visual_style,
                visible_text_policy=self.fusion_stage_input.visible_text_policy,
                negative_prompt_supported=(
                    self.fusion_stage_input.negative_prompt_supported
                ),
            )
            if self.fusion_stage_output.identity_prompt_clause != identity_clause:
                raise ValueError(
                    "identity prompt clause differs from deterministic manifestation assembly"
                )
            if (
                self.fusion_stage_output.final_positive_prompt
                != expected_positive_prompt
                or self.fusion_stage_output.final_negative_prompt
                != expected_negative_prompt
            ):
                raise ValueError(
                    "fusion prompts differ from deterministic prompt assembly"
                )
            self._validate_current_continuity_contract()
        elif fusion_version == "visual_anchor_fusion_stage.v12":
            if not isinstance(self.fusion_stage_output, LegacyFusionStageOutputV12):
                raise ValueError("v12 fusion prompt requires its historical output shape")
        elif not isinstance(self.fusion_stage_output, LegacyFusionStageOutput):
            raise ValueError("historical fusion prompt requires its historical output shape")
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
        if isinstance(self.fusion_stage_output, FusionStageOutput):
            expected_trace = prompt_assembly_trace_from_fusion_output(
                self.fusion_stage_output
            )
            if self.generation_request.prompt_assembly_trace != expected_trace:
                raise ValueError(
                    "generation request must preserve the exact prompt assembly trace"
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

    def _validate_current_continuity_contract(self) -> None:
        output = self.fusion_stage_output
        if not isinstance(output, FusionStageOutput):
            raise ValueError("current continuity validation requires current output")
        context = self.fusion_stage_input.continuous_scene_context
        has_existing = context.existing_selected_fusion_method is not None
        current_existing_fields = (
            context.existing_identity_prompt_clause,
            context.existing_relative_scale_and_visual_weight,
            context.existing_support_carrier_and_material_relation,
            context.existing_visual_identity_scene_interaction,
        )
        if has_existing and any(value is None for value in current_existing_fields):
            raise ValueError(
                "current fusion continuity requires the complete previous decision"
            )
        if not has_existing:
            if output.inherited_existing_fusion_decision:
                raise ValueError("first or independent frame cannot inherit a decision")
            if output.continuity_change_reason:
                raise ValueError(
                    "continuity_change_reason must be empty without an existing decision"
                )
            return
        if output.inherited_existing_fusion_decision:
            if output.continuity_change_reason:
                raise ValueError(
                    "directly inherited decisions cannot include a change reason"
                )
            inherited_pairs = (
                (output.selected_fusion_method, context.existing_selected_fusion_method),
                (output.final_manifestation, context.existing_final_manifestation),
                (output.identity_prompt_clause, context.existing_identity_prompt_clause),
                (
                    output.relative_scale_and_visual_weight,
                    context.existing_relative_scale_and_visual_weight,
                ),
                (
                    output.support_carrier_and_material_relation,
                    context.existing_support_carrier_and_material_relation,
                ),
                (
                    output.visual_identity_scene_interaction,
                    context.existing_visual_identity_scene_interaction,
                ),
                (
                    output.spatial_contact_and_lighting_relation,
                    context.existing_spatial_contact_and_lighting_relation,
                ),
            )
            if any(current != previous for current, previous in inherited_pairs):
                raise ValueError(
                    "directly inherited fusion decision must match every previous field"
                )
        elif not output.continuity_change_reason:
            raise ValueError(
                "changing an existing fusion decision requires continuity_change_reason"
            )
