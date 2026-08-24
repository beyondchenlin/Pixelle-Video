from __future__ import annotations

import re
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

CONTENT_STAGE_PROMPT_VERSION = "visual_anchor_content_stage.v12"
FUSION_STAGE_PROMPT_VERSION = "visual_anchor_fusion_stage.v8"
GENERATION_REQUEST_VERSION = "visual_anchor_generation_request.v4"
ContentStagePromptVersion = Literal[
    "visual_anchor_content_stage.v5",
    "visual_anchor_content_stage.v6",
    "visual_anchor_content_stage.v7",
    "visual_anchor_content_stage.v8",
    "visual_anchor_content_stage.v9",
    "visual_anchor_content_stage.v10",
    "visual_anchor_content_stage.v11",
    CONTENT_STAGE_PROMPT_VERSION,
]
FusionStagePromptVersion = Literal[
    "visual_anchor_fusion_stage.v4",
    "visual_anchor_fusion_stage.v5",
    "visual_anchor_fusion_stage.v6",
    "visual_anchor_fusion_stage.v7",
    FUSION_STAGE_PROMPT_VERSION,
]

GenerationRequestVersion = Literal[
    "visual_anchor_generation_request.v3",
    GENERATION_REQUEST_VERSION,
]
StageSelfCheckDecision = Literal["pass", "fail"]
ContentSubjectCategory = Literal[
    "person",
    "animal",
    "object",
    "product",
    "place",
    "event",
]
ProtectedFactCategory = Literal[
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
ContentStageValidationCode = Literal[
    "schema_contract_invalid",
    "self_check_failed",
    "subject_source_evidence_invalid",
    "subject_prompt_evidence_invalid",
    "concrete_fact_missing",
    "fact_subject_reference_invalid",
    "fact_subject_evidence_mismatch",
    "subject_fact_missing",
    "fact_source_evidence_invalid",
    "fact_prompt_evidence_invalid",
    "identity_isolation_failed",
    "server_control_leaked",
]
_CONTENT_STAGE_VALIDATION_CODES = get_args(ContentStageValidationCode)

_FORBIDDEN_IMAGE_PROMPT_TERMS = (
    "视觉锚点",
    "知识产权角色",
    "受保护事实",
    "融合方案",
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
    "server_validation",
    "validation_codes",
    *_CONTENT_STAGE_VALIDATION_CODES,
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
_CONTENT_SUBJECT_PRONOUN_NAMES = frozenset(
    {"他", "她", "它", "他们", "她们", "它们", "此人", "该人物", "该角色"}
)
_PLACEHOLDER_SUBJECT_PATTERNS = (
    re.compile(r"表达.*第?[一二三四五六七八九十0-9]+个?分镜", re.IGNORECASE),
    re.compile(r"第?[一二三四五六七八九十0-9]+个?分镜段落", re.IGNORECASE),
    re.compile(r"visuali[sz]e\s+(?:the\s+)?(?:frame|segment)", re.IGNORECASE),
    re.compile(r"show\s+(?:the\s+)?(?:frame|segment)", re.IGNORECASE),
)


def _contains_required_prompt_fragment_contract(prompt: str, required: str) -> bool:
    normalized_prompt = " ".join(str(prompt or "").split()).casefold()
    fragments = [
        " ".join(fragment.split()).casefold()
        for fragment in re.split(r"[,，;；]+", str(required or ""))
        if " ".join(fragment.split())
    ]
    return bool(fragments) and all(fragment in normalized_prompt for fragment in fragments)


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


def _concrete_subject_text(value: object, field_name: str) -> str:
    text = _text(value, field_name)
    if any(pattern.search(text) for pattern in _PLACEHOLDER_SUBJECT_PATTERNS):
        raise ValueError(f"{field_name} cannot use a storyboard placeholder")
    return text


def _optional_concrete_subject_text(value: object, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = " ".join(value.split())
    if text and any(pattern.search(text) for pattern in _PLACEHOLDER_SUBJECT_PATTERNS):
        raise ValueError(f"{field_name} cannot use a storyboard placeholder")
    return text


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

    category: ProtectedFactCategory
    statement: str
    source_evidence: str = Field(
        description="从原始分镜文案或文章背景中逐字复制的最短连续片段"
    )
    pure_content_prompt_evidence: str = Field(
        description=(
            "从 pure_content_prompt 中逐字复制、足以证明事实存在的最短连续片段；"
            "不得改写或跨过其他词语拼接"
        )
    )

    @field_validator(
        "statement",
        "source_evidence",
        "pure_content_prompt_evidence",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _concrete_subject_text(value, info.field_name)


_FLATTENED_CONTENT_FACT_FIELDS = (
    "category",
    "statement",
    "source_evidence",
    "pure_content_prompt_evidence",
)
_CATEGORYLESS_SUBJECT_FACT_FIELDS = (
    "statement",
    "source_evidence",
    "pure_content_prompt_evidence",
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


def _decode_categoryless_subject_facts(
    value: object,
    *,
    subject_category: object,
) -> object:
    """Decode complete subject-local fact groups whose category is inherited."""

    if subject_category not in get_args(ContentSubjectCategory):
        return value
    if not isinstance(value, list) or not value:
        return value
    if not all(isinstance(item, str) for item in value):
        return value
    if len(value) % len(_CATEGORYLESS_SUBJECT_FACT_FIELDS) != 0:
        return value

    decoded: list[dict[str, str]] = []
    group_size = len(_CATEGORYLESS_SUBJECT_FACT_FIELDS)
    for offset in range(0, len(value), group_size):
        group = value[offset : offset + group_size]
        fact: dict[str, str] = {}
        for item in group:
            field_name, separator, field_value = item.partition(":")
            normalized_field_name = field_name.strip()
            if (
                not separator
                or normalized_field_name not in _CATEGORYLESS_SUBJECT_FACT_FIELDS
                or normalized_field_name in fact
                or not field_value.strip()
            ):
                return value
            fact[normalized_field_name] = field_value.strip()
        if set(fact) != set(_CATEGORYLESS_SUBJECT_FACT_FIELDS):
            return value
        decoded.append({"category": subject_category, **fact})
    return decoded


def _decode_subject_fact_statements(
    subject: object,
    *,
    pure_content_prompt: object,
) -> object:
    """Materialize fact objects from bare statements using subject-local evidence."""

    if not isinstance(subject, dict):
        return subject
    facts = subject.get("protected_facts")
    if not isinstance(facts, list) or not facts or not all(
        isinstance(item, str) for item in facts
    ):
        return subject

    keyed_facts = _decode_flattened_content_facts(facts)
    if keyed_facts is not facts:
        return {**subject, "protected_facts": keyed_facts}

    categoryless_facts = _decode_categoryless_subject_facts(
        facts,
        subject_category=subject.get("category"),
    )
    if categoryless_facts is not facts:
        return {**subject, "protected_facts": categoryless_facts}

    for item in facts:
        field_name, separator, _ = item.partition(":")
        if separator and field_name.strip() in _FLATTENED_CONTENT_FACT_FIELDS:
            return subject

    category = subject.get("category")
    source_fallback = subject.get("source_evidence")
    prompt_fallback = subject.get("pure_content_prompt_evidence")
    if (
        category not in get_args(ContentSubjectCategory)
        or not isinstance(source_fallback, str)
        or not source_fallback.strip()
        or not isinstance(prompt_fallback, str)
        or not prompt_fallback.strip()
    ):
        return subject

    normalized_prompt = (
        " ".join(pure_content_prompt.split())
        if isinstance(pure_content_prompt, str)
        else ""
    )
    decoded: list[dict[str, str]] = []
    for item in facts:
        statement = " ".join(item.split())
        if not statement:
            return subject
        decoded.append(
            {
                "category": category,
                "statement": statement,
                "source_evidence": source_fallback,
                "pure_content_prompt_evidence": (
                    statement if statement in normalized_prompt else prompt_fallback
                ),
            }
        )
    return {**subject, "protected_facts": decoded}


def _unique_longest_exact_prompt_fragment(
    evidence: object,
    normalized_prompt: str,
) -> str | None:
    """Resolve an unambiguous exact excerpt from delimiter-joined evidence."""

    if not isinstance(evidence, str):
        return None
    fragments = [
        " ".join(fragment.split())
        for fragment in re.split(r"[，,;；、]+", evidence)
        if fragment.strip()
    ]
    if len(fragments) < 2:
        return None

    normalized_prompt_folded = normalized_prompt.casefold()
    exact_fragments: dict[str, str] = {}
    for fragment in fragments:
        folded_fragment = fragment.casefold()
        if folded_fragment in normalized_prompt_folded:
            exact_fragments.setdefault(folded_fragment, fragment)
    if not exact_fragments:
        return None

    longest_length = max(len(fragment) for fragment in exact_fragments)
    longest_fragments = [
        fragment
        for fragment in exact_fragments.values()
        if len(fragment.casefold()) == longest_length
    ]
    if len(longest_fragments) != 1:
        return None
    return longest_fragments[0]


def _use_exact_prompt_evidence(value: object, pure_content_prompt: object) -> object:
    """Prefer an existing exact prompt excerpt when the claimed excerpt is inexact."""

    if not isinstance(value, dict) or not isinstance(pure_content_prompt, str):
        return value
    normalized_prompt = " ".join(pure_content_prompt.split())
    current_evidence = value.get("pure_content_prompt_evidence")
    if (
        isinstance(current_evidence, str)
        and current_evidence.strip()
        and " ".join(current_evidence.split()) in normalized_prompt
    ):
        return value
    exact_fragment = _unique_longest_exact_prompt_fragment(
        current_evidence,
        normalized_prompt,
    )
    if exact_fragment is not None:
        return {**value, "pure_content_prompt_evidence": exact_fragment}
    for field_name in ("statement", "source_evidence"):
        candidate = value.get(field_name)
        if (
            isinstance(candidate, str)
            and candidate.strip()
            and " ".join(candidate.split()) in normalized_prompt
        ):
            return {**value, "pure_content_prompt_evidence": candidate}
    return value


def _normalize_subject_prompt_evidence(
    subject: object,
    pure_content_prompt: object,
) -> object:
    if not isinstance(subject, dict):
        return subject
    normalized_subject = _use_exact_prompt_evidence(subject, pure_content_prompt)
    if isinstance(pure_content_prompt, str):
        normalized_name = " ".join(str(normalized_subject.get("name", "")).split())
        normalized_identity = " ".join(
            str(normalized_subject.get("identity", "")).split()
        )
        normalized_evidence = " ".join(
            str(
                normalized_subject.get("pure_content_prompt_evidence", "")
            ).split()
        )
        normalized_prompt = " ".join(pure_content_prompt.split())
        if (
            normalized_name in _CONTENT_SUBJECT_PRONOUN_NAMES
            and normalized_identity.casefold() == normalized_evidence.casefold()
            and normalized_evidence
            and normalized_evidence.casefold() in normalized_prompt.casefold()
        ):
            normalized_subject = {**normalized_subject, "name": normalized_evidence}
    facts = normalized_subject.get("protected_facts")
    if not isinstance(facts, list):
        return normalized_subject
    return {
        **normalized_subject,
        "protected_facts": [
            _use_exact_prompt_evidence(fact, pure_content_prompt) for fact in facts
        ],
    }


def _retain_rendered_scene_facts(
    scene_facts: list[object],
    pure_content_prompt: object,
) -> list[object]:
    """Keep only scene facts with exact evidence in the rendered content prompt."""

    if not isinstance(pure_content_prompt, str):
        return scene_facts
    normalized_prompt = " ".join(pure_content_prompt.split()).casefold()
    retained: list[object] = []
    for fact in scene_facts:
        normalized_fact = _use_exact_prompt_evidence(fact, pure_content_prompt)
        if not isinstance(normalized_fact, dict):
            retained.append(normalized_fact)
            continue
        evidence = normalized_fact.get("pure_content_prompt_evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            retained.append(normalized_fact)
            continue
        if " ".join(evidence.split()).casefold() in normalized_prompt:
            retained.append(normalized_fact)
    return retained


class ContentStageSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ContentSubjectCategory
    name: str
    identity: str
    quantity: int = Field(gt=0)
    action: str
    source_evidence: str = Field(
        description="从原始分镜文案或文章背景中逐字复制的最短连续片段"
    )
    pure_content_prompt_evidence: str = Field(
        description=(
            "从 pure_content_prompt 中逐字复制的最短连续片段；优先只复制主体名称，"
            "不得跨过其他词语拼接名称、身份和动作"
        )
    )
    protected_facts: SkipJsonSchema[list[ContentFact]] = Field(
        default_factory=list,
        description=(
            "直接描述该主体且必须由后续阶段保留的事实对象数组；"
            "每项必须是 ContentFact 对象，不能是字符串"
        ),
    )

    @field_validator("protected_facts", mode="before")
    @classmethod
    def _decode_protected_facts(cls, value: object) -> object:
        if isinstance(value, list) and value and all(item is None for item in value):
            return []
        return _decode_flattened_content_facts(value)

    @field_validator(
        "name",
        "identity",
        "source_evidence",
        "pure_content_prompt_evidence",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _concrete_subject_text(value, info.field_name)

    @field_validator("action", mode="before")
    @classmethod
    def _validate_action(cls, value: object) -> str:
        return _optional_concrete_subject_text(value, "action")


class ContentStageModelOutput(BaseModel):
    """Identifier-free response contract for the content-stage model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    core_claim: str
    primary_subject: ContentStageSubject
    secondary_subjects: list[ContentStageSubject] = Field(default_factory=list)
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
    self_check: SkipJsonSchema[StageSelfCheckDecision] = "pass"
    self_check_failures: SkipJsonSchema[list[str]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _decode_subject_facts(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        pure_content_prompt = value.get("pure_content_prompt")
        primary_subject = _decode_subject_fact_statements(
            value.get("primary_subject"),
            pure_content_prompt=pure_content_prompt,
        )
        primary_subject = _normalize_subject_prompt_evidence(
            primary_subject,
            pure_content_prompt,
        )
        secondary_subjects = value.get("secondary_subjects")
        if isinstance(secondary_subjects, list):
            secondary_subjects = [
                _normalize_subject_prompt_evidence(
                    _decode_subject_fact_statements(
                        subject,
                        pure_content_prompt=pure_content_prompt,
                    ),
                    pure_content_prompt,
                )
                for subject in secondary_subjects
            ]
        decoded_value = {**value, "primary_subject": primary_subject}
        if "secondary_subjects" in value:
            decoded_value["secondary_subjects"] = secondary_subjects
        scene_facts = value.get("scene_facts")
        if isinstance(scene_facts, list):
            scene_facts = _decode_flattened_content_facts(scene_facts)
            decoded_value["scene_facts"] = _retain_rendered_scene_facts(
                scene_facts,
                pure_content_prompt,
            )
        return decoded_value

    @field_validator("core_claim", "pure_content_prompt", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)

    @field_validator("scene_facts", mode="before")
    @classmethod
    def _decode_scene_facts(cls, value: object) -> object:
        return _decode_flattened_content_facts(value)

    @field_validator("adjustable_non_core_content", "self_check_failures")
    @classmethod
    def _validate_list(cls, value: list[str], info) -> list[str]:
        return _text_list(value, info.field_name)

    @model_validator(mode="after")
    def _validate_result(self) -> "ContentStageModelOutput":
        if self.self_check == "pass" and self.self_check_failures:
            raise ValueError("a passed content-stage result cannot contain failures")
        if self.self_check == "fail" and not self.self_check_failures:
            raise ValueError("a failed content-stage result must contain failures")
        return self


class ContentSubject(BaseModel):
    """Server-owned subject contract used after deterministic materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_id: str
    role: Literal["primary", "secondary"]
    category: ContentSubjectCategory
    name: str
    identity: str
    quantity: int = Field(gt=0)
    action: str
    source_evidence: str = Field(
        description="从原始分镜文案或文章背景中逐字复制的最短连续片段"
    )
    pure_content_prompt_evidence: str = Field(
        description=(
            "从 pure_content_prompt 中逐字复制的最短连续片段；优先只复制主体名称，"
            "不得跨过其他词语拼接名称、身份和动作"
        )
    )

    @field_validator(
        "subject_id",
        "name",
        "identity",
        "source_evidence",
        "pure_content_prompt_evidence",
        mode="before",
    )
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _concrete_subject_text(value, info.field_name)

    @field_validator("action", mode="before")
    @classmethod
    def _validate_action(cls, value: object) -> str:
        return _optional_concrete_subject_text(value, "action")


class ProtectedFact(ContentFact):
    """Server-owned fact contract with deterministic internal identifiers."""

    fact_id: str
    subject_ids: list[str]

    @field_validator("fact_id", mode="before")
    @classmethod
    def _validate_fact_id(cls, value: object) -> str:
        return _concrete_subject_text(value, "fact_id")

    @field_validator("subject_ids")
    @classmethod
    def _validate_subject_ids(cls, value: list[str]) -> list[str]:
        return _text_list(value, "subject_ids")


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


class ContentStageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    core_claim: str
    protected_facts: list[ProtectedFact] = Field(min_length=1)
    primary_subject: ContentSubject
    secondary_subjects: list[ContentSubject] = Field(default_factory=list)
    adjustable_non_core_content: list[str] = Field(default_factory=list)
    pure_content_prompt: str
    self_check: StageSelfCheckDecision
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
        if self.primary_subject.role != "primary":
            raise ValueError("primary_subject must have the primary role")
        if any(subject.role != "secondary" for subject in self.secondary_subjects):
            raise ValueError("secondary_subjects must all have the secondary role")
        subject_ids = [
            self.primary_subject.subject_id,
            *(subject.subject_id for subject in self.secondary_subjects),
        ]
        if len(set(subject_ids)) != len(subject_ids):
            raise ValueError("content subject ids must be unique")
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
    required_single_instance_prompt_fragment: str
    review_feedback: list[str] = Field(
        default_factory=list,
        description="仅用于读取旧版审计制品，不得触发再次调用",
    )
    prompt_version: FusionStagePromptVersion = FUSION_STAGE_PROMPT_VERSION

    @field_validator(
        "frame_id",
        "original_storyboard_text",
        "workflow_identity_condition_summary",
        "target_image_prompt_language",
        "required_single_instance_prompt_fragment",
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


class ProtectedFactCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str
    preserved: bool
    final_image_evidence: str = Field(
        description="从 final_positive_prompt 中逐字复制的最短连续事实证据"
    )

    @field_validator("fact_id", "final_image_evidence", mode="before")
    @classmethod
    def _validate_text(cls, value: object, info) -> str:
        return _text(value, info.field_name)


class IdentityTraitCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trait: str
    preserved: bool
    final_prompt_evidence: str = Field(
        description=(
            "从 final_positive_prompt 中逐字复制、实际描述该身份特征的最短连续片段；"
            "不得跨过其他词语拼接"
        )
    )

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
    primary_subject_preserved: bool
    primary_subject_final_prompt_evidence: str = Field(
        description=(
            "必须逐字等于 content_stage_output.primary_subject.name；该名称也必须逐字"
            "存在于 final_positive_prompt"
        )
    )
    visual_anchor_replaces_primary_subject: Literal[False]
    identity_trait_checks: list[IdentityTraitCheck] = Field(min_length=1)
    final_manifestation: str
    target_visual_anchor_instance_count: Literal[1]
    other_scene_elements_inherit_identity_features: Literal[False]
    single_instance_prompt_evidence: str = Field(
        description=(
            "从 final_positive_prompt 中逐字复制、明确表示全画面只有一个身份实例的"
            "连续片段，例如“画面中只有一只斑点狗”"
        )
    )
    spatial_contact_and_lighting_relation: str
    inherited_existing_fusion_decision: bool
    continuity_change_reason: str
    final_positive_prompt: str
    final_negative_prompt: str
    self_check: StageSelfCheckDecision
    self_check_failures: list[str] = Field(default_factory=list)

    @field_validator(
        "selected_fusion_method",
        "final_manifestation",
        "single_instance_prompt_evidence",
        "primary_subject_final_prompt_evidence",
        "spatial_contact_and_lighting_relation",
        "continuity_change_reason",
        "final_positive_prompt",
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

    request_version: GenerationRequestVersion = GENERATION_REQUEST_VERSION
    task_id: str
    frame_id: str
    generation_attempt: Literal[1] = 1
    random_seed: int = Field(ge=1, le=2**64 - 1)
    target_visual_anchor_instance_count: Literal[1] = 1
    selected_fusion_method: str
    final_manifestation: str
    protected_fact_checks: list[ProtectedFactCheck] = Field(min_length=1)
    primary_subject_name: str
    primary_subject_preserved: Literal[True]
    primary_subject_final_prompt_evidence: str
    visual_anchor_replaces_primary_subject: Literal[False]
    identity_trait_checks: list[IdentityTraitCheck] = Field(min_length=1)
    single_instance_prompt_evidence: str
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
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized.pop("preflight_review_prompt_version", None)
        normalized.pop("preflight_review_decision", None)
        return normalized

    @field_validator(
        "task_id",
        "frame_id",
        "selected_fusion_method",
        "final_manifestation",
        "single_instance_prompt_evidence",
        "primary_subject_name",
        "primary_subject_final_prompt_evidence",
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
            normalized_trait = " ".join(check.trait.split()).casefold()
            if (
                (
                    evidence == normalized_identity_name
                    and normalized_trait != normalized_identity_name
                )
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
        primary_evidence = " ".join(
            self.primary_subject_final_prompt_evidence.split()
        ).casefold()
        if not primary_evidence or primary_evidence not in normalized_positive:
            raise ValueError(
                "primary-subject evidence must be present in the image prompt"
            )
        if self.identity_conditioning_mode == "reference_image":
            if self.identity_reference_condition is None:
                raise ValueError(
                    "reference-image generation requires a real reference condition"
                )
            expected_reference_version = (
                f"reference-image:{self.identity_reference_condition.asset_sha256}"
            )
            if (
                self.identity_reference_condition.resource_version
                != expected_reference_version
            ):
                raise ValueError(
                    "identity reference resource version must match its immutable digest"
                )
        elif self.identity_reference_condition is not None:
            raise ValueError(
                "text-profile generation cannot include a reference-image condition"
            )
        for fragment in self.target_visual_style.required_final_prompt_fragments:
            if fragment.casefold() not in normalized_positive:
                raise ValueError(
                    "image generation prompt dropped a required global style fragment"
                )
        normalized_negative = " ".join(self.final_negative_prompt.split()).casefold()
        if self.negative_prompt_supported:
            for fragment in self.target_visual_style.required_negative_prompt_fragments:
                if fragment.casefold() not in normalized_negative:
                    raise ValueError(
                        "image generation prompt dropped a required negative style fragment"
                    )
        if self.visible_text_policy.suppress_visible_text:
            if (
                not _contains_required_prompt_fragment_contract(
                    normalized_positive,
                    self.visible_text_policy.required_positive_prompt_fragment,
                )
                or (
                    self.negative_prompt_supported
                    and not _contains_required_prompt_fragment_contract(
                        normalized_negative,
                        self.visible_text_policy.required_negative_prompt_fragment,
                    )
                )
            ):
                raise ValueError(
                    "image generation prompt dropped visible-text suppression"
                )
        return self


class VisualAnchorTwoStageFrameResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    content_stage_input: ContentStageInput
    content_stage_output: ContentStageOutput
    fusion_stage_input: FusionStageInput
    fusion_stage_output: FusionStageOutput
    generation_request: VisualAnchorImageGenerationRequest
    content_attempt_count: int = Field(
        default=1,
        ge=1,
        le=2,
        description="旧版审计字段；新生成结果固定为 1",
    )
    content_retry_validation_codes: list[ContentStageValidationCode] = Field(
        default_factory=list,
        description="旧版审计字段；新生成结果固定为空",
    )
    fusion_attempt_count: int = Field(
        default=1,
        ge=1,
        le=2,
        description="旧版审计字段；新生成结果固定为 1",
    )

    @model_validator(mode="before")
    @classmethod
    def _discard_legacy_review_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized.pop("preflight_review_input", None)
        normalized.pop("preflight_review_output", None)
        return normalized

    @field_validator("frame_id", mode="before")
    @classmethod
    def _validate_frame_id(cls, value: object) -> str:
        return _text(value, "frame_id")

    @field_validator("content_retry_validation_codes")
    @classmethod
    def _validate_content_retry_validation_codes(
        cls,
        value: list[ContentStageValidationCode],
    ) -> list[ContentStageValidationCode]:
        requested = set(value)
        canonical = [
            code for code in _CONTENT_STAGE_VALIDATION_CODES if code in requested
        ]
        if value != canonical:
            raise ValueError(
                "content retry validation codes must be unique and canonical"
            )
        return value

    @model_validator(mode="after")
    def _validate_cross_stage_contract(self) -> "VisualAnchorTwoStageFrameResult":
        if self.content_attempt_count == 1 and self.content_retry_validation_codes:
            raise ValueError(
                "a single content attempt cannot contain retry validation codes"
            )
        if self.content_attempt_count > 1 and not self.content_retry_validation_codes:
            raise ValueError(
                "a retried content stage must record validation codes"
            )
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
            or self.generation_request.primary_subject_name
            != self.content_stage_output.primary_subject.name
            or self.generation_request.primary_subject_preserved
            != self.fusion_stage_output.primary_subject_preserved
            or self.generation_request.primary_subject_final_prompt_evidence
            != self.fusion_stage_output.primary_subject_final_prompt_evidence
            or self.generation_request.visual_anchor_replaces_primary_subject
            != self.fusion_stage_output.visual_anchor_replaces_primary_subject
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
