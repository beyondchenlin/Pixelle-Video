from pixelle_video.services.visual_anchor_manual_acceptance import (
    VisualAnchorManualAcceptanceChecks,
)


def _checks_payload() -> dict[str, bool]:
    return {
        "protected_facts_visible": True,
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


def test_manual_acceptance_uses_deterministic_fusion_audit_check():
    checks = VisualAnchorManualAcceptanceChecks.model_validate(
        {
            **_checks_payload(),
            "deterministic_fusion_and_post_audit_complete": True,
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

    assert checks.deterministic_fusion_and_post_audit_complete is True
    assert "preflight_and_post_audit_complete" not in checks.model_dump()
