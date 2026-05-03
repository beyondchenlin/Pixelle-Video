from web.state.storyboard_overrides import (
    STORYBOARD_OVERRIDE_DRAFT_KEY,
    build_storyboard_override_snapshot_identity,
    get_storyboard_override_draft,
    get_storyboard_override_values_for_snapshot,
    set_storyboard_override_draft,
)


def test_set_storyboard_override_draft_updates_state_and_reports_change():
    session_state = {}
    draft = {
        "snapshot_identity": "storyboard_snapshot_abc",
        "frame_overrides": [
            {
                "plan_id": "plan_1",
                "plan_revision": 2,
                "frame_id": "frame_0001",
                "source_digest": "a" * 64,
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    }

    changed = set_storyboard_override_draft(session_state, draft)

    assert changed is True
    assert session_state[STORYBOARD_OVERRIDE_DRAFT_KEY] == draft


def test_set_storyboard_override_draft_clears_existing_draft():
    session_state = {
        STORYBOARD_OVERRIDE_DRAFT_KEY: {
            "snapshot_identity": "storyboard_snapshot_abc",
            "frame_overrides": [],
        }
    }

    changed = set_storyboard_override_draft(session_state, None)

    assert changed is True
    assert session_state[STORYBOARD_OVERRIDE_DRAFT_KEY] is None


def test_storyboard_override_snapshot_identity_changes_with_display_frames():
    first_identity = build_storyboard_override_snapshot_identity(
        {"frames": [{"scene_id": "scene-1", "shot_type": "medium_shot"}]}
    )
    second_identity = build_storyboard_override_snapshot_identity(
        {"frames": [{"scene_id": "scene-1", "shot_type": "close_up"}]}
    )

    assert first_identity.startswith("storyboard_snapshot_")
    assert second_identity.startswith("storyboard_snapshot_")
    assert first_identity != second_identity


def test_get_storyboard_override_values_for_snapshot_only_returns_matching_identity():
    session_state = {
        STORYBOARD_OVERRIDE_DRAFT_KEY: {
            "snapshot_identity": "storyboard_snapshot_abc",
            "frame_overrides": [
                {
                    "plan_id": "plan_1",
                    "plan_revision": 2,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        }
    }

    assert get_storyboard_override_values_for_snapshot(
        session_state,
        snapshot_identity="storyboard_snapshot_abc",
    ) == [
        {
            "plan_id": "plan_1",
            "plan_revision": 2,
            "frame_id": "frame_0001",
            "source_digest": "a" * 64,
            "locked_fields": ["shot_type"],
            "shot_type": "medium_shot",
        }
    ]
    assert get_storyboard_override_values_for_snapshot(
        session_state,
        snapshot_identity="storyboard_snapshot_other",
    ) == []


def test_get_storyboard_override_draft_normalizes_invalid_state_to_none():
    session_state = {STORYBOARD_OVERRIDE_DRAFT_KEY: "invalid"}

    assert get_storyboard_override_draft(session_state) is None
