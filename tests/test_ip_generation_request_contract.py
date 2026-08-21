from pixelle_video.contracts.ip_generation_request import (
    FORMAL_CONTENT_IP_WORLD_FIELDS,
    HELPER_ONLY_CONTENT_IP_WORLD_FIELDS,
    REMOVED_CONTENT_IP_WORLD_FIELDS,
    build_formal_content_ip_world_payload,
    dropped_content_ip_world_fields,
)


def test_formal_field_set_is_narrow():
    assert FORMAL_CONTENT_IP_WORLD_FIELDS == {
        "series_visual_signature_enabled",
        "series_visual_signature_asset_bible_id",
        "series_visual_signature_profile_id",
        "generation_world_hint",
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
        "series_visual_signature_llm_prompt_assembly_enabled",
        "mandatory_content_bound_anchor",
        "series_visual_signature_contract_version",
        "series_visual_signature_output_validation_mode",
        "series_visual_signature_output_max_attempts",
    }


def test_removed_and_helper_field_sets_are_not_formal():
    forbidden = HELPER_ONLY_CONTENT_IP_WORLD_FIELDS | REMOVED_CONTENT_IP_WORLD_FIELDS
    assert FORMAL_CONTENT_IP_WORLD_FIELDS.isdisjoint(forbidden)
    assert REMOVED_CONTENT_IP_WORLD_FIELDS == {
        "generation_notes",
        "slot_preference_override",
        "presence_strength",
    }


def test_build_formal_payload_drops_helper_and_removed_fields():
    payload = build_formal_content_ip_world_payload(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
            "generation_world_hint": "script world",
            "series_visual_signature_expression_mode": "explanatory_diagram",
            "series_visual_signature_structure_mode": "workflow",
        "series_visual_signature_participation_mode": "guide_explainer",
        "ip_profile_world_hint": "asset helper",
        "series_visual_signature_presentation_mode": "content_bound_mandatory_ip",
        "series_visual_signature_enforcement": "strict",
        "series_visual_signature_fallback_enabled": False,
        "series_visual_signature_fallback_mode": "disabled",
        "series_visual_signature_min_visibility": "prominent",
        "generation_world_hint_source": "ip_default",
        "generation_notes": "old notes",
            "slot_preference_override": "prefer_main",
            "presence_strength": "strong",
            "unknown": "ignored",
        }
    )

    assert payload == {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "bible_demo",
        "series_visual_signature_profile_id": "ip_main",
        "generation_world_hint": "script world",
        "series_visual_signature_expression_mode": "explanatory_diagram",
        "series_visual_signature_structure_mode": "workflow",
        "series_visual_signature_participation_mode": "guide_explainer",
        "series_visual_signature_mode": "supporting_integration",
        "series_visual_signature_consistency_mode": "off",
        "series_visual_signature_presentation_mode": "content_bound_mandatory_ip",
        "series_visual_signature_enforcement": "strict",
        "series_visual_signature_fallback_enabled": False,
        "series_visual_signature_fallback_mode": "disabled",
        "series_visual_signature_min_visibility": "clear",
        "series_visual_signature_llm_prompt_assembly_enabled": False,
        "mandatory_content_bound_anchor": True,
        "series_visual_signature_contract_version": "final_visual_prompt_contract.v4_6",
        "series_visual_signature_output_validation_mode": "required",
        "series_visual_signature_output_max_attempts": 3,
        "effective_series_visual_signature_mode": "supporting_integration",
    }
    assert "unknown" not in payload


def test_enabled_ip_omits_blank_ids_but_preserves_world_hint():
    assert build_formal_content_ip_world_payload(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "   ",
            "series_visual_signature_profile_id": "\t\n",
            "generation_world_hint": "  request world  ",
        }
    ) == {
        "series_visual_signature_enabled": True,
        "series_visual_signature_expression_mode": "auto",
        "series_visual_signature_structure_mode": "auto",
        "series_visual_signature_participation_mode": "auto",
        "series_visual_signature_mode": "supporting_integration",
        "series_visual_signature_consistency_mode": "off",
        "series_visual_signature_presentation_mode": "content_bound_mandatory_ip",
        "series_visual_signature_enforcement": "strict",
        "series_visual_signature_fallback_enabled": False,
        "series_visual_signature_fallback_mode": "disabled",
        "series_visual_signature_min_visibility": "clear",
        "series_visual_signature_llm_prompt_assembly_enabled": False,
        "mandatory_content_bound_anchor": True,
        "series_visual_signature_contract_version": "final_visual_prompt_contract.v4_6",
        "series_visual_signature_output_validation_mode": "required",
        "series_visual_signature_output_max_attempts": 3,
        "effective_series_visual_signature_mode": "supporting_integration",
        "generation_world_hint": "request world",
    }


def test_disabled_ip_still_carries_request_world_hint():
    assert build_formal_content_ip_world_payload(
        {
            "series_visual_signature_enabled": False,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
            "generation_world_hint": "world without selected IP",
        }
    ) == {
        "series_visual_signature_enabled": False,
        "generation_world_hint": "world without selected IP",
    }


def test_string_false_does_not_enable_formal_content_ip_payload():
    assert build_formal_content_ip_world_payload(
        {
            "series_visual_signature_enabled": "false",
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
            "generation_world_hint": "world without selected IP",
        }
    ) == {
        "series_visual_signature_enabled": False,
        "generation_world_hint": "world without selected IP",
    }


def test_dropped_content_ip_world_fields_reports_only_known_non_formal_fields():
    assert dropped_content_ip_world_fields(
        {
            "ip_profile_world_hint": "asset helper",
            "generation_notes": "old notes",
            "unknown": "ignored",
        }
    ) == {"ip_profile_world_hint", "generation_notes"}
