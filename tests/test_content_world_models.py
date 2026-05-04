import pytest

from pixelle_video.models.content_world import (
    ContentWorldHintSource,
    ContentWorldProfile,
)


def test_content_world_profile_serializes_structured_fields():
    profile = ContentWorldProfile(
        summary="正定古城清晨漫游",
        time_space="当代正定古城，清晨，长乐门到城楼",
        visual_environment="青砖城墙、滹沱河水汽、古城街巷",
        atmosphere="温柔、历史感、慢节奏",
        cultural_context="中国古城文旅叙事",
        story_constraints="不能让 IP 替代长乐门、历史建筑或真实历史主体",
        ip_integration_guidance="IP 作为陪伴式向导，低侵入融入画面",
        hint_source=ContentWorldHintSource.MANUAL,
    )

    payload = profile.to_dict()
    restored = ContentWorldProfile.from_dict(payload)

    assert payload["summary"] == "正定古城清晨漫游"
    assert payload["hint_source"] == "manual"
    assert restored.ip_integration_guidance == "IP 作为陪伴式向导，低侵入融入画面"


def test_content_world_profile_compacts_blank_fields_to_none():
    profile = ContentWorldProfile(
        summary="  正定古城  ",
        time_space=" ",
        visual_environment=None,
        atmosphere="历史感",
    )

    assert profile.summary == "正定古城"
    assert profile.time_space is None
    assert profile.visual_environment is None
    assert profile.atmosphere == "历史感"


def test_content_world_profile_rejects_hex_color_leakage():
    with pytest.raises(ValueError, match="hex color"):
        ContentWorldProfile(summary="主色 #FFFFFF 的古城")
