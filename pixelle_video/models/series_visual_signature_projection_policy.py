from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)

DEFAULT_MAX_PROJECTION_FRAMES = 512
DEFAULT_MAX_BASE_PROMPT_CHARS = 20_000
DEFAULT_MAX_NEGATIVE_PROMPT_CHARS = 12_000
DEFAULT_MAX_REQUIRED_SUBJECTS = 64
DEFAULT_MAX_REQUIRED_SUBJECT_CHARS = 256
DEFAULT_MAX_IDENTITY_TRAITS = 32
DEFAULT_MAX_PROJECTION_AUDIT_BYTES = 512 * 1024
DEFAULT_MAX_FINAL_POSITIVE_PROMPT_CHARS = 1200
DEFAULT_MAX_FINAL_NEGATIVE_PROMPT_CHARS = 800
DEFAULT_MAX_CANONICAL_IDENTITY_CHARS = 400
DEFAULT_MAX_MAIN_AND_SUBJECT_CHARS = 400
DEFAULT_MAX_PLACEMENT_AND_FUSION_CHARS = 300
DEFAULT_MAX_STYLE_CHARS = 100

# Only fixed protocol field names may be retained in observability. Unknown
# compatibility keys may be accepted at runtime while callers migrate, but their
# names are user-controlled input and therefore must never be persisted.
_AUDITABLE_SERIES_VISUAL_SIGNATURE_OPTION_KEYS = frozenset(
    {
        "series_visual_signature_enabled",
        "series_visual_signature_asset_bible_id",
        "series_visual_signature_profile_id",
        "series_visual_signature_role",
        "series_visual_signature_role_was_explicit",
        "series_visual_signature_max_area_ratio",
        "series_visual_signature_user_hint",
        "series_visual_signature_pipeline_version",
        "series_visual_signature_expression_mode",
        "series_visual_signature_structure_mode",
        "series_visual_signature_participation_mode",
        "series_visual_signature_mode",
        "series_visual_signature_consistency_mode",
        "series_visual_signature_presentation_mode",
        "series_visual_signature_enforcement",
        "series_visual_signature_fallback_enabled",
        "series_visual_signature_fallback_mode",
        "series_visual_signature_min_visibility",
        "series_visual_signature_strategy",
    }
)


