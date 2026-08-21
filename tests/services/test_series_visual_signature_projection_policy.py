from __future__ import annotations

import json

import pytest

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.series_visual_signature_projection_policy import (
    SeriesVisualSignatureProjectionAuditPolicy,
    SeriesVisualSignatureProjectionBudget,
    SeriesVisualSignatureProjectionMetrics,
)
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionError,
    SeriesVisualSignatureProjectionService,
)


def _request() -> SeriesVisualSignatureRequest:
    return SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "guide",
        }
    )


def _profile() -> VisualSignatureProfileSnapshot:
    return VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        identity_traits=("black spots", "red collar"),
    )


def _project(
    *,
    service: SeriesVisualSignatureProjectionService | None = None,
    base_prompt: str = "worker operates a machine",
    primary_subject: str = "worker",
):
    return (service or SeriesVisualSignatureProjectionService()).project_batch(
        base_prompts=[base_prompt],
        frame_ids=["frame-1"],
        frame_contexts=[{"primary_subject": primary_subject}],
        request=_request(),
        profile=_profile(),
    )


def test_projection_audit_has_explicit_denominator_and_full_coverage() -> None:
    audit = _project().audit_dict()

    assert audit["schema_version"] == "series_visual_signature_projection_audit.v4"
    assert audit["status"] == "passed"
    assert audit["expected_frame_count"] == 1
    assert audit["attempted_frame_count"] == 1
    assert audit["projected_frame_count"] == 1
    assert audit["unique_frame_count"] == 1
    assert audit["duplicate_frame_count"] == 0
    assert audit["failed_frame_count"] == 0
    assert audit["not_attempted_frame_count"] == 0
    assert audit["coverage_rate"] == 1.0
    assert audit["projection_success_rate"] == 1.0
    assert audit["all_frames_passed"] is True


def test_projection_metrics_separate_observation_coverage_from_success_rate() -> None:
    metrics = SeriesVisualSignatureProjectionMetrics(
        expected_frame_count=4,
        attempted_frame_count=3,
        projected_frame_count=2,
        unique_frame_count=2,
    )

    assert metrics.coverage_rate == pytest.approx(0.75)
    assert metrics.projection_success_rate == pytest.approx(0.5)
    assert metrics.failed_frame_count == 1
    assert metrics.not_attempted_frame_count == 1
    assert metrics.all_frames_passed is False


def test_projection_audit_encodes_single_runtime_ownership() -> None:
    policy = _project().audit_dict()["audit_policy"]

    assert policy["production_identity_owner"] == (
        "mandatory_content_bound_v46_projection"
    )
    assert policy["compatibility_adapter_scope"] == "input_normalization_only"
    assert policy["legacy_prompt_runtime_allowed"] is False
    assert policy["shadow_runtime_allowed"] is False


def test_projection_audit_forbids_raw_prompt_subject_and_identity_retention() -> None:
    raw_prompt = "worker operates a machine"
    raw_subject = "worker"
    identity_trait = "black spots"
    audit = _project(base_prompt=raw_prompt, primary_subject=raw_subject).audit_dict()
    serialized = json.dumps(audit, ensure_ascii=False, sort_keys=True)

    assert audit["audit_policy"]["payload_class"] == "bounded_hash_count_only"
    assert audit["audit_policy"]["retention_owner"] == "parent_planning_snapshot"
    assert (
        audit["audit_policy"]["retention_mode"]
        == "inherit_parent_planning_snapshot_atomically"
    )
    assert audit["audit_policy"]["independent_retention_allowed"] is False
    assert audit["audit_policy"]["independent_cleanup_allowed"] is False
    assert audit["audit_policy"]["contains_raw_prompt"] is False
    assert audit["audit_policy"]["contains_raw_subjects"] is False
    assert audit["audit_policy"]["contains_raw_identity_traits"] is False
    assert audit["audit_policy"]["contains_raw_request_hints"] is False
    assert raw_prompt not in serialized
    assert identity_trait not in serialized
    assert f'"{raw_subject}"' not in serialized


def test_request_audit_never_persists_user_controlled_compatibility_key_names() -> None:
    sentinel = "private-compatibility-key-918273"
    request = SeriesVisualSignatureRequest(
        compatibility_options={
            "series_visual_signature_mode": "auto",
            f"series_visual_signature_{sentinel}": "private-value",
        }
    )

    audit = SeriesVisualSignatureProjectionAuditPolicy().request_audit_dict(request)
    serialized = json.dumps(audit, ensure_ascii=False, sort_keys=True)

    assert audit["compatibility_option_keys"] == ["series_visual_signature_mode"]
    assert audit["compatibility_option_count"] == 2
    assert audit["unrecognized_compatibility_option_count"] == 1
    assert sentinel not in serialized
    assert "private-value" not in serialized


