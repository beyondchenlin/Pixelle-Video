from __future__ import annotations

# ── Model / Enum tests ──

def test_field_id_enum_values():
    from web.ip_design.models import FieldId
    assert FieldId.NAME.value == "name"
    assert FieldId.LOGLINE.value == "logline"
    assert FieldId.IDENTITY_LOCK.value == "identity_lock"


def test_ip_profile_draft_defaults():
    from web.ip_design.models import IPProfileDraft
    draft = IPProfileDraft(series_visual_signature_profile_id="ip_1", name="Test")
    assert draft.series_visual_signature_profile_id == "ip_1"
    assert draft.name == "Test"
    assert draft.ip_type == "cartoon_animal"
    assert draft.logline == ""
    assert draft.identity_lock == []


def test_ip_profile_draft_all_fields():
    from web.ip_design.models import IPProfileDraft
    draft = IPProfileDraft(
        series_visual_signature_profile_id="ip_1",
        name="Test",
        ip_type="anime_human",
        logline="A test",
        visual_summary="Summary",
        identity_lock=["lock1"],
        minimal_traits=["trait1"],
        adaptable_slots=["slot1"],
    )
    assert draft.ip_type == "anime_human"
    assert draft.logline == "A test"
    assert draft.identity_lock == ["lock1"]


def test_asset_bible_draft_with_profiles():
    from web.ip_design.models import AssetBibleDraft, CharacterProfileDraft, IPProfileDraft
    draft = AssetBibleDraft(
        asset_bible_id="bible_1",
        ip_profiles=[
            IPProfileDraft(series_visual_signature_profile_id="ip_1", name="IP One"),
        ],
        character_profiles=[
            CharacterProfileDraft(character_id="char_1", display_name="Char One"),
        ],
    )
    assert len(draft.ip_profiles) == 1
    assert draft.ip_profiles[0].name == "IP One"
    assert draft.character_profiles[0].display_name == "Char One"


def test_scene_cast_draft():
    from web.ip_design.models import SceneCastDraft
    draft = SceneCastDraft(
        scene_cast_id="cast_1",
        storyboard_plan_id="plan_1",
        frame_id="frame_1",
        character_ids=["char_1", "char_2"],
        scene_id="scene_1",
        prop_ids=["prop_1"],
        style_id="style_1",
        continuity_notes=["note1"],
    )
    assert draft.scene_cast_id == "cast_1"
    assert draft.character_ids == ["char_1", "char_2"]
    assert draft.style_id == "style_1"


def test_list_asset_bibles_response():
    from web.ip_design.models import AssetBibleSummary, ListAssetBiblesResponse
    resp = ListAssetBiblesResponse(
        success=True,
        asset_bibles=[
            AssetBibleSummary(asset_bible_id="bible_1"),
        ],
    )
    assert resp.success is True
    assert len(resp.asset_bibles) == 1
    assert resp.asset_bibles[0].asset_bible_id == "bible_1"


def test_save_response():
    from web.ip_design.models import SaveResponse
    resp = SaveResponse(success=True, message="saved")
    assert resp.success is True
    assert resp.message == "saved"


def test_list_scene_casts_response():
    from web.ip_design.models import ListSceneCastsResponse
    resp = ListSceneCastsResponse(
        success=True,
        scene_casts=[{"scene_cast_id": "cast_1"}],
    )
    assert resp.success is True
    assert resp.scene_casts == [{"scene_cast_id": "cast_1"}]


def test_typed_response_base():
    from web.ip_design.models import TypedResponse
    resp = TypedResponse(success=True)
    assert resp.success is True
    assert resp.message == ""
    assert resp.errors == []


def test_preset_summary():
    from web.ip_design.models import PresetSummary
    preset = PresetSummary(preset_id="builtin_asset_bible_demo", display_name="Demo")
    assert preset.preset_id == "builtin_asset_bible_demo"
    assert preset.display_name == "Demo"


