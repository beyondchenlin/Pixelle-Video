from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pixelle_video.models.visual_signature_emphasis import VisualSignatureEmphasis

CONTENT_STAGE_PROMPT_VERSION = "visual_anchor_content_stage.v21"
FUSION_STAGE_PROMPT_VERSION = "visual_anchor_fusion_stage.v29"
FINALIZATION_STAGE_PROMPT_VERSION = "visual_anchor_finalization_stage.v10"
GENERATION_REQUEST_VERSION = "visual_anchor_generation_request.v11"
CONTENT_PROMPT_ASSEMBLY_VERSION = "visual_anchor_content_prompt_assembly.v1"
FUSION_PROMPT_ASSEMBLY_VERSION = "visual_anchor_fusion_prompt_assembly.v1"
RAW_CONTENT_PROMPT_PASSTHROUGH_VERSION = "visual_anchor_content_raw_passthrough.v1"
RAW_FUSION_PROMPT_PASSTHROUGH_VERSION = "visual_anchor_fusion_raw_passthrough.v1"
CONTENT_PROMPT_PASSTHROUGH_VERSION = "visual_anchor_content_prompt_passthrough.v2"
FUSION_PROMPT_PASSTHROUGH_VERSION = "visual_anchor_fusion_prompt_passthrough.v2"
FINALIZATION_PROMPT_PASSTHROUGH_VERSION = (
    "visual_anchor_finalization_prompt_passthrough.v1"
)
_PLANNING_TEXT_MAX_LENGTH = 1200
_PROMPT_TEXT_MAX_LENGTH = 12000
HistoricalContentStagePromptVersion = Literal[
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
]
ContentStagePromptVersion = HistoricalContentStagePromptVersion | Literal[
    "visual_anchor_content_stage.v15",
    "visual_anchor_content_stage.v16",
    "visual_anchor_content_stage.v19",
    "visual_anchor_content_stage.v20",
    CONTENT_STAGE_PROMPT_VERSION
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
    "visual_anchor_fusion_stage.v13",
    "visual_anchor_fusion_stage.v14",
    "visual_anchor_fusion_stage.v17",
    "visual_anchor_fusion_stage.v18",
    "visual_anchor_fusion_stage.v19",
    "visual_anchor_fusion_stage.v20",
    "visual_anchor_fusion_stage.v21",
    "visual_anchor_fusion_stage.v22",
    "visual_anchor_fusion_stage.v23",
    "visual_anchor_fusion_stage.v24",
    "visual_anchor_fusion_stage.v25",
    "visual_anchor_fusion_stage.v26",
    "visual_anchor_fusion_stage.v27",
    "visual_anchor_fusion_stage.v28",
    FUSION_STAGE_PROMPT_VERSION,
]
FinalizationStagePromptVersion = Literal[
    "visual_anchor_finalization_stage.v1",
    "visual_anchor_finalization_stage.v2",
    "visual_anchor_finalization_stage.v3",
    "visual_anchor_finalization_stage.v4",
    "visual_anchor_finalization_stage.v5",
    "visual_anchor_finalization_stage.v6",
    "visual_anchor_finalization_stage.v7",
    "visual_anchor_finalization_stage.v8",
    "visual_anchor_finalization_stage.v9",
    FINALIZATION_STAGE_PROMPT_VERSION,
]
GenerationRequestVersion = Literal[
    "visual_anchor_generation_request.v7",
    "visual_anchor_generation_request.v8",
    "visual_anchor_generation_request.v9",
    "visual_anchor_generation_request.v10",
    GENERATION_REQUEST_VERSION,
]

MAX_VISUAL_STYLE_FRAGMENT_COUNT = 32
MAX_VISUAL_STYLE_BOUNDARY_COUNT = 16
MAX_VISUAL_STYLE_FRAGMENT_CHARS = 1000
MAX_VISUAL_STYLE_TOTAL_CHARS = 12000
MAX_VISUAL_STYLE_DESCRIPTION_CHARS = 16000
_STYLE_DATA_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all",
    "system message",
    "system prompt",
    "assistant message",
    "developer message",
    "override instructions",
    "jailbreak",
    "prompt injection",
    "忽略之前",
    "忽略以上",
    "忽略所有",
    "系统消息",
    "系统提示",
    "助手消息",
    "开发者消息",
    "覆盖指令",
    "越狱",
)


