from pixelle_video.services.visual_anchor_manual_acceptance import (
    MANUAL_ACCEPTANCE_SCHEMA_VERSION,
    VisualAnchorManualAcceptanceChecks,
    VisualAnchorManualAcceptanceRecord,
)


def _checks_payload() -> dict[str, bool]:
    return {
        "story_content_visible": True,
        "identity_present": True,
        "identity_instance_count_one": True,
        "identity_traits_recognizable": True,
        "perspective_lighting_material_natural": True,
        "support_contact_occlusion_natural": True,
        "no_sticker_floating_or_penetration": True,
        "size_and_position_fit_current_composition": True,
        "unique_final_plan_submitted": True,
        "first_generation_reference_bound": True,
        "continuous_scene_consistency": True,
        "original_first_generation_unmodified": True,
    }


def test_manual_acceptance_uses_generation_binding_audit_check():
    checks = VisualAnchorManualAcceptanceChecks.model_validate(
        {
            **_checks_payload(),
            "generation_binding_and_post_audit_complete": True,
        }
    )

    assert checks.all_passed is True
    assert "preflight_and_post_audit_complete" not in checks.model_dump()


def test_legacy_preflight_audit_check_is_migrated_on_read():
    checks = VisualAnchorManualAcceptanceChecks.model_validate(
        {
            **_checks_payload(),
            "preflight_and_post_audit_complete": True,
        }
    )

    assert checks.generation_binding_and_post_audit_complete is True
    assert "preflight_and_post_audit_complete" not in checks.model_dump()


def test_legacy_manual_acceptance_record_is_upgraded_on_read():
    record = VisualAnchorManualAcceptanceRecord.model_validate(
        {
            "schema_version": "visual_anchor_manual_acceptance.v1",
            "task_id": "task-a",
            "acceptance_batch_id": "batch-a",
            "acceptance_round": 1,
            "sample_id": "sample-a",
            "frame_id": "frame-a",
            "random_seed": 1,
            "image_sha256": "a" * 64,
            "rendered_audit_sha256": "b" * 64,
            "first_request_binding_sha256": "c" * 64,
            "status": "passed",
            "checks": {
                **_checks_payload(),
                "preflight_and_post_audit_complete": True,
            },
            "reviewer": "tester",
        }
    )

    payload = record.model_dump(mode="json")
    assert payload["schema_version"] == MANUAL_ACCEPTANCE_SCHEMA_VERSION
    assert "preflight_and_post_audit_complete" not in payload["checks"]
    assert payload["checks"]["story_content_visible"] is True