def test_projection_failure_audit_has_denominator_and_no_raw_cause_text() -> None:
    raw_subject = "private-subject-918273"
    service = SeriesVisualSignatureProjectionService(
        budget=SeriesVisualSignatureProjectionBudget(max_required_subject_chars=5)
    )

    with pytest.raises(SeriesVisualSignatureProjectionError) as exc_info:
        _project(service=service, primary_subject=raw_subject)

    audit = exc_info.value.audit_dict()
    serialized = json.dumps(audit, ensure_ascii=False, sort_keys=True)
    assert audit["status"] == "failed"
    assert audit["expected_frame_count"] == 1
    assert audit["attempted_frame_count"] == 1
    assert audit["projected_frame_count"] == 0
    assert audit["failed_frame_count"] == 1
    assert audit["not_attempted_frame_count"] == 0
    assert audit["coverage_rate"] == 1.0
    assert audit["projection_success_rate"] == 0.0
    assert audit["reason_code"] == "projection_budget_exceeded"
    assert audit["exception_type"] == "ValueError"
    assert raw_subject not in serialized


def test_projection_failure_marks_remaining_frames_not_attempted() -> None:
    service = SeriesVisualSignatureProjectionService(
        budget=SeriesVisualSignatureProjectionBudget(max_required_subject_chars=5)
    )

    with pytest.raises(SeriesVisualSignatureProjectionError) as exc_info:
        service.project_batch(
            base_prompts=["one", "two", "three"],
            frame_ids=["frame-1", "frame-2", "frame-3"],
            frame_contexts=[
                {"primary_subject": "worker"},
                {"primary_subject": "owner"},
                {"primary_subject": "robot"},
            ],
            request=_request(),
            profile=_profile(),
        )

    audit = exc_info.value.audit_dict()
    assert audit["attempted_frame_count"] == 1
    assert audit["projected_frame_count"] == 0
    assert audit["failed_frame_count"] == 1
    assert audit["not_attempted_frame_count"] == 2
    assert audit["coverage_rate"] == pytest.approx(1 / 3)
    assert audit["projection_success_rate"] == 0.0


def test_projection_budget_rejects_too_many_frames_before_projection() -> None:
    service = SeriesVisualSignatureProjectionService(
        budget=SeriesVisualSignatureProjectionBudget(max_frames_per_batch=1)
    )

    with pytest.raises(ValueError, match="frame count exceeds deterministic runtime budget"):
        service.project_batch(
            base_prompts=["worker at machine", "owner at desk"],
            frame_ids=["frame-1", "frame-2"],
            frame_contexts=[
                {"primary_subject": "worker"},
                {"primary_subject": "owner"},
            ],
            request=_request(),
            profile=_profile(),
        )


def test_projection_budget_rejects_oversized_base_prompt() -> None:
    service = SeriesVisualSignatureProjectionService(
        budget=SeriesVisualSignatureProjectionBudget(max_base_prompt_chars=12)
    )

    with pytest.raises(ValueError, match="base prompt exceeds deterministic runtime budget"):
        _project(service=service, base_prompt="x" * 13)


def test_projection_budget_rejects_subject_count_and_subject_length() -> None:
    count_limited = SeriesVisualSignatureProjectionService(
        budget=SeriesVisualSignatureProjectionBudget(max_required_subjects_per_frame=1)
    )
    with pytest.raises(SeriesVisualSignatureProjectionError) as count_error:
        count_limited.project_batch(
            base_prompts=["worker and owner"],
            frame_ids=["frame-1"],
            frame_contexts=[
                {
                    "primary_subject": "worker",
                    "secondary_subjects": ["owner"],
                }
            ],
            request=_request(),
            profile=_profile(),
        )
    assert count_error.value.reason_code == "projection_budget_exceeded"

    length_limited = SeriesVisualSignatureProjectionService(
        budget=SeriesVisualSignatureProjectionBudget(max_required_subject_chars=5)
    )
    with pytest.raises(SeriesVisualSignatureProjectionError) as length_error:
        _project(service=length_limited, primary_subject="worker")
    assert length_error.value.reason_code == "projection_budget_exceeded"


def test_projection_budget_rejects_excessive_identity_traits() -> None:
    service = SeriesVisualSignatureProjectionService(
        budget=SeriesVisualSignatureProjectionBudget(max_identity_traits=1)
    )

    with pytest.raises(ValueError, match="identity-trait count exceeds"):
        service.project_batch(
            base_prompts=["worker operates a machine"],
            frame_ids=["frame-1"],
            frame_contexts=[{"primary_subject": "worker"}],
            request=_request(),
            profile=_profile(),
        )


def test_projection_budget_rejects_oversized_audit_before_publish() -> None:
    service = SeriesVisualSignatureProjectionService(
        budget=SeriesVisualSignatureProjectionBudget(max_audit_bytes=64)
    )

    with pytest.raises(ValueError, match="audit exceeds deterministic persistence budget"):
        _project(service=service)


def test_projection_rejects_empty_batch_instead_of_reporting_false_success() -> None:
    with pytest.raises(ValueError, match="at least one frame"):
        SeriesVisualSignatureProjectionService().project_batch(
            base_prompts=[],
            frame_ids=[],
            frame_contexts=[],
            request=_request(),
            profile=_profile(),
        )
