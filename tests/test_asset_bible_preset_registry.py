import json
from collections import Counter
from pathlib import Path

import pytest

from pixelle_video.models.asset_bible_preset import AssetBiblePreset
from pixelle_video.services.asset_bible_preset_registry import (
    DEFAULT_ASSET_BIBLE_PRESET_ROOT,
    AssetBiblePresetRegistry,
)


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
                    "series_visual_signature_profile_id": "ip_main",
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


def test_default_registry_root_is_absolute_and_cwd_independent(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    registry = AssetBiblePresetRegistry()
    preset = registry.get_preset("builtin_asset_bible_zhengding_guide")

    assert DEFAULT_ASSET_BIBLE_PRESET_ROOT.is_absolute()
    assert preset.preset_id == "builtin_asset_bible_zhengding_guide"


def test_registry_rejects_duplicate_preset_ids(tmp_path: Path):
    root = tmp_path / "asset_bibles"
    root.mkdir()
    (root / "demo.json").write_text(json.dumps(_preset_payload()), encoding="utf-8")
    duplicate = _preset_payload()
    duplicate["display_name"] = "Duplicate Demo"
    (root / "duplicate.json").write_text(json.dumps(duplicate), encoding="utf-8")
    registry = AssetBiblePresetRegistry(root=root)

    with pytest.raises(ValueError, match="duplicate asset bible preset_id"):
        registry.list_presets()


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
    assert preset.description == "通用陪伴式卡通 IP 角色，可适配不同内容场景。"
    assert preset.tags == ("卡通角色", "通用IP", "陪伴式")
    assert profile.name == "正定向导兔"
    assert profile.ip_type == "cartoon_animal"
    assert profile.visual_summary == (
        "白色卡通兔子，蓝色领结，长耳朵，浅粉色耳朵内侧，圆润脸型，清爽亲和的卡通造型。"
    )
    assert profile.identity_lock == (
        "白色卡通兔子",
        "蓝色领结",
        "长耳朵",
        "浅粉色耳朵内侧",
        "圆润脸型",
        "清爽亲和的卡通造型",
    )
    assert profile.minimal_traits == ("蓝色领结一角", "长耳朵轮廓")
    assert profile.default_slot_preference == "prefer_supporting"
    assert len(profile.role_presets) == 5
    assert profile.role_presets[0].startswith("导游讲解者")
    assert len(profile.presence_spectrum) == 5
    assert profile.presence_spectrum[-1].startswith("完全不出镜")
    assert len(profile.adaptable_slots) == 5
    assert profile.world_hint == "通用场景，可适配文旅、日常、情感、美食等不同内容域。"
    assert profile.style_hint == (
        "清爽亲和的彩色扁平卡通角色插画，圆润简洁的造型，干净边缘与柔和明快的固定配色"
    )
    assert profile.rendering_style.value == "flat_illustration"
    assert profile.style_scope.value == "ip_character_only"
    assert profile.style_boundary_rules == (
        "该视觉风格仅作用于正定向导兔本身，不扩散到叙事人物、环境、道具和背景",
    )
    assert profile.semantic_boundary == (
        "它是可融入场景的陪伴式角色",
        "不是历史人物",
        "不是宗教人物",
        "不能替代画面中的真实主体",
    )
    assert profile.negative_constraints == (
        "不能变成人类",
        "不能变成其他动物",
        "不能变成写实恐怖动物",
        "不能变成真人玩偶",
        "不能变成蓝色兔子",
        "不要出现错误文字和乱码",
    )
    assert profile.visible_text_whitelist == ()
    assert profile.color_palette == {
        "body": {"prompt": "身体和脸部保持纯白色"},
        "bow_tie": {"prompt": "领结保持明亮蓝色"},
        "inner_ears": {"prompt": "耳朵内侧保持浅粉色"},
    }
    assert profile.variable_slots == ()
    assert preset.asset_bible.metadata == {}
    assert duplicates == []