def _contract_version_at_least(value: str, minimum: int) -> bool:
    """Keep validation epochs monotonic when a contract version is bumped."""

    try:
        version = int(value.rsplit(".v", 1)[1])
    except (IndexError, ValueError):
        return False
    return version >= minimum

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


def _verbatim_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


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


def _validate_visual_style_data_text(value: str, field_name: str) -> str:
    if len(value) > MAX_VISUAL_STYLE_FRAGMENT_CHARS:
        raise ValueError(
            f"{field_name} values must not exceed "
            f"{MAX_VISUAL_STYLE_FRAGMENT_CHARS} characters"
        )
    normalized = value.casefold()
    if any(marker.casefold() in normalized for marker in _STYLE_DATA_INJECTION_MARKERS):
        raise ValueError(
            f"{field_name} must contain visual data, not prompt-control instructions"
        )
    return value


def _validate_visual_style_data_list(
    value: list[str],
    field_name: str,
    *,
    allow_empty: bool,
) -> list[str]:
    raw_values = list(value)
    result = _text_list(value, field_name)
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    if len(result) != len(raw_values):
        raise ValueError(f"{field_name} must not contain blank values")
    seen: set[str] = set()
    for fragment in result:
        _validate_visual_style_data_text(fragment, field_name)
        normalized = fragment.casefold()
        if normalized in seen:
            raise ValueError(f"{field_name} must not contain duplicates")
        seen.add(normalized)
    return result


