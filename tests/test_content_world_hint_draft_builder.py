from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.services.content_world_hint_draft_builder import build_world_hint_draft


def test_build_world_hint_draft_renders_compact_chinese_text():
    profile = ContentWorldProfile(
        summary="正定古城清晨漫游",
        time_space="当代正定古城，清晨，长乐门到城楼一线",
        visual_environment="青砖城墙、晨雾、水汽和古城街巷",
        story_constraints="不能替代真实古建筑与历史主体",
        ip_integration_guidance="IP 作为陪伴式向导，低侵入融入",
    )

    draft = build_world_hint_draft(profile, prompt_language="zh_CN")

    assert "正定古城清晨漫游" in draft
    assert "不能替代真实古建筑与历史主体" in draft
    assert "IP 作为陪伴式向导" in draft
    assert "summary" not in draft
    assert "generation_world_profile" not in draft


def test_build_world_hint_draft_skips_empty_fields():
    profile = ContentWorldProfile(
        summary="古城漫游",
        atmosphere=None,
        story_constraints=None,
    )

    draft = build_world_hint_draft(profile, prompt_language="zh_CN")

    assert "古城漫游" in draft
    assert "None" not in draft


def test_build_world_hint_draft_supports_english():
    profile = ContentWorldProfile(
        summary="Ancient city dawn walk",
        ip_integration_guidance="The IP appears as a low-intrusion guide.",
    )

    draft = build_world_hint_draft(profile, prompt_language="en_US")

    assert "Ancient city dawn walk" in draft
    assert "low-intrusion guide" in draft
