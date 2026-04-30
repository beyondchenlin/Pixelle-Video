import pytest

from pixelle_video.models.asset_bible import (
    AssetBible,
    CharacterProfile,
    PropAsset,
    SceneAsset,
    StyleProfile,
)
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.scene_casting import (
    SceneCastValidationError,
    validate_scene_cast,
)


def build_asset_bible() -> AssetBible:
    return AssetBible(
        asset_bible_id="bible_demo",
        workspace_id="workspace_1",
        project_id="project_1",
        character_profiles=[
            CharacterProfile(
                character_id="char_luna",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Luna",
            )
        ],
        scene_assets=[
            SceneAsset(
                scene_id="scene_lab",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Sky Lab",
            )
        ],
        prop_assets=[
            PropAsset(
                prop_id="prop_compass",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Star Compass",
            )
        ],
        style_profiles=[
            StyleProfile(
                style_id="style_warm_comic",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Warm Comic",
                visual_style="warm comic",
            )
        ],
    )


def build_scene_cast(**overrides) -> SceneCast:
    params = {
        "scene_cast_id": "cast_frame_1",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "asset_bible_id": "bible_demo",
        "character_ids": ["char_luna"],
        "scene_id": "scene_lab",
        "prop_ids": ["prop_compass"],
        "style_id": "style_warm_comic",
    }
    params.update(overrides)
    return SceneCast(**params)


def test_validate_scene_cast_accepts_known_asset_references():
    validated = validate_scene_cast(build_scene_cast(), build_asset_bible())

    assert validated.scene_cast_id == "cast_frame_1"
    assert validated.character_ids == ("char_luna",)


@pytest.mark.parametrize(
    "overrides, field_name, invalid_id",
    [
        ({"character_ids": ["char_missing"]}, "character_ids", "char_missing"),
        ({"scene_id": "scene_missing"}, "scene_id", "scene_missing"),
        ({"prop_ids": ["prop_missing"]}, "prop_ids", "prop_missing"),
        ({"style_id": "style_missing"}, "style_id", "style_missing"),
    ],
)
def test_validate_scene_cast_rejects_unknown_asset_ids(
    overrides,
    field_name,
    invalid_id,
):
    with pytest.raises(SceneCastValidationError) as exc_info:
        validate_scene_cast(build_scene_cast(**overrides), build_asset_bible())

    assert exc_info.value.field_name == field_name
    assert exc_info.value.invalid_id == invalid_id
    assert invalid_id in str(exc_info.value)


@pytest.mark.parametrize(
    "overrides, field_name",
    [
        ({"workspace_id": "other_workspace"}, "workspace_id"),
        ({"project_id": "other_project"}, "project_id"),
        ({"asset_bible_id": "other_bible"}, "asset_bible_id"),
    ],
)
def test_validate_scene_cast_rejects_cross_asset_bible_ownership(overrides, field_name):
    with pytest.raises(SceneCastValidationError) as exc_info:
        validate_scene_cast(build_scene_cast(**overrides), build_asset_bible())

    assert exc_info.value.field_name == field_name

