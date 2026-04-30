import pytest

from pixelle_video.models.scene_cast import SceneCast


def test_scene_cast_round_trips_frame_level_asset_references():
    scene_cast = SceneCast(
        scene_cast_id="cast_frame_1",
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        asset_bible_id="bible_demo",
        character_ids=["char_luna", "char_milo"],
        scene_id="scene_lab",
        prop_ids=["prop_compass"],
        style_id="style_warm_comic",
        continuity_notes=["Luna keeps round goggles visible."],
        metadata={"source": "manual"},
    )

    restored = SceneCast.from_dict(scene_cast.to_dict())

    assert restored.scene_cast_id == "cast_frame_1"
    assert restored.workspace_id == "workspace_1"
    assert restored.project_id == "project_1"
    assert restored.storyboard_plan_id == "storyboard_plan_1"
    assert restored.frame_id == "frame_0001"
    assert restored.asset_bible_id == "bible_demo"
    assert restored.character_ids == ("char_luna", "char_milo")
    assert restored.scene_id == "scene_lab"
    assert restored.prop_ids == ("prop_compass",)
    assert restored.style_id == "style_warm_comic"
    assert restored.continuity_notes == ("Luna keeps round goggles visible.",)
    assert restored.to_dict()["metadata"] == {"source": "manual"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "scene_cast_id": "cast_frame_1",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "storyboard_plan_id": "storyboard_plan_1",
            "frame_id": "",
            "asset_bible_id": "bible_demo",
        },
        {
            "scene_cast_id": "cast_frame_1",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "storyboard_plan_id": "storyboard_plan_1",
            "frame_id": "frame_0001",
            "asset_bible_id": "bible_demo",
            "character_ids": ["char_luna", "char_luna"],
        },
        {
            "scene_cast_id": "cast_frame_1",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "storyboard_plan_id": "storyboard_plan_1",
            "frame_id": "frame_0001",
            "asset_bible_id": "bible_demo",
            "prop_ids": "prop_compass",
        },
    ],
)
def test_scene_cast_rejects_invalid_identity_or_reference_lists(payload):
    with pytest.raises(ValueError):
        SceneCast.from_dict(payload)


def test_scene_cast_references_ids_only_not_embedded_assets():
    with pytest.raises(ValueError, match="character_ids"):
        SceneCast(
            scene_cast_id="cast_frame_1",
            workspace_id="workspace_1",
            project_id="project_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
            asset_bible_id="bible_demo",
            character_ids=[{"character_id": "char_luna"}],
        )

