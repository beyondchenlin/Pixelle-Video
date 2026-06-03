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
                series_visual_signature_profile_id="ip_main",
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
                series_visual_signature_profile_id="ip_main",
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
        series_visual_signature_profile_id="ip_main",
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
        "series_visual_signature_profile_id": "ip_main",
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


@pytest.mark.parametrize(
    "palette_field,palette_payload",
    [
        (
            "color_palette",
            {"tie": {"hex": "#006BFF", "prompt": "tie #006BFF"}},
        ),
        (
            "image_text_palette",
            {"title": {"hex": "#5A2A12", "color_prompt": "ink #5A2A12"}},
        ),
        (
            "color_palette",
            {"tie": {"hex": "#006BFF", "accent_prompt": "tie #006BFF"}},
        ),
        (
            "color_palette",
            {"tie": {"hex": "#006BFF", "prompt": ["tie #006BFF"]}},
        ),
        (
            "image_text_palette",
            {"title": {"hex": "#5A2A12", "prompt": {"primary": "ink #5A2A12"}}},
        ),
    ],
)
def test_ip_profile_palette_prompt_fields_reject_hex_colors(palette_field, palette_payload):
    payload = {
        "series_visual_signature_profile_id": "ip_main",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "name": "正定向导兔",
        palette_field: palette_payload,
    }

    with pytest.raises(ValueError, match=palette_field):
        IPProfile(**payload)


def test_ip_profile_palette_non_prompt_annotations_allow_hex_text_and_round_trip():
    profile = IPProfile(
        series_visual_signature_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        color_palette={
            "tie": {
                "hex": "#006BFF",
                "prompt": "鲜明宝蓝色领带",
                "label": "brand #006BFF reference",
            },
        },
        image_text_palette={
            "title": {
                "hex": "#5A2A12",
                "prompt": "深棕色墨迹",
                "note": "legacy #5A2A12 swatch",
            },
        },
    )

    restored = IPProfile.from_dict(profile.to_dict())

    assert restored.color_palette["tie"]["label"] == "brand #006BFF reference"
    assert restored.image_text_palette["title"]["note"] == "legacy #5A2A12 swatch"


def test_ip_profile_palette_mapping_errors_name_palette_field():
    with pytest.raises(ValueError, match="color_palette"):
        IPProfile(
            series_visual_signature_profile_id="ip_main",
            workspace_id="workspace_1",
            project_id="project_1",
            name="正定向导兔",
            color_palette=("not", "a", "mapping"),
        )


def test_ip_profile_from_dict_rejects_string_tuple_payloads():
    with pytest.raises(ValueError, match="identity_lock"):
        IPProfile.from_dict(
            {
                "series_visual_signature_profile_id": "ip_main",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "name": "正定向导兔",
                "identity_lock": "abc",
            }
        )


def test_ip_profile_from_dict_rejects_forbidden_elements_string_payloads():
    with pytest.raises(ValueError, match="forbidden_elements"):
        IPProfile.from_dict(
            {
                "series_visual_signature_profile_id": "ip_main",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "name": "正定向导兔",
                "forbidden_elements": "abc",
            }
        )


def test_ip_profile_supports_universal_actor_fields():
    """New fields from the universal-actor redesign round-trip correctly."""
    profile = IPProfile(
        series_visual_signature_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子", "蓝色领结", "长耳朵"),
        ip_type="cartoon_animal",
        visual_summary="白色卡通兔子，蓝色领结，长耳朵，圆润脸型。",
        minimal_traits=("蓝色领结一角", "长耳朵轮廓"),
        default_slot_preference="prefer_supporting",
        role_presets=(
            "导游讲解者：温和的讲解者，面向场景做介绍手势",
            "情感陪伴者：安静的陪伴角色，与画面主体自然互动",
            "路人观察者：融入环境背景",
            "画面主角：占据画面主体位置",
            "画外不出镜：不出现在画面中",
        ),
        presence_spectrum=(
            "全身出镜：完整呈现角色形象",
            "半身出镜：展示上半身和表情",
            "局部细节：只露出特征性局部",
            "远景融入：作为场景中的小元素融入背景",
            "完全不出镜：该帧不出现IP角色",
        ),
        adaptable_slots=(
            "服装配饰：可根据场景穿不同的服装配饰",
            "手持道具：可根据场景持有不同道具",
            "动作姿势：可根据场景做不同动作",
            "表情神态：可根据场景产生不同表情",
        ),
    )

    restored = IPProfile.from_dict(profile.to_dict())

    assert restored.ip_type == "cartoon_animal"
    assert restored.visual_summary == "白色卡通兔子，蓝色领结，长耳朵，圆润脸型。"
    assert restored.minimal_traits == ("蓝色领结一角", "长耳朵轮廓")
    assert restored.default_slot_preference == "prefer_supporting"
    assert len(restored.role_presets) == 5
    assert restored.role_presets[0].startswith("导游讲解者")
    assert len(restored.presence_spectrum) == 5
    assert restored.presence_spectrum[-1].startswith("完全不出镜")
    assert len(restored.adaptable_slots) == 4


def test_ip_profile_preserves_legacy_fields():
    """Legacy fields (world_hint, style_hint, identity_anchors, variable_slots)
    are preserved through serialization even though they are no longer shown in UI."""
    profile = IPProfile(
        series_visual_signature_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        world_hint="正定古城",
        style_hint="清爽文旅插画风格",
        identity_lock=("白色卡通兔子",),
        identity_anchors=("蓝色领结", "长耳朵"),
        variable_slots=("表情", "动作", "站位"),
    )

    restored = IPProfile.from_dict(profile.to_dict())

    assert restored.world_hint == "正定古城"
    assert restored.style_hint == "清爽文旅插画风格"
    assert restored.identity_anchors == ("蓝色领结", "长耳朵")
    assert restored.variable_slots == ("表情", "动作", "站位")