@dataclass(frozen=True)
class SeriesVisualSignatureProjectionBudget:
    """Deterministic complexity limits for canonical signature projection.

    Wall-clock time is deliberately not used as a correctness boundary because
    host load is nondeterministic. These limits constrain the amount of text and
    structured data the projection layer is allowed to process and persist.
    """

    max_frames_per_batch: int = DEFAULT_MAX_PROJECTION_FRAMES
    max_base_prompt_chars: int = DEFAULT_MAX_BASE_PROMPT_CHARS
    max_negative_prompt_chars: int = DEFAULT_MAX_NEGATIVE_PROMPT_CHARS
    max_required_subjects_per_frame: int = DEFAULT_MAX_REQUIRED_SUBJECTS
    max_required_subject_chars: int = DEFAULT_MAX_REQUIRED_SUBJECT_CHARS
    max_identity_traits: int = DEFAULT_MAX_IDENTITY_TRAITS
    max_audit_bytes: int = DEFAULT_MAX_PROJECTION_AUDIT_BYTES
    max_final_positive_prompt_chars: int = DEFAULT_MAX_FINAL_POSITIVE_PROMPT_CHARS
    max_final_negative_prompt_chars: int = DEFAULT_MAX_FINAL_NEGATIVE_PROMPT_CHARS
    max_canonical_identity_chars: int = DEFAULT_MAX_CANONICAL_IDENTITY_CHARS
    max_main_and_subject_chars: int = DEFAULT_MAX_MAIN_AND_SUBJECT_CHARS
    max_placement_and_fusion_chars: int = DEFAULT_MAX_PLACEMENT_AND_FUSION_CHARS
    max_style_chars: int = DEFAULT_MAX_STYLE_CHARS

    def __post_init__(self) -> None:
        for field_name in (
            "max_frames_per_batch",
            "max_base_prompt_chars",
            "max_negative_prompt_chars",
            "max_required_subjects_per_frame",
            "max_required_subject_chars",
            "max_identity_traits",
            "max_audit_bytes",
            "max_final_positive_prompt_chars",
            "max_final_negative_prompt_chars",
            "max_canonical_identity_chars",
            "max_main_and_subject_chars",
            "max_placement_and_fusion_chars",
            "max_style_chars",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")

    def assert_batch_inputs(
        self,
        *,
        frame_ids: Sequence[str],
        base_prompts: Sequence[str],
        base_negative_prompts: Sequence[str | None],
    ) -> None:
        count = len(frame_ids)
        if count > self.max_frames_per_batch:
            raise ValueError(
                "visual signature projection frame count exceeds deterministic runtime budget: "
                f"{count} > {self.max_frames_per_batch}"
            )
        for index, prompt in enumerate(base_prompts):
            prompt_length = len(str(prompt or ""))
            if prompt_length > self.max_base_prompt_chars:
                raise ValueError(
                    "visual signature projection base prompt exceeds deterministic runtime budget "
                    f"at index {index}: {prompt_length} > {self.max_base_prompt_chars}"
                )
        for index, prompt in enumerate(base_negative_prompts):
            prompt_length = len(str(prompt or ""))
            if prompt_length > self.max_negative_prompt_chars:
                raise ValueError(
                    "visual signature projection negative prompt exceeds deterministic runtime budget "
                    f"at index {index}: {prompt_length} > {self.max_negative_prompt_chars}"
                )

    def assert_required_subjects(self, required_subjects: Sequence[str]) -> None:
        if len(required_subjects) > self.max_required_subjects_per_frame:
            raise ValueError(
                "visual signature projection required-subject count exceeds deterministic runtime budget: "
                f"{len(required_subjects)} > {self.max_required_subjects_per_frame}"
            )
        for subject in required_subjects:
            if len(subject) > self.max_required_subject_chars:
                raise ValueError(
                    "visual signature projection required subject exceeds deterministic runtime budget: "
                    f"{len(subject)} > {self.max_required_subject_chars} characters"
                )

    def assert_profile(self, profile: VisualSignatureProfileSnapshot) -> None:
        if len(profile.identity_traits) > self.max_identity_traits:
            raise ValueError(
                "visual signature projection identity-trait count exceeds deterministic runtime budget: "
                f"{len(profile.identity_traits)} > {self.max_identity_traits}"
            )
        if len(profile.canonical_identity_clause) > self.max_canonical_identity_chars:
            raise ValueError(
                "visual signature canonical identity exceeds deterministic prompt budget: "
                f"{len(profile.canonical_identity_clause)} > {self.max_canonical_identity_chars}"
            )

    def assert_audit_size(self, audit_payload: Mapping[str, Any]) -> int:
        serialized = json.dumps(
            audit_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        size = len(serialized)
        if size > self.max_audit_bytes:
            raise ValueError(
                "visual signature projection audit exceeds deterministic persistence budget: "
                f"{size} > {self.max_audit_bytes} bytes"
            )
        return size


@dataclass(frozen=True)
class SeriesVisualSignatureProjectionMetrics:
    """Executable denominator contract for canonical production projection.

    Coverage means that an expected frame reached a projection attempt. Projection
    success is tracked separately so a failed-but-observed frame cannot be confused
    with a frame that was never attempted.
    """

    expected_frame_count: int
    attempted_frame_count: int
    projected_frame_count: int
    unique_frame_count: int

    def __post_init__(self) -> None:
        for field_name in (
            "expected_frame_count",
            "attempted_frame_count",
            "projected_frame_count",
            "unique_frame_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.attempted_frame_count > self.expected_frame_count:
            raise ValueError("attempted_frame_count cannot exceed expected_frame_count")
        if self.projected_frame_count > self.attempted_frame_count:
            raise ValueError("projected_frame_count cannot exceed attempted_frame_count")
        if self.unique_frame_count > self.projected_frame_count:
            raise ValueError("unique_frame_count cannot exceed projected_frame_count")

    @property
    def duplicate_frame_count(self) -> int:
        return self.projected_frame_count - self.unique_frame_count

    @property
    def failed_frame_count(self) -> int:
        return self.attempted_frame_count - self.projected_frame_count

    @property
    def not_attempted_frame_count(self) -> int:
        return self.expected_frame_count - self.attempted_frame_count

    @property
    def coverage_rate(self) -> float:
        """Fraction of expected frames that reached a projection attempt."""

        if self.expected_frame_count <= 0:
            return 0.0
        return self.attempted_frame_count / self.expected_frame_count

    @property
    def projection_success_rate(self) -> float:
        """Fraction of expected frames that completed projection successfully."""

        if self.expected_frame_count <= 0:
            return 0.0
        return self.projected_frame_count / self.expected_frame_count

    @property
    def all_frames_passed(self) -> bool:
        return (
            self.expected_frame_count > 0
            and self.attempted_frame_count == self.expected_frame_count
            and self.projected_frame_count == self.expected_frame_count
            and self.coverage_rate == 1.0
            and self.projection_success_rate == 1.0
            and self.failed_frame_count == 0
            and self.not_attempted_frame_count == 0
            and self.duplicate_frame_count == 0
        )

    def to_dict(self) -> dict[str, int | float | bool]:
        return {
            "expected_frame_count": self.expected_frame_count,
            "attempted_frame_count": self.attempted_frame_count,
            "projected_frame_count": self.projected_frame_count,
            "unique_frame_count": self.unique_frame_count,
            "duplicate_frame_count": self.duplicate_frame_count,
            "failed_frame_count": self.failed_frame_count,
            "not_attempted_frame_count": self.not_attempted_frame_count,
            "coverage_rate": self.coverage_rate,
            "projection_success_rate": self.projection_success_rate,
            "all_frames_passed": self.all_frames_passed,
        }


@dataclass(frozen=True)
class SeriesVisualSignatureProjectionAuditPolicy:
    """Privacy, retention and runtime-ownership contract for projection observability.

    Projection audit is planning metadata, not a second prompt store. Raw prompt,
    subject, identity-trait, user-hint and world-hint text is forbidden. Runtime
    ownership is encoded as invariants rather than a migration switch: there is
    one canonical production identity owner and compatibility may normalize input
    only. Retention is inherited atomically from the parent planning snapshot;
    projection observability cannot create an independent TTL or cleanup lifecycle.
    This avoids reintroducing a second storage or runtime authority.
    """

    schema_version: str = "series_visual_signature_projection_audit.v3"
    payload_class: str = "bounded_hash_count_only"
    retention_owner: str = "parent_planning_snapshot"
    retention_mode: str = "inherit_parent_planning_snapshot_atomically"
    independent_retention_allowed: bool = False
    independent_cleanup_allowed: bool = False
    production_identity_owner: str = "canonical_v45_projection"
    compatibility_adapter_scope: str = "input_normalization_only"
    legacy_prompt_runtime_allowed: bool = False
    shadow_runtime_allowed: bool = False
    raw_prompt_retention: str = "forbidden"
    raw_subject_retention: str = "forbidden"
    raw_identity_trait_retention: str = "forbidden"
    raw_request_hint_retention: str = "forbidden"

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "schema_version": self.schema_version,
            "payload_class": self.payload_class,
            "retention_owner": self.retention_owner,
            "retention_mode": self.retention_mode,
            "independent_retention_allowed": self.independent_retention_allowed,
            "independent_cleanup_allowed": self.independent_cleanup_allowed,
            "production_identity_owner": self.production_identity_owner,
            "compatibility_adapter_scope": self.compatibility_adapter_scope,
            "legacy_prompt_runtime_allowed": self.legacy_prompt_runtime_allowed,
            "shadow_runtime_allowed": self.shadow_runtime_allowed,
            "contains_raw_prompt": False,
            "contains_raw_subjects": False,
            "contains_raw_identity_traits": False,
            "contains_raw_request_hints": False,
            "raw_prompt_retention": self.raw_prompt_retention,
            "raw_subject_retention": self.raw_subject_retention,
            "raw_identity_trait_retention": self.raw_identity_trait_retention,
            "raw_request_hint_retention": self.raw_request_hint_retention,
        }

    def request_audit_dict(
        self,
        request: SeriesVisualSignatureRequest,
    ) -> dict[str, Any]:
        compatibility_option_keys = {
            str(key) for key in request.compatibility_options.keys()
        }
        auditable_option_keys = sorted(
            compatibility_option_keys & _AUDITABLE_SERIES_VISUAL_SIGNATURE_OPTION_KEYS
        )
        return {
            "enabled": request.enabled,
            "pipeline_version": request.pipeline_version,
            "profile_id": request.profile_id,
            "role": request.role.value,
            "role_was_explicit": request.role_was_explicit,
            "max_area_ratio": request.max_area_ratio,
            "compatibility_option_keys": auditable_option_keys,
            "compatibility_option_count": len(compatibility_option_keys),
            "unrecognized_compatibility_option_count": len(
                compatibility_option_keys
                - _AUDITABLE_SERIES_VISUAL_SIGNATURE_OPTION_KEYS
            ),
            "contains_user_hint": request.user_hint is not None,
            "contains_generation_world_hint": request.generation_world_hint is not None,
        }

    def profile_reference_dict(
        self,
        profile: VisualSignatureProfileSnapshot,
    ) -> dict[str, Any]:
        return {
            "profile_id": profile.profile_id,
            "identity_trait_count": len(profile.identity_traits),
            "core_identity_trait_count": len(profile.core_identity_traits),
            "supporting_identity_trait_count": len(profile.supporting_identity_traits),
            "style_safe_trait_count": len(profile.style_safe_traits),
            "forbidden_trait_count": len(profile.forbidden_traits),
            "source_asset_count": len(profile.source_asset_ids),
        }


DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_BUDGET = SeriesVisualSignatureProjectionBudget()
DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_AUDIT_POLICY = (
    SeriesVisualSignatureProjectionAuditPolicy()
)


__all__ = [
    "DEFAULT_MAX_CANONICAL_IDENTITY_CHARS",
    "DEFAULT_MAX_FINAL_NEGATIVE_PROMPT_CHARS",
    "DEFAULT_MAX_FINAL_POSITIVE_PROMPT_CHARS",
    "DEFAULT_MAX_MAIN_AND_SUBJECT_CHARS",
    "DEFAULT_MAX_PLACEMENT_AND_FUSION_CHARS",
    "DEFAULT_MAX_PROJECTION_AUDIT_BYTES",
    "DEFAULT_MAX_PROJECTION_FRAMES",
    "DEFAULT_MAX_STYLE_CHARS",
    "DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_AUDIT_POLICY",
    "DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_BUDGET",
    "SeriesVisualSignatureProjectionAuditPolicy",
    "SeriesVisualSignatureProjectionBudget",
    "SeriesVisualSignatureProjectionMetrics",
]
