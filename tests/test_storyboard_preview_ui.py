from pathlib import Path

from web.components.storyboard_preview import (
    build_frame_override_payload,
    build_storyboard_preview_snapshot_identity,
    build_storyboard_preview_state_namespace,
    collect_storyboard_preview_overrides,
)


def test_build_frame_override_payload_only_keeps_locked_fields():
    payload = build_frame_override_payload(
        scene_id="scene-1",
        snapshot_identity="snapshot:scene-1",
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
        "snapshot_identity": "snapshot:scene-1",
        "locked_fields": ["shot_type", "world_elements"],
        "shot_type": "medium_shot",
        "world_elements": ["strategy board"],
        "override_source": "user_preview",
    }


def test_collect_storyboard_preview_overrides_skips_empty_entries():
    snapshot = {
        "frames": [
            {
                "scene_id": "scene-1",
                "shot_type": "medium_shot",
                "shot_purpose": "context",
                "primary_subject": "coach",
                "world_elements": ["strategy board"],
                "continuity_anchors": ["desk"],
                "focus_detail": "marker notes",
                "prompt_intent": "teach concept A",
            }
        ]
    }
    snapshot_identity = build_storyboard_preview_snapshot_identity(snapshot)
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
        ],
        snapshot_identity=snapshot_identity,
    )

    assert overrides == [
        {
            "scene_id": "scene-1",
            "snapshot_identity": snapshot_identity,
            "locked_fields": ["shot_type"],
            "shot_type": "medium_shot",
            "override_source": "user_preview",
        }
    ]


def test_storyboard_preview_snapshot_identity_hashes_snapshot_frames():
    snapshot = {
        "frames": [
            {
                "scene_id": "scene-1",
                "shot_type": "medium_shot",
                "shot_purpose": "context",
                "primary_subject": "coach",
                "world_elements": ["strategy board"],
                "continuity_anchors": ["desk"],
                "focus_detail": "marker notes",
                "prompt_intent": "teach concept A",
            }
        ]
    }

    identity = build_storyboard_preview_snapshot_identity(snapshot)
    payload = build_frame_override_payload(
        scene_id="scene-1",
        snapshot_identity=identity,
        locked_fields=["shot_type"],
        values={"shot_type": "close_up"},
    )

    assert payload is not None
    assert payload["snapshot_identity"] == identity


def test_storyboard_preview_state_namespace_changes_with_snapshot_content():
    first_snapshot = {
        "frames": [
            {
                "scene_id": "scene-1",
                "shot_type": "medium_shot",
                "prompt_intent": "teach concept A",
            }
        ]
    }
    second_snapshot = {
        "frames": [
            {
                "scene_id": "scene-1",
                "shot_type": "close_up",
                "prompt_intent": "teach concept B",
            }
        ]
    }

    first_namespace = build_storyboard_preview_state_namespace(first_snapshot)
    second_namespace = build_storyboard_preview_state_namespace(second_snapshot)

    assert first_namespace.startswith("storyboard_preview_")
    assert second_namespace.startswith("storyboard_preview_")
    assert first_namespace != second_namespace


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
