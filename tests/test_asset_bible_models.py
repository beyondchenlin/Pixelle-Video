import pytest

from pixelle_video.models.asset_bible import (
    AssetBible,
    CharacterProfile,
    IPProfile,
    PropAsset,
    SceneAsset,
    StyleProfile,
)


def test_asset_bible_round_trips_ip_and_visual_assets():
    bible = AssetBible(
        asset_bible_id="bible_demo",
        workspace_id="workspace_1",
        project_id="project_1",
        ip_profiles=[
            IPProfile(
                ip_profile_id="ip_main",
                workspace_id="workspace_1",
                project_id="project_1",
                name="Pixelle Demo",
                logline="A warm AI comic world.",
                world_hint="Soft futuristic city with friendly machines.",
                style_hint="clean comic panels, warm rim light",
                forbidden_elements=["photorealistic gore", "brand logos"],
                metadata={"tone": "hopeful"},
            )
        ],
        character_profiles=[
            CharacterProfile(
                character_id="char_luna",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Luna",
                role="lead inventor",
                visual_description="short silver hair, amber jacket",
                personality="curious and precise",
                continuity_notes=["always wears round goggles"],
            )
        ],
        scene_assets=[
            SceneAsset(
                scene_id="scene_lab",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Sky Lab",
                visual_description="floating workshop above clouds",
                environment_notes=["large crescent window"],
            )
        ],
        prop_assets=[
            PropAsset(
                prop_id="prop_compass",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Star Compass",
                visual_description="brass compass with blue hologram",
                usage_notes=["glows when a clue is nearby"],
            )
        ],
        style_profiles=[
            StyleProfile(
                style_id="style_warm_comic",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Warm Comic",
                visual_style="expressive comic in warm pastel colors",
                world_style="optimistic science-fantasy",
                provider_prompt="warm comic, clean line art, pastel palette",
                negative_prompt="photorealistic, text, watermark",
            )
        ],
        metadata={"source": "unit-test"},
    )

    restored = AssetBible.from_dict(bible.to_dict())

    assert restored.asset_bible_id == "bible_demo"
    assert restored.workspace_id == "workspace_1"
    assert restored.project_id == "project_1"
    assert restored.ip_profiles[0].forbidden_elements == (
        "photorealistic gore",
        "brand logos",
    )
    assert restored.character_profiles[0].continuity_notes == (
        "always wears round goggles",
    )
    assert restored.scene_assets[0].environment_notes == ("large crescent window",)
    assert restored.prop_assets[0].usage_notes == ("glows when a clue is nearby",)
    assert restored.style_profiles[0].provider_prompt == (
        "warm comic, clean line art, pastel palette"
    )
    assert restored.to_dict()["metadata"] == {"source": "unit-test"}


@pytest.mark.parametrize(
    "payload",
    [
        {"asset_bible_id": "bible_demo", "workspace_id": "", "project_id": "project_1"},
        {"asset_bible_id": "bible_demo", "workspace_id": "workspace_1", "project_id": ""},
        {
            "asset_bible_id": "bible_demo",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "character_profiles": [
                {
                    "character_id": "char_luna",
                    "workspace_id": "workspace_1",
                    "project_id": "other",
                    "display_name": "Luna",
                }
            ],
        },
        {
            "asset_bible_id": "bible_demo",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "style_profiles": [
                {
                    "style_id": "style_text",
                    "workspace_id": "workspace_1",
                    "project_id": "project_1",
                    "display_name": "Text Style",
                    "visual_style": "Should not accept text rendering fields.",
                    "caption_style": {},
                }
            ],
        },
    ],
)
def test_asset_bible_rejects_invalid_or_cross_project_assets(payload):
    with pytest.raises(ValueError):
        AssetBible.from_dict(payload)


def test_style_profile_rejects_text_rendering_style_metadata():
    with pytest.raises(ValueError, match="caption_style"):
        StyleProfile(
            style_id="style_warm_comic",
            workspace_id="workspace_1",
            project_id="project_1",
            display_name="Warm Comic",
            visual_style="warm comic panels",
            metadata={"caption_style": {"font_size": 24}},
        )


@pytest.mark.parametrize(
    "asset_factory, field_name",
    [
        (
            lambda: IPProfile(
                ip_profile_id="ip_main",
                workspace_id="workspace_1",
                project_id="project_1",
                name="Main IP",
                forbidden_elements=["", "brand logos"],
            ),
            "forbidden_elements",
        ),
        (
            lambda: CharacterProfile(
                character_id="char_luna",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Luna",
                continuity_notes=["round goggles", "round goggles"],
            ),
            "continuity_notes",
        ),
    ],
)
def test_asset_profiles_reject_empty_or_duplicate_id_lists(asset_factory, field_name):
    with pytest.raises(ValueError, match=field_name):
        asset_factory()


def test_ip_profile_supports_identity_locks_color_tokens_and_text_rules():
    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子", "长耳朵", "圆润脸型"),
        identity_anchors=("蓝色领带", "浅粉色耳朵内侧"),
        variable_slots=("动作", "表情", "服装", "道具", "站位"),
        semantic_boundary=("不能替代历史建筑", "不能替代宗教人物"),
        negative_constraints=("避免贴纸感", "避免多余文字"),
        color_palette={
            "body": {"hex": "#FFFFFF", "prompt": "纯白色身体"},
            "tie": {"hex": "#006BFF", "prompt": "鲜明宝蓝色领带"},
        },
        image_text_palette={
            "title": {"hex": "#5A2A12", "prompt": "深棕色墨迹"},
        },
        visible_text_whitelist=("长乐门", "正定古城"),
    )

    restored = IPProfile.from_dict(profile.to_dict())

    assert restored.identity_lock == ("白色卡通兔子", "长耳朵", "圆润脸型")
    assert restored.variable_slots == ("动作", "表情", "服装", "道具", "站位")
    assert restored.color_palette["tie"]["prompt"] == "鲜明宝蓝色领带"
    assert restored.visible_text_whitelist == ("长乐门", "正定古城")


@pytest.mark.parametrize("field_name", ["logline", "world_hint", "style_hint"])
def test_ip_profile_rejects_hex_colors_in_prompt_text_fields(field_name):
    payload = {
        "ip_profile_id": "ip_main",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "name": "正定向导兔",
        field_name: "use #FFFFFF as a prompt color",
    }

    with pytest.raises(ValueError, match=field_name):
        IPProfile(**payload)


def test_non_ip_asset_text_tuples_preserve_existing_hex_color_behavior():
    character = CharacterProfile(
        character_id="char_luna",
        workspace_id="workspace_1",
        project_id="project_1",
        display_name="Luna",
        continuity_notes=("#FFFFFF badge stays visible",),
    )
    scene = SceneAsset(
        scene_id="scene_lab",
        workspace_id="workspace_1",
        project_id="project_1",
        display_name="Sky Lab",
        environment_notes=("#006BFF light strips",),
    )
    prop = PropAsset(
        prop_id="prop_compass",
        workspace_id="workspace_1",
        project_id="project_1",
        display_name="Star Compass",
        usage_notes=("#5A2A12 engraving",),
    )

    assert character.continuity_notes == ("#FFFFFF badge stays visible",)
    assert scene.environment_notes == ("#006BFF light strips",)
    assert prop.usage_notes == ("#5A2A12 engraving",)