def test_import_preset_response():
    from web.ip_design.models import ImportPresetResponse
    resp = ImportPresetResponse(success=True, asset_bible_id="bible_1")
    assert resp.success is True
    assert resp.asset_bible_id == "bible_1"


# ── Session key tests ──

def test_ip_session_keys_structure():
    from web.ip_design.session_keys import IPSessionKeys
    keys = IPSessionKeys()
    assert keys.ASSET_BIBLE.select == "ip_design_asset_bible_select"
    assert keys.ASSET_BIBLE.asset_bible_id == "ip_design_asset_bible_id"
    assert keys.FORM.ip_profile_select == "ip_design_ip_profile_select"
    assert keys.FORM.name == "ip_design_ip_name"
    assert keys.FORM.logline == "ip_design_logline"
    assert keys.SCENE_CAST.scene_cast_id == "ip_design_scene_cast_id"
    assert keys.SCENE_CAST.frame_id == "ip_design_frame_id"
    assert keys.SCENE_CAST.character_ids == "ip_design_character_ids"
    assert keys.SCENE_CAST.prop_ids == "ip_design_prop_ids"
    assert keys.SCENE_CAST.style_id == "ip_design_style_id"
    assert keys.PRESET.select == "ip_design_builtin_asset_bible_preset_select"
    assert keys.PRESET.import_id == "ip_design_import_asset_bible_id"


def test_ip_session_keys_widget_keys_contains_form_fields():
    from web.ip_design.session_keys import IPSessionKeys
    keys = IPSessionKeys()
    widget = keys.FORM.widget_keys()
    assert "ip_design_ip_name" in widget
    assert "ip_design_logline" in widget
    assert len(widget) > 0


def test_form_session_key_names_match_scene_cast():
    from web.ip_design.models import SceneCastDraft
    from web.ip_design.session_keys import IPSessionKeys
    keys = IPSessionKeys()
    model_fields = set(SceneCastDraft.model_fields)
    key_attrs = {f.name for f in keys.SCENE_CAST.__class__.__dataclass_fields__.values()
                 if not f.name.startswith("_") and f.name != "select"}
    missing = model_fields - key_attrs
    assert not missing, (
        f"SceneCastDraft fields without SCENE_CAST key mapping: {missing}"
    )
    # Verify every key_attr resolves to a non-empty session state key
    for attr in key_attrs:
        key = getattr(keys.SCENE_CAST, attr)
        assert key and key.startswith("ip_design_"), f"Invalid key value for {attr}: {key}"


def test_form_session_key_names_match_model_fields():
    from web.ip_design.models import IPProfileDraft
    from web.ip_design.session_keys import IPSessionKeys
    keys = IPSessionKeys()
    model_fields = set(IPProfileDraft.model_fields)
    carrier_fields = {"identity_anchors", "variable_slots", "world_hint",
                      "style_hint", "image_text_palette", "metadata"}
    key_attrs = {f.name for f in keys.FORM.__class__.__dataclass_fields__.values()
                 if not f.name.startswith("_") and f.name not in ("ip_profile_select", "active_asset_tab")}
    missing = model_fields - key_attrs - carrier_fields
    assert not missing, (
        f"Model fields without session key mapping (breaks populate_form_from_model/build_model_from_form): {missing}"
    )
    # Verify every key_attr resolves to a non-empty session state key
    for attr in key_attrs:
        key = getattr(keys.FORM, attr)
        assert key and key.startswith("ip_design_"), f"Invalid key value for {attr}: {key}"


# ── _to_model helper tests ──

def test_to_ip_profile_draft():
    from web.ip_design.asset_bible_payloads import _to_ip_profile_draft
    from web.ip_design.models import IPProfileDraft
    data = {
        "series_visual_signature_profile_id": "ip_1",
        "name": "Test",
        "ip_type": "anime_human",
        "logline": "A test logline",
        "identity_lock": ["lock_a", "lock_b"],
    }
    draft = _to_ip_profile_draft(data)
    assert isinstance(draft, IPProfileDraft)
    assert draft.series_visual_signature_profile_id == "ip_1"
    assert draft.name == "Test"
    assert draft.ip_type == "anime_human"
    assert draft.logline == "A test logline"
    assert draft.identity_lock == ["lock_a", "lock_b"]


