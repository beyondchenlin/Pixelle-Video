from __future__ import annotations

from web.ip_design.form_fields import (
    IP_PROFILE_FORM_FIELDS,
    derive_ip_profile_carrier_fields,
    ip_profile_form_field_names,
)
from web.ip_design.models import IPProfileDraft
from web.ip_design.session_keys import IPSessionKeys


def test_ip_profile_form_schema_has_session_key_and_help_for_every_field() -> None:
    for field in IP_PROFILE_FORM_FIELDS:
        assert getattr(IPSessionKeys.FORM, field.name)
        assert field.label_key.startswith("ip_design.")
        assert field.help_key.startswith("ip_design.help.")


def test_ip_profile_form_schema_tracks_expected_model_fields() -> None:
    assert ip_profile_form_field_names() == {
        "ip_profile_id",
        "name",
        "ip_type",
        "logline",
        "visual_summary",
        "identity_lock",
        "color_palette",
        "minimal_traits",
        "adaptable_slots",
        "default_slot_preference",
        "presence_spectrum",
        "role_presets",
        "negative_constraints",
        "semantic_boundary",
        "identity_suppression_rules",
        "forbidden_elements",
        "visible_text_whitelist",
    }


def test_ip_profile_carrier_fields_are_derived_from_model() -> None:
    carrier_fields = dict(derive_ip_profile_carrier_fields(IPProfileDraft))
    assert carrier_fields == {
        "identity_anchors": list,
        "variable_slots": list,
        "world_hint": str,
        "style_hint": str,
        "image_text_palette": dict,
        "metadata": dict,
    }
    assert set(carrier_fields).isdisjoint(ip_profile_form_field_names())
