import json
from collections import Counter
from pathlib import Path

import pytest

from pixelle_video.models.asset_bible_preset import AssetBiblePreset
from pixelle_video.services.asset_bible_preset_registry import AssetBiblePresetRegistry


def _preset_payload() -> dict:
    return {
        "preset_id": "builtin_asset_bible_demo",
        "revision": "2026-05-04.1",
        "source": "builtin",
        "display_name": "Demo IP",
        "description": "Demo preset.",
        "tags": ["demo"],
        "preview_asset_path": "resources/presets/asset_bibles/previews/demo.png",
        "asset_bible": {
            "asset_bible_id": "demo_bible",
            "workspace_id": "__builtin__",
            "project_id": "__builtin__",
            "ip_profiles": [
                {
                    "ip_profile_id": "ip_main",
                    "workspace_id": "__builtin__",
                    "project_id": "__builtin__",
                    "name": "Demo IP",
                    "identity_lock": ["white cartoon rabbit"],
                    "identity_anchors": ["blue bow tie"],
                }
            ],
            "character_profiles": [],
            "scene_assets": [],
            "prop_assets": [],
            "style_profiles": [],
            "metadata": {},
        },
    }


def test_asset_bible_preset_validates_asset_bible_payload():
    preset = AssetBiblePreset.from_dict(_preset_payload())

    assert preset.preset_id == "builtin_asset_bible_demo"
    assert preset.revision == "2026-05-04.1"
    assert preset.asset_bible.asset_bible_id == "demo_bible"
    assert preset.to_summary_dict()["display_name"] == "Demo IP"


def test_asset_bible_preset_defaults_missing_tags_to_empty_tuple():
    payload = _preset_payload()
    del payload["tags"]

    preset = AssetBiblePreset.from_dict(payload)

    assert preset.tags == ()
    assert preset.to_summary_dict()["tags"] == []


def test_asset_bible_preset_rejects_string_tags():
    payload = _preset_payload()
    payload["tags"] = "demo"

    with pytest.raises(ValueError, match="tags"):
        AssetBiblePreset.from_dict(payload)


def test_asset_bible_preset_rejects_empty_string_tags():
    payload = _preset_payload()
    payload["tags"] = ""

    with pytest.raises(ValueError, match="tags"):
        AssetBiblePreset.from_dict(payload)


def test_asset_bible_preset_rejects_explicit_none_tags():
    payload = _preset_payload()
    payload["tags"] = None

    with pytest.raises(ValueError, match="tags"):
        AssetBiblePreset.from_dict(payload)


def test_asset_bible_preset_rejects_duplicate_tags():
    payload = _preset_payload()
    payload["tags"] = ["demo", "demo"]

    with pytest.raises(ValueError, match="tags"):
        AssetBiblePreset.from_dict(payload)


def test_asset_bible_preset_rejects_non_sequence_tags():
    payload = _preset_payload()
    payload["tags"] = 123

    with pytest.raises(ValueError, match="tags"):
        AssetBiblePreset.from_dict(payload)


def test_registry_loads_json_presets_from_root(tmp_path: Path):
    root = tmp_path / "asset_bibles"
    root.mkdir()
    (root / "demo.json").write_text(json.dumps(_preset_payload()), encoding="utf-8")

    registry = AssetBiblePresetRegistry(root=root)

    assert [item.preset_id for item in registry.list_presets()] == [
        "builtin_asset_bible_demo"
    ]
    assert registry.get_preset("builtin_asset_bible_demo").display_name == "Demo IP"


def test_registry_builds_project_asset_bible_with_origin_metadata(tmp_path: Path):
    root = tmp_path / "asset_bibles"
    root.mkdir()
    (root / "demo.json").write_text(json.dumps(_preset_payload()), encoding="utf-8")
    registry = AssetBiblePresetRegistry(root=root)

    asset_bible = registry.build_project_asset_bible(
        preset_id="builtin_asset_bible_demo",
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="demo_project_bible",
        imported_at="2026-05-04T00:00:00Z",
    )

    assert asset_bible.workspace_id == "workspace_1"
    assert asset_bible.project_id == "project_1"
    assert asset_bible.asset_bible_id == "demo_project_bible"
    assert asset_bible.ip_profiles[0].workspace_id == "workspace_1"
    assert asset_bible.ip_profiles[0].project_id == "project_1"
    assert asset_bible.metadata["source_kind"] == "imported"
    assert asset_bible.metadata["origin_preset_id"] == "builtin_asset_bible_demo"
    assert asset_bible.metadata["origin_revision"] == "2026-05-04.1"


def test_registry_rejects_unknown_preset(tmp_path: Path):
    registry = AssetBiblePresetRegistry(root=tmp_path)

    with pytest.raises(KeyError, match="unknown asset bible preset"):
        registry.get_preset("missing")


def test_packaged_zhengding_guide_preset_is_valid():
    registry = AssetBiblePresetRegistry()

    preset = registry.get_preset("builtin_asset_bible_zhengding_guide")
    profile = preset.asset_bible.ip_profiles[0]
    combined = list(profile.identity_lock) + list(profile.identity_anchors)
    duplicates = [item for item, count in Counter(combined).items() if count > 1]

    assert preset.display_name == "正定向导兔"
    assert preset.description == "面向正定古城文旅短视频的陪伴式导游 IP。"
    assert preset.tags == ("文旅", "正定", "导游IP", "卡通角色")
    assert profile.name == "正定向导兔"
    assert profile.world_hint == "正定古城、城墙、古寺、青砖、历史文化旅游。"
    assert (
        profile.style_hint
        == "清爽文旅插画风格，干净线条，柔和自然光，温暖色彩，适合短视频导览画面。"
    )
    assert profile.variable_slots == (
        "表情",
        "动作",
        "站位",
        "手持地图",
        "手持导览旗",
        "讲解姿势",
        "与游客或古城场景的距离",
        "出场强度",
    )
    assert profile.visible_text_whitelist == ("正定", "古城", "导览")
    assert profile.semantic_boundary == (
        "它是陪伴式古城导游和文旅吉祥物",
        "不是历史人物",
        "不是宗教人物",
        "不是佛像",
        "不能替代正定古城城墙寺庙碑刻等真实主体",
    )
    assert profile.negative_constraints == (
        "不要替代古城主体",
        "不要遮挡佛像寺庙城墙等核心内容",
        "不要出现错误文字",
        "不要出现乱码",
        "不要变成蓝色兔子",
        "不要变成真人玩偶",
    )
    assert preset.asset_bible.metadata == {}
    assert duplicates == []