class TargetVisualStyle(BaseModel):
    """Scene-only style contract for narrative subjects and the non-IP world."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(max_length=MAX_VISUAL_STYLE_DESCRIPTION_CHARS)
    required_final_prompt_fragments: list[str] = Field(
        default_factory=list,
        max_length=MAX_VISUAL_STYLE_FRAGMENT_COUNT,
    )
    required_negative_prompt_fragments: list[str] = Field(
        default_factory=list,
        max_length=MAX_VISUAL_STYLE_FRAGMENT_COUNT,
    )

    @field_validator("description", mode="before")
    @classmethod
    def _validate_description(cls, value: object) -> str:
        description = _text(value, "description")
        normalized = description.casefold()
        if any(
            marker.casefold() in normalized
            for marker in _STYLE_DATA_INJECTION_MARKERS
        ):
            raise ValueError(
                "description must contain visual data, not prompt-control instructions"
            )
        return description

    @field_validator(
        "required_final_prompt_fragments",
        "required_negative_prompt_fragments",
    )
    @classmethod
    def _validate_fragments(cls, value: list[str], info) -> list[str]:
        return _validate_visual_style_data_list(
            value,
            info.field_name,
            allow_empty=True,
        )

    @model_validator(mode="after")
    def _validate_total_style_size(self) -> "TargetVisualStyle":
        total_chars = len(self.description) + sum(
            len(fragment)
            for fragment in (
                *self.required_final_prompt_fragments,
                *self.required_negative_prompt_fragments,
            )
        )
        if total_chars > MAX_VISUAL_STYLE_DESCRIPTION_CHARS:
            raise ValueError("target visual style exceeds the total character limit")
        return self


class VisualSignatureStyleContract(BaseModel):
    """Independent style contract applied only to the recurring visual signature."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    style_fragments: list[str] = Field(
        min_length=1,
        max_length=MAX_VISUAL_STYLE_FRAGMENT_COUNT,
    )
    negative_fragments: list[str] = Field(
        default_factory=list,
        max_length=MAX_VISUAL_STYLE_FRAGMENT_COUNT,
    )
    rendering_style: Literal[
        "style_inherited",
        "photorealistic_human",
        "stylized_character",
        "flat_illustration",
    ]
    source_style_scope: Literal["ip_character_only", "ip_world", "inherited"]
    boundary_rules: list[str] = Field(
        default_factory=list,
        max_length=MAX_VISUAL_STYLE_BOUNDARY_COUNT,
    )
    application_scope: Literal["visual_signature_only"] = "visual_signature_only"

    @field_validator(
        "profile_id",
        "rendering_style",
        "source_style_scope",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("style_fragments", "negative_fragments", "boundary_rules")
    @classmethod
    def _validate_fragments(cls, value: list[str], info) -> list[str]:
        return _validate_visual_style_data_list(
            value,
            info.field_name,
            allow_empty=info.field_name != "style_fragments",
        )

    @model_validator(mode="after")
    def _validate_total_style_size(self) -> "VisualSignatureStyleContract":
        total_chars = sum(
            len(fragment)
            for fragment in (
                *self.style_fragments,
                *self.negative_fragments,
                *self.boundary_rules,
            )
        )
        if total_chars > MAX_VISUAL_STYLE_TOTAL_CHARS:
            raise ValueError(
                "visual signature style contract exceeds the total character limit"
            )
        return self


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


class LegacyContentCompositionPlan(BaseModel):
    """Exact v14 composition shape without current output limits or optional layers."""

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


class _ContentStageCommonOutput(BaseModel):
    """Shared factual boundary for current and historical content outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    core_claim: str
    primary_subject: ContentStageSubject
    secondary_subjects: list[ContentStageSubject] = Field(default_factory=list)
    scene_facts: list[ContentFact] = Field(
        default_factory=list,
        description=(
            "只保存纯内容画面直接呈现的跨主体或全场景事实对象数组；"
            "抽象事实若已转换成结果、隐喻或氛围且原事实不再直接出现，必须省略；"
            "每项必须是 ContentFact 对象，不能是字符串"
        ),
    )
    adjustable_non_core_content: list[str] = Field(default_factory=list)

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
    composition_plan: LegacyContentCompositionPlan
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

    core_claim: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)
    secondary_subjects: list[ContentStageSubject] = Field(
        default_factory=list,
        max_length=8,
    )
    scene_facts: list[ContentFact] = Field(default_factory=list, max_length=16)
    adjustable_non_core_content: list[str] = Field(
        default_factory=list,
        max_length=12,
    )
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
    """Historical v15 result with a deterministic server-assembled prompt."""

    prompt_assembly_version: Literal[CONTENT_PROMPT_ASSEMBLY_VERSION]
    pure_content_prompt: str = Field(max_length=_PROMPT_TEXT_MAX_LENGTH)

    @field_validator("pure_content_prompt", mode="before")
    @classmethod
    def _validate_prompt(cls, value: object) -> str:
        return _text(value, "pure_content_prompt")


class ContentStagePromptPassthrough(BaseModel):
    """Current content-stage contract: one model response retained verbatim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passthrough_version: Literal[CONTENT_PROMPT_PASSTHROUGH_VERSION]
    raw_prompt: str

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_raw_contract(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        if (
            normalized.get("prompt_assembly_version")
            != RAW_CONTENT_PROMPT_PASSTHROUGH_VERSION
        ):
            return normalized
        normalized["passthrough_version"] = CONTENT_PROMPT_PASSTHROUGH_VERSION
        normalized["raw_prompt"] = normalized.pop("pure_content_prompt", None)
        normalized.pop("prompt_assembly_version", None)
        return normalized

    @field_validator("raw_prompt", mode="before")
    @classmethod
    def _preserve_raw_prompt(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("raw_prompt must be a string")
        return value

    @property
    def pure_content_prompt(self) -> str:
        """Compatibility view for historical in-process callers."""

        return self.raw_prompt


RawContentStageOutput = ContentStagePromptPassthrough


ReadableContentStageOutput = (
    RawContentStageOutput
    | ContentStageOutput
    | LegacyContentStageOutputV14
    | LegacyContentStageOutput
)

class _ContentStageInputCommon(BaseModel):
    """Fields shared by current and historical content-stage inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    original_storyboard_text: str
    article_context: str
    previous_frame_summary: str
    next_frame_summary: str
    target_image_prompt_language: str

    @field_validator("*", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info):
        if info.field_name in {"prompt_version", "target_visual_style"}:
            return value
        if info.field_name in {
            "original_storyboard_text",
            "article_context",
            "previous_frame_summary",
            "next_frame_summary",
        }:
            return _verbatim_text(value, info.field_name)
        return _text(value, info.field_name)


class LegacyContentStageInput(_ContentStageInputCommon):
    """Historical style-aware input retained only for persisted artifacts."""

    target_visual_style: TargetVisualStyle
    prompt_version: HistoricalContentStagePromptVersion


class ContentStageInput(_ContentStageInputCommon):
    """Current style-neutral input boundary for the content-only model call."""

    prompt_version: Literal[CONTENT_STAGE_PROMPT_VERSION] = CONTENT_STAGE_PROMPT_VERSION


class LegacyContentStageInputV15(_ContentStageInputCommon):
    """Historical style-neutral input retained for persisted artifacts."""

    prompt_version: Literal[
        "visual_anchor_content_stage.v15",
        "visual_anchor_content_stage.v16",
        "visual_anchor_content_stage.v19",
    ]


ReadableContentStageInput = (
    ContentStageInput | LegacyContentStageInputV15 | LegacyContentStageInput
)


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
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        if info.field_name in {"previous_frame_summary", "next_frame_summary"}:
            return _verbatim_text(value, info.field_name)
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
    visual_signature_emphasis: VisualSignatureEmphasis = (
        VisualSignatureEmphasis.STANDARD
    )
    continuous_scene_context: ContinuousSceneContext
    series_fusion_history: list[str] = Field(default_factory=list, max_length=3)
    target_visual_style: TargetVisualStyle
    visual_signature_style: VisualSignatureStyleContract | None = None
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
        if info.field_name == "original_storyboard_text":
            return _verbatim_text(value, info.field_name)
        return _text(value, info.field_name)

    @model_validator(mode="after")
    def _validate_identity_conditioning(self) -> "FusionStageInput":
        if (
            _contract_version_at_least(self.prompt_version, 26)
            and "visual_signature_emphasis" not in self.model_fields_set
        ):
            raise ValueError(
                "current fusion input requires an explicit visual signature emphasis"
            )
        if _contract_version_at_least(self.prompt_version, 27):
            if self.visual_signature_style is None:
                raise ValueError(
                    "current fusion input requires an independent visual signature style"
                )
            if self.visual_signature_style.profile_id != self.identity_profile.profile_id:
                raise ValueError(
                    "visual signature style must match the identity profile"
                )
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
    """Historical v13 structured model response."""

    selected_fusion_method: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)
    final_manifestation: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)
    spatial_contact_and_lighting_relation: str = Field(
        max_length=_PLANNING_TEXT_MAX_LENGTH
    )
    continuity_change_reason: str = Field(max_length=_PLANNING_TEXT_MAX_LENGTH)
    relative_scale_and_visual_weight: str = Field(
        max_length=_PLANNING_TEXT_MAX_LENGTH
    )
    support_carrier_and_material_relation: str = Field(
        max_length=_PLANNING_TEXT_MAX_LENGTH
    )
    visual_identity_scene_interaction: str = Field(
        max_length=_PLANNING_TEXT_MAX_LENGTH
    )
    scene_negative_prompt: str = Field(default="", max_length=_PROMPT_TEXT_MAX_LENGTH)

    @field_validator(
        "relative_scale_and_visual_weight",
        "support_carrier_and_material_relation",
        "visual_identity_scene_interaction",
        mode="before",
    )
    @classmethod
    def _validate_current_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("scene_negative_prompt", mode="before")
    @classmethod
    def _validate_scene_negative_prompt(cls, value: object) -> str:
        return _optional_text(value, "scene_negative_prompt")


class FusionStageOutput(FusionStageModelOutput):
    """Historical v13 result with deterministic server prompt assembly."""

    prompt_assembly_version: Literal[FUSION_PROMPT_ASSEMBLY_VERSION]
    base_content_prompt: str = Field(max_length=_PROMPT_TEXT_MAX_LENGTH)
    identity_prompt_clause: str = Field(max_length=_PROMPT_TEXT_MAX_LENGTH)
    final_positive_prompt: str = Field(max_length=_PROMPT_TEXT_MAX_LENGTH)
    final_negative_prompt: str = Field(default="", max_length=_PROMPT_TEXT_MAX_LENGTH)

    @field_validator(
        "base_content_prompt",
        "identity_prompt_clause",
        "final_positive_prompt",
        mode="before",
    )
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


class FusionStagePromptPassthrough(BaseModel):
    """Current fusion-stage contract: one model response is the image prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passthrough_version: Literal[FUSION_PROMPT_PASSTHROUGH_VERSION]
    raw_prompt: str

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_raw_contract(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        if (
            normalized.get("prompt_assembly_version")
            != RAW_FUSION_PROMPT_PASSTHROUGH_VERSION
        ):
            return normalized
        normalized["passthrough_version"] = FUSION_PROMPT_PASSTHROUGH_VERSION
        normalized["raw_prompt"] = normalized.pop("final_positive_prompt", None)
        normalized.pop("prompt_assembly_version", None)
        normalized.pop("base_content_prompt", None)
        normalized.pop("final_negative_prompt", None)
        return normalized

    @field_validator("raw_prompt", mode="before")
    @classmethod
    def _preserve_raw_prompt(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("raw_prompt must be a string")
        return value

    @property
    def final_positive_prompt(self) -> str:
        """Compatibility view for historical in-process callers."""

        return self.raw_prompt

    @property
    def final_negative_prompt(self) -> str:
        """Compatibility view; the passthrough stage has no negative channel."""

        return ""


RawFusionStageOutput = FusionStagePromptPassthrough


ReadableFusionStageOutput = (
    RawFusionStageOutput
    | FusionStageOutput
    | LegacyFusionStageOutputV12
    | LegacyFusionStageOutput
)


class FinalizationStageInput(BaseModel):
    """Fixed third-stage input for unconstrained final scene recomposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    original_storyboard_text: str
    content_stage_input: ReadableContentStageInput | None = None
    fusion_stage_input: FusionStageInput
    fusion_stage_output: ReadableFusionStageOutput
    series_final_prompt_history: list[str] = Field(default_factory=list, max_length=3)
    prompt_version: FinalizationStagePromptVersion = FINALIZATION_STAGE_PROMPT_VERSION

    @field_validator("frame_id", "original_storyboard_text", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        if info.field_name == "original_storyboard_text":
            return _verbatim_text(value, info.field_name)
        return _text(value, info.field_name)

    @model_validator(mode="after")
    def _validate_exact_draft_chain(self) -> "FinalizationStageInput":
        if (
            _contract_version_at_least(self.prompt_version, 7)
            and self.content_stage_input is None
        ):
            raise ValueError(
                "current finalization input requires the exact content-stage input"
            )
        if self.frame_id != self.fusion_stage_input.frame_id:
            raise ValueError("finalization frame id must match the fusion input")
        if (
            self.original_storyboard_text
            != self.fusion_stage_input.original_storyboard_text
        ):
            raise ValueError(
                "finalization storyboard text must match the fusion input"
            )
        if self.content_stage_input is not None:
            if self.frame_id != self.content_stage_input.frame_id:
                raise ValueError(
                    "finalization frame id must match the content-stage input"
                )
            if (
                self.original_storyboard_text
                != self.content_stage_input.original_storyboard_text
            ):
                raise ValueError(
                    "finalization storyboard text must match the content-stage input"
                )
        if (
            self.prompt_version == FINALIZATION_STAGE_PROMPT_VERSION
            and self.fusion_stage_input.prompt_version != FUSION_STAGE_PROMPT_VERSION
        ):
            raise ValueError(
                "current finalization input requires the current fusion-stage version"
            )
        return self


class FinalizationStagePromptPassthrough(BaseModel):
    """One finalizer response retained verbatim as the image prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passthrough_version: Literal[FINALIZATION_PROMPT_PASSTHROUGH_VERSION]
    raw_prompt: str

    @field_validator("raw_prompt", mode="before")
    @classmethod
    def _preserve_raw_prompt(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("raw_prompt must be a string")
        return value

    @property
    def final_positive_prompt(self) -> str:
        return self.raw_prompt

    @property
    def final_negative_prompt(self) -> str:
        return ""


RawFinalizationStageOutput = FinalizationStagePromptPassthrough

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
    base_content_prompt: str
    identity_prompt_clause: str
    relative_scale_and_visual_weight: str
    support_carrier_and_material_relation: str
    visual_identity_scene_interaction: str
    spatial_contact_and_lighting_relation: str
    scene_negative_prompt: str = ""

    @field_validator(
        "base_content_prompt",
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

    @field_validator("scene_negative_prompt", mode="before")
    @classmethod
    def _validate_scene_negative_prompt(cls, value: object) -> str:
        return _optional_text(value, "scene_negative_prompt")


class VisualAnchorImageGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_version: GenerationRequestVersion = GENERATION_REQUEST_VERSION
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
    identity_forbidden_traits: list[str] = Field(default_factory=list)
    identity_resource_version: str
    identity_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_conditioning_mode: Literal["text_profile", "reference_image"]
    identity_reference_condition: IdentityReferenceCondition | None = None
    target_visual_style: TargetVisualStyle
    visual_signature_style: VisualSignatureStyleContract | None = None
    visible_text_policy: VisibleTextPolicy = Field(default_factory=VisibleTextPolicy)
    content_stage_prompt_version: ContentStagePromptVersion
    fusion_stage_prompt_version: FusionStagePromptVersion
    finalization_stage_prompt_version: FinalizationStagePromptVersion | None = None
    negative_prompt_supported: bool
    target_image_prompt_language: str | None = None
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
            "visual_anchor_generation_request.v6",
        }:
            normalized["request_version"] = "visual_anchor_generation_request.v7"
        return normalized

    @field_validator(
        "task_id",
        "frame_id",
        "identity_profile_id",
        "identity_display_name",
        "identity_resource_version",
        "workflow_key",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("selected_fusion_method", "final_manifestation", mode="before")
    @classmethod
    def _preserve_optional_model_metadata(cls, value: object, info) -> str:
        return _optional_text(value, info.field_name)

    @field_validator("final_positive_prompt", "final_negative_prompt", mode="before")
    @classmethod
    def _preserve_model_prompt_verbatim(cls, value: object, info) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{info.field_name} must be a string")
        return value

    @field_validator("identity_core_traits")
    @classmethod
    def _validate_identity_core_traits(cls, value: list[str]) -> list[str]:
        result = _text_list(value, "identity_core_traits")
        if not result:
            raise ValueError("identity_core_traits must not be empty")
        return result

    @field_validator("identity_forbidden_traits")
    @classmethod
    def _validate_identity_forbidden_traits(cls, value: list[str]) -> list[str]:
        return _text_list(value, "identity_forbidden_traits")

    @field_validator("target_image_prompt_language", mode="before")
    @classmethod
    def _validate_target_image_prompt_language(cls, value: object) -> str | None:
        if value is None:
            return None
        return _text(value, "target_image_prompt_language")

    @model_validator(mode="after")
    def _validate_non_content_resource_wiring(
        self,
    ) -> "VisualAnchorImageGenerationRequest":
        expected_identity_version = (
            f"identity:{self.identity_profile_id}:{self.identity_content_sha256}"
        )
        if self.identity_resource_version != expected_identity_version:
            raise ValueError(
                "identity resource version must match the identity id and digest"
            )
        if self.identity_conditioning_mode == "reference_image":
            if self.identity_reference_condition is None:
                raise ValueError(
                    "reference-image generation requires a reference condition"
                )
        elif self.identity_reference_condition is not None:
            raise ValueError(
                "text-profile generation cannot include a reference condition"
            )
        if (
            _contract_version_at_least(self.request_version, 8)
            and self.finalization_stage_prompt_version is None
        ):
            raise ValueError(
                "current generation requests require the finalization stage version"
            )
        if _contract_version_at_least(self.request_version, 9):
            if self.visual_signature_style is None:
                raise ValueError(
                    "current generation requests require an independent visual signature style"
                )
            if self.visual_signature_style.profile_id != self.identity_profile_id:
                raise ValueError(
                    "generation visual signature style must match the identity profile"
                )
        if self.request_version == GENERATION_REQUEST_VERSION and (
            self.content_stage_prompt_version != CONTENT_STAGE_PROMPT_VERSION
            or self.fusion_stage_prompt_version != FUSION_STAGE_PROMPT_VERSION
            or self.finalization_stage_prompt_version
            != FINALIZATION_STAGE_PROMPT_VERSION
        ):
            raise ValueError(
                "current generation requests require the current three-stage prompt chain"
            )
        if self.request_version == GENERATION_REQUEST_VERSION:
            expected_global_negative = (
                self.visible_text_policy.required_negative_prompt_fragment
                if self.negative_prompt_supported
                else ""
            )
            if self.final_negative_prompt != expected_global_negative:
                raise ValueError(
                    "current generation requests may place only image-wide visible-text "
                    "exclusions in the global negative prompt"
                )
        if (
            self.request_version == "visual_anchor_generation_request.v7"
            and self.finalization_stage_prompt_version is not None
        ):
            raise ValueError(
                "historical two-stage requests cannot declare a finalization stage"
            )
        return self


def visual_signature_style_binding_payload(
    request: VisualAnchorImageGenerationRequest,
) -> dict[str, object] | None:
    """Return the canonical audit payload for the request's own schema epoch."""

    style = request.visual_signature_style
    if style is None:
        return None
    payload = style.model_dump(mode="json")
    if not _contract_version_at_least(request.request_version, 10):
        payload.pop("negative_fragments", None)
    return payload


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
    return ", ".join(fragments)


def assemble_content_stage_prompt(
    output: ContentStageModelOutput,
) -> str:
    """Build the content prompt exclusively from validated visual decisions."""

    composition = output.composition_plan
    subject_fragments: list[str] = []
    for subject in (output.primary_subject, *output.secondary_subjects):
        subject_name = (
            subject.name
            if subject.quantity == 1
            else f"{subject.quantity}× {subject.name}"
        )
        subject_fragments.extend((subject_name, subject.identity, subject.action))
    return _join_prompt_fragments(
        [
            composition.shot_scale_and_camera,
            *subject_fragments,
            output.decisive_moment,
            output.content_subject_interaction,
            *output.renderable_story_beats,
            *(fact.statement for fact in output.scene_facts),
            composition.foreground,
            composition.midground,
            composition.background,
            composition.visual_focus,
        ]
    )


def assemble_identity_prompt_clause(
    output: FusionStageModelOutput,
    *,
    identity_profile: VisualAnchorIdentityProfile,
    target_image_prompt_language: str,
) -> str:
    """Build one prompt-ready manifestation clause from the chosen relationships."""

    return assemble_identity_prompt_clause_from_fields(
        final_manifestation=output.final_manifestation,
        identity_display_name=identity_profile.display_name,
        identity_core_traits=identity_profile.core_identity_traits,
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
        target_image_prompt_language=target_image_prompt_language,
    )


def assemble_identity_prompt_clause_from_fields(
    *,
    final_manifestation: str,
    identity_display_name: str,
    identity_core_traits: list[str],
    relative_scale_and_visual_weight: str,
    support_carrier_and_material_relation: str,
    visual_identity_scene_interaction: str,
    spatial_contact_and_lighting_relation: str,
    target_image_prompt_language: str,
) -> str:
    normalized_language = target_image_prompt_language.casefold()
    single_instance = (
        f"整幅画只出现一个可识别的{identity_display_name}视觉身份实例"
        if "中文" in normalized_language or "chinese" in normalized_language
        else (
            "exactly one recognizable visual identity instance of "
            f"{identity_display_name} in the entire image"
        )
    )
    return _join_prompt_fragments(
        [
            final_manifestation,
            *identity_core_traits,
            relative_scale_and_visual_weight,
            support_carrier_and_material_relation,
            visual_identity_scene_interaction,
            spatial_contact_and_lighting_relation,
            single_instance,
        ]
    )


def assemble_fusion_positive_prompt(
    output: FusionStageModelOutput,
    *,
    content_stage_output: ContentStageOutput,
    identity_prompt_clause: str,
    identity_profile: VisualAnchorIdentityProfile,
    target_visual_style: TargetVisualStyle,
    visible_text_policy: VisibleTextPolicy,
    negative_prompt_supported: bool,
    target_image_prompt_language: str,
) -> str:
    """Insert the identity decision inside the scene and append deterministic policies."""

    trace = VisualAnchorPromptAssemblyTrace(
        assembly_version=FUSION_PROMPT_ASSEMBLY_VERSION,
        base_content_prompt=content_stage_output.pure_content_prompt,
        identity_prompt_clause=identity_prompt_clause,
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
    return assemble_positive_prompt_from_trace(
        trace,
        identity_forbidden_traits=identity_profile.forbidden_traits,
        target_visual_style=target_visual_style,
        visible_text_policy=visible_text_policy,
        negative_prompt_supported=negative_prompt_supported,
        target_image_prompt_language=target_image_prompt_language,
    )


def assemble_positive_prompt_from_trace(
    trace: VisualAnchorPromptAssemblyTrace,
    *,
    identity_forbidden_traits: list[str],
    target_visual_style: TargetVisualStyle,
    visible_text_policy: VisibleTextPolicy,
    negative_prompt_supported: bool,
    target_image_prompt_language: str,
) -> str:
    return _join_prompt_fragments(
        [
            trace.base_content_prompt,
            trace.identity_prompt_clause,
            target_visual_style.description,
            *target_visual_style.required_final_prompt_fragments,
            visible_text_policy.required_positive_prompt_fragment,
            *(
                []
                if negative_prompt_supported
                else _positive_identity_avoidance_fragments(
                    identity_forbidden_traits,
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
    return assemble_negative_prompt_from_fields(
        scene_negative_prompt=output.scene_negative_prompt,
        identity_forbidden_traits=identity_profile.forbidden_traits,
        target_visual_style=target_visual_style,
        visible_text_policy=visible_text_policy,
        negative_prompt_supported=negative_prompt_supported,
    )


def assemble_negative_prompt_from_fields(
    *,
    scene_negative_prompt: str,
    identity_forbidden_traits: list[str],
    target_visual_style: TargetVisualStyle,
    visible_text_policy: VisibleTextPolicy,
    negative_prompt_supported: bool,
) -> str:
    if not negative_prompt_supported:
        return ""
    return _join_prompt_fragments(
        [
            scene_negative_prompt,
            *identity_forbidden_traits,
            *target_visual_style.required_negative_prompt_fragments,
            visible_text_policy.required_negative_prompt_fragment,
        ]
    )


def assemble_negative_prompt_from_trace(
    trace: VisualAnchorPromptAssemblyTrace,
    *,
    identity_forbidden_traits: list[str],
    target_visual_style: TargetVisualStyle,
    visible_text_policy: VisibleTextPolicy,
    negative_prompt_supported: bool,
) -> str:
    return assemble_negative_prompt_from_fields(
        scene_negative_prompt=trace.scene_negative_prompt,
        identity_forbidden_traits=identity_forbidden_traits,
        target_visual_style=target_visual_style,
        visible_text_policy=visible_text_policy,
        negative_prompt_supported=negative_prompt_supported,
    )


def _positive_identity_avoidance_fragments(
    identity_forbidden_traits: list[str],
    *,
    target_image_prompt_language: str,
) -> list[str]:
    normalized_language = target_image_prompt_language.casefold()
    use_chinese = "中文" in normalized_language or "chinese" in normalized_language
    result: list[str] = []
    for trait in identity_forbidden_traits:
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
        base_content_prompt=output.base_content_prompt,
        identity_prompt_clause=output.identity_prompt_clause,
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
    content_stage_input: ReadableContentStageInput
    content_stage_output: ReadableContentStageOutput
    fusion_stage_input: FusionStageInput
    fusion_stage_output: ReadableFusionStageOutput
    finalization_stage_input: FinalizationStageInput | None = None
    finalization_stage_output: FinalizationStagePromptPassthrough | None = None
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
    def _validate_current_three_stage_chain(self) -> "VisualAnchorTwoStageFrameResult":
        if self.generation_request.request_version != GENERATION_REQUEST_VERSION:
            return self
        if not (
            self.frame_id
            == self.content_stage_input.frame_id
            == self.fusion_stage_input.frame_id
            == self.generation_request.frame_id
        ):
            raise ValueError("current visual-anchor frame ids must match")
        if self.fusion_stage_input.content_stage_output != self.content_stage_output:
            raise ValueError("fusion input must contain the exact content output")
        if (
            self.generation_request.content_stage_prompt_version
            != self.content_stage_input.prompt_version
        ):
            raise ValueError(
                "generation request content version must match its stage input"
            )
        if (
            self.generation_request.fusion_stage_prompt_version
            != self.fusion_stage_input.prompt_version
        ):
            raise ValueError(
                "generation request fusion version must match its stage input"
            )
        if self.finalization_stage_input is None or self.finalization_stage_output is None:
            raise ValueError(
                "current visual-anchor results require one finalization input and output"
            )
        if self.finalization_stage_input.fusion_stage_input != self.fusion_stage_input:
            raise ValueError("finalization input must contain the exact fusion input")
        if self.finalization_stage_input.fusion_stage_output != self.fusion_stage_output:
            raise ValueError("finalization input must contain the exact fusion output")
        if (
            self.finalization_stage_input.content_stage_input is not None
            and self.finalization_stage_input.content_stage_input
            != self.content_stage_input
        ):
            raise ValueError(
                "finalization input must contain the exact content-stage input"
            )
        if (
            self.generation_request.finalization_stage_prompt_version
            != self.finalization_stage_input.prompt_version
        ):
            raise ValueError(
                "generation request finalization version must match its stage input"
            )
        if (
            self.generation_request.final_positive_prompt
            != self.finalization_stage_output.raw_prompt
        ):
            raise ValueError(
                "generation prompt must exactly match the finalization response"
            )
        return self
