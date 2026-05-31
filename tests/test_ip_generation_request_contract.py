from pixelle_video.contracts.ip_generation_request import (
    FORMAL_CONTENT_IP_WORLD_FIELDS,
    HELPER_ONLY_CONTENT_IP_WORLD_FIELDS,
    REMOVED_CONTENT_IP_WORLD_FIELDS,
    build_formal_content_ip_world_payload,
    dropped_content_ip_world_fields,
)


def test_formal_field_set_is_narrow():
    assert FORMAL_CONTENT_IP_WORLD_FIELDS == {
        "ip_enabled",
        "ip_asset_bible_id",
        "ip_profile_id",
        "generation_world_hint",
        "visual_expression_mode",
        "visual_structure_mode",
        "visual_participation_mode",
        "visual_role_mode",
        "visual_consistency_mode",
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
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
            "generation_world_hint": "script world",
            "visual_expression_mode": "explanatory_diagram",
            "visual_structure_mode": "workflow",
            "visual_participation_mode": "guide_explainer",
            "ip_profile_world_hint": "asset helper",
            "generation_world_hint_source": "ip_default",
            "generation_notes": "old notes",
            "slot_preference_override": "prefer_main",
            "presence_strength": "strong",
            "unknown": "ignored",
        }
    )

    assert payload == {
        "ip_enabled": True,
        "ip_asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
        "generation_world_hint": "script world",
        "visual_expression_mode": "explanatory_diagram",
        "visual_structure_mode": "workflow",
        "visual_participation_mode": "guide_explainer",
        "visual_role_mode": "auto",
        "visual_consistency_mode": "off",
        "effective_visual_role_mode": "auto",
    }
    assert "unknown" not in payload


def test_enabled_ip_omits_blank_ids_but_preserves_world_hint():
    assert build_formal_content_ip_world_payload(
        {
            "ip_enabled": True,
            "ip_asset_bible_id": "   ",
            "ip_profile_id": "\t\n",
            "generation_world_hint": "  request world  ",
        }
    ) == {
        "ip_enabled": True,
        "visual_expression_mode": "auto",
        "visual_structure_mode": "auto",
        "visual_participation_mode": "auto",
        "visual_role_mode": "auto",
        "visual_consistency_mode": "off",
        "effective_visual_role_mode": "auto",
        "generation_world_hint": "request world",
    }


def test_disabled_ip_still_carries_request_world_hint():
    assert build_formal_content_ip_world_payload(
        {
            "ip_enabled": False,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
            "generation_world_hint": "world without selected IP",
        }
    ) == {
        "ip_enabled": False,
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
