from pathlib import Path

from web.components.storyboard_preview import (
    build_frame_override_payload,
    collect_storyboard_preview_overrides,
)


def test_build_frame_override_payload_only_keeps_locked_fields():
    payload = build_frame_override_payload(
        scene_id="scene-1",
        locked_fields=["shot_type", "world_elements"],
        values={
            "shot_type": "medium_shot",
            "world_elements": ["strategy board"],
            "prompt_intent": "should be ignored",
        },
        override_source="user_preview",
    )

    assert payload == {
        "scene_id": "scene-1",
        "locked_fields": ["shot_type", "world_elements"],
        "shot_type": "medium_shot",
        "world_elements": ["strategy board"],
        "override_source": "user_preview",
    }


def test_collect_storyboard_preview_overrides_skips_empty_entries():
    overrides = collect_storyboard_preview_overrides(
        [
            {
                "scene_id": "scene-1",
                "locked_fields": ["shot_type"],
                "values": {"shot_type": "medium_shot"},
            },
            {
                "scene_id": "scene-2",
                "locked_fields": [],
                "values": {"shot_type": "close_up"},
            },
        ]
    )

    assert overrides == [
        {
            "scene_id": "scene-1",
            "locked_fields": ["shot_type"],
            "shot_type": "medium_shot",
            "override_source": "user_preview",
        }
    ]


def test_history_page_source_mentions_planning_snapshot_fields():
    source = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "pages"
        / "2_📚_History.py"
    ).read_text(encoding="utf-8")

    assert "world_preset_id" in source
    assert "shot_preset_id" in source
    assert "resolved_content_mode" in source
    assert "selected_role_locking_strength" in source