def test_to_ip_profile_draft_empty():
    from web.ip_design.asset_bible_payloads import _to_ip_profile_draft
    draft = _to_ip_profile_draft({})
    assert draft.series_visual_signature_profile_id == ""
    assert draft.ip_type == "cartoon_animal"
    assert draft.identity_lock == []


def test_to_character_profile_draft():
    from web.ip_design.asset_bible_payloads import _to_character_profile_draft
    draft = _to_character_profile_draft({
        "character_id": "char_1",
        "display_name": "Charlie",
        "role": "lead",
        "continuity_notes": ["note1"],
    })
    assert draft.character_id == "char_1"
    assert draft.display_name == "Charlie"
    assert draft.continuity_notes == ["note1"]


def test_to_scene_asset_draft():
    from web.ip_design.asset_bible_payloads import _to_scene_asset_draft
    draft = _to_scene_asset_draft({
        "scene_id": "scene_1",
        "display_name": "Forest",
    })
    assert draft.scene_id == "scene_1"
    assert draft.display_name == "Forest"


def test_to_prop_asset_draft():
    from web.ip_design.asset_bible_payloads import _to_prop_asset_draft
    draft = _to_prop_asset_draft({
        "prop_id": "prop_1",
        "display_name": "Sword",
    })
    assert draft.prop_id == "prop_1"


def test_to_style_profile_draft():
    from web.ip_design.asset_bible_payloads import _to_style_profile_draft
    draft = _to_style_profile_draft({
        "style_id": "style_1",
        "display_name": "Watercolor",
        "visual_style": "soft",
    })
    assert draft.style_id == "style_1"
    assert draft.visual_style == "soft"


def test_to_asset_bible_draft():
    from web.ip_design.asset_bible_payloads import _to_asset_bible_draft
    draft = _to_asset_bible_draft({
        "asset_bible_id": "bible_1",
        "ip_profiles": [
            {"series_visual_signature_profile_id": "ip_1", "name": "Hero"},
            {"series_visual_signature_profile_id": "ip_2", "name": "Sidekick"},
        ],
        "character_profiles": [
            {"character_id": "char_1", "display_name": "Alice"},
        ],
    })
    assert draft.asset_bible_id == "bible_1"
    assert len(draft.ip_profiles) == 2
    assert draft.ip_profiles[0].name == "Hero"
    assert len(draft.character_profiles) == 1
    assert draft.scene_assets == []
    assert draft.style_profiles == []


def test_to_scene_cast_draft():
    from web.ip_design.asset_bible_payloads import _to_scene_cast_draft
    draft = _to_scene_cast_draft({
        "scene_cast_id": "cast_1",
        "storyboard_plan_id": "plan_1",
        "frame_id": "frame_1",
        "character_ids": ["char_1", "char_2"],
        "prop_ids": ["prop_1"],
        "style_id": "style_1",
    })
    assert draft.scene_cast_id == "cast_1"
    assert draft.character_ids == ["char_1", "char_2"]
    assert draft.prop_ids == ["prop_1"]
    assert draft.style_id == "style_1"


def test_package_init_exports_all_model_symbols():
    from web.ip_design import __all__ as pkg_all
    from web.ip_design import models as _models

    assert len(_models.__all__) > 0, (
        "models.__all__ is empty — the assertions below would pass vacuously"
    )

    for name in _models.__all__:
        cls = getattr(_models, name)
        assert name in pkg_all, (
            f"{name} is in models.__all__ but missing from web.ip_design.__all__"
        )
        resolved = getattr(__import__("web.ip_design", fromlist=[name]), name)
        assert resolved is cls, (
            f"web.ip_design.{name} is {resolved!r}, expected {cls!r} "
            f"(likely missing from explicit import in web/ip_design/__init__.py)"
        )
