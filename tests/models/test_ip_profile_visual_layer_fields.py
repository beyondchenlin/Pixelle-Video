import pytest

from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle, IPStyleScope


def test_ip_profile_visual_layer_fields_round_trip():
    profile = IPProfile.from_dict(
        {
            "ip_profile_id": "teacher",
            "workspace_id": "workspace",
            "project_id": "project",
            "name": "Young Teacher",
            "rendering_style": "photorealistic_human",
            "style_scope": "ip_character_only",
            "exclusive_visual_layer": True,
            "style_boundary_rules": ["Only the IP human character may be photorealistic."],
        }
    )
    assert profile.rendering_style is IPRenderingStyle.PHOTOREALISTIC_HUMAN
    assert profile.style_scope is IPStyleScope.IP_CHARACTER_ONLY
    assert profile.exclusive_visual_layer is True
    assert profile.to_dict()["rendering_style"] == "photorealistic_human"


def test_ip_profile_rejects_unknown_rendering_style():
    with pytest.raises(ValueError):
        IPProfile.from_dict(
            {
                "ip_profile_id": "teacher",
                "workspace_id": "workspace",
                "project_id": "project",
                "name": "Young Teacher",
                "rendering_style": "real human maybe",
            }
        )
