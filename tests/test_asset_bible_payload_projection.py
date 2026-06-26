from __future__ import annotations


def _asset_bible_response() -> dict:
    return {
        "asset_bible_id": "bible_demo",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "ip_profiles": [
            {
                "series_visual_signature_profile_id": "ip_main",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "name": "Main IP",
                "logline": "Main logline",
                "world_hint": "Main world",
                "style_hint": "Main style",
                "identity_lock": ["white rabbit"],
                "identity_anchors": ["blue bow"],
                "identity_suppression_rules": ["hide ears in distant shots"],
                "variable_slots": ["pose"],
                "semantic_boundary": ["do not replace landmark"],
                "negative_constraints": ["no extra text"],
                "color_palette": {"tie": {"prompt": "bright blue bow"}},
                "image_text_palette": {"title": {"prompt": "ink title"}},
                "visible_text_whitelist": ["Chang Le Gate"],
                "metadata": {"source": "response"},
                "forbidden_elements": ["legacy field"],
            },
            {
                "series_visual_signature_profile_id": "ip_side",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "name": "Side IP",
                "identity_lock": ["side identity"],
                "identity_anchors": ["side badge"],
                "forbidden_elements": ["legacy field"],
            },
        ],
        "character_profiles": [
            {
                "character_id": "char_luna",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "display_name": "Luna",
                "role": "lead",
            }
        ],
        "scene_assets": [
            {
                "scene_id": "scene_lab",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "display_name": "Sky Lab",
            }
        ],
        "prop_assets": [
            {
                "prop_id": "prop_compass",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "display_name": "Compass",
            }
        ],
        "style_profiles": [
            {
                "style_id": "style_warm",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "display_name": "Warm Comic",
                "visual_style": "warm comic",
            }
        ],
        "metadata": {"owner": "ip-design"},
    }


def test_build_asset_bible_draft_payload_from_response_strips_response_only_fields():
    from web.utils.asset_bible_payloads import build_asset_bible_draft_payload_from_response

    payload = build_asset_bible_draft_payload_from_response(_asset_bible_response())

    assert "workspace_id" not in payload
    assert "asset_bible_id" not in payload
    assert "project_id" not in payload
    assert payload["metadata"] == {"owner": "ip-design"}
    assert payload["ip_profiles"][0] == {
        "series_visual_signature_profile_id": "ip_main",
        "name": "Main IP",
        "logline": "Main logline",
        "world_hint": "Main world",
        "style_hint": "Main style",
        "identity_lock": ["white rabbit"],
        "identity_anchors": ["blue bow"],
        "identity_suppression_rules": ["hide ears in distant shots"],
        "variable_slots": ["pose"],
        "semantic_boundary": ["do not replace landmark"],
        "negative_constraints": ["no extra text"],
        "forbidden_elements": ["legacy field"],
        "color_palette": {"tie": {"prompt": "bright blue bow"}},
        "image_text_palette": {"title": {"prompt": "ink title"}},
        "visible_text_whitelist": ["Chang Le Gate"],
        "metadata": {"source": "response"},
    }
    assert payload["character_profiles"] == [
        {"character_id": "char_luna", "display_name": "Luna", "role": "lead"}
    ]
    assert payload["scene_assets"] == [{"scene_id": "scene_lab", "display_name": "Sky Lab"}]
    assert payload["prop_assets"] == [{"prop_id": "prop_compass", "display_name": "Compass"}]
    assert payload["style_profiles"] == [
        {
            "style_id": "style_warm",
            "display_name": "Warm Comic",
            "visual_style": "warm comic",
        }
    ]


def test_upsert_ip_profile_draft_replaces_matching_profile_and_preserves_siblings():
    from web.utils.asset_bible_payloads import (
        build_asset_bible_draft_payload_from_response,
        upsert_ip_profile_draft,
    )

    payload = build_asset_bible_draft_payload_from_response(_asset_bible_response())
    updated = upsert_ip_profile_draft(
        payload,
        {
            "series_visual_signature_profile_id": "ip_main",
            "name": "Updated Main IP",
            "identity_lock": ["updated rabbit"],
            "identity_anchors": ["updated bow"],
        },
    )

    assert [profile["series_visual_signature_profile_id"] for profile in updated["ip_profiles"]] == [
        "ip_main",
        "ip_side",
    ]
    assert updated["ip_profiles"][0] == {
        "series_visual_signature_profile_id": "ip_main",
        "name": "Updated Main IP",
        "identity_lock": ["updated rabbit"],
        "identity_anchors": ["updated bow"],
    }
    assert updated["ip_profiles"][1]["name"] == "Side IP"
    assert updated["character_profiles"] == payload["character_profiles"]


def test_upsert_ip_profile_draft_appends_new_profile_when_id_is_new():
    from web.utils.asset_bible_payloads import (
        build_asset_bible_draft_payload_from_response,
        upsert_ip_profile_draft,
    )

    payload = build_asset_bible_draft_payload_from_response(_asset_bible_response())
    updated = upsert_ip_profile_draft(
        payload,
        {
            "series_visual_signature_profile_id": "ip_new",
            "name": "New IP",
            "identity_lock": ["new identity"],
        },
    )

    assert [profile["series_visual_signature_profile_id"] for profile in updated["ip_profiles"]] == [
        "ip_main",
        "ip_side",
        "ip_new",
    ]
    assert updated["ip_profiles"][2] == {
        "series_visual_signature_profile_id": "ip_new",
        "name": "New IP",
        "identity_lock": ["new identity"],
    }


def test_upsert_ip_profile_draft_adds_first_profile_to_empty_projected_asset_bible():
    from web.utils.asset_bible_payloads import (
        build_asset_bible_draft_payload_from_response,
        upsert_ip_profile_draft,
    )

    payload = build_asset_bible_draft_payload_from_response(
        {
            **_asset_bible_response(),
            "ip_profiles": [],
        }
    )
    updated = upsert_ip_profile_draft(
        payload,
        {
            "series_visual_signature_profile_id": "ip_main",
            "name": "Main IP",
            "identity_lock": ["white rabbit"],
        },
    )

    assert updated["ip_profiles"] == [
        {
            "series_visual_signature_profile_id": "ip_main",
            "name": "Main IP",
            "identity_lock": ["white rabbit"],
        }
    ]
    assert updated["character_profiles"] == [
        {"character_id": "char_luna", "display_name": "Luna", "role": "lead"}
    ]
