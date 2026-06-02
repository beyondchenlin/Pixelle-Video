from types import MappingProxyType

from web.state.storyboard_preview import (
    STORYBOARD_PREVIEW_SNAPSHOT_KEY,
    get_storyboard_preview_snapshot,
    set_storyboard_preview_snapshot,
)


def test_set_storyboard_preview_snapshot_updates_state_and_reports_change():
    session_state = {}

    changed = set_storyboard_preview_snapshot(
        session_state,
        {"storyboard_generation": {"plan_id": "plan_1"}},
    )

    assert changed is True
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] == {
        "storyboard_generation": {"plan_id": "plan_1"}
    }


def test_set_storyboard_preview_snapshot_detaches_mappingproxy_values():
    session_state = {}

    changed = set_storyboard_preview_snapshot(
        session_state,
        {
            "visual_role_projected_prompt_parts_by_frame": {
                "frame_0001": MappingProxyType({"projector_validation_passed": True})
            }
        },
    )

    assert changed is True
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] == {
        "visual_role_projected_prompt_parts_by_frame": {
            "frame_0001": {"projector_validation_passed": True}
        }
    }


def test_set_storyboard_preview_snapshot_skips_equal_snapshot():
    session_state = {
        STORYBOARD_PREVIEW_SNAPSHOT_KEY: {
            "storyboard_generation": {"plan_id": "plan_1"}
        }
    }

    changed = set_storyboard_preview_snapshot(
        session_state,
        {"storyboard_generation": {"plan_id": "plan_1"}},
    )

    assert changed is False
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] == {
        "storyboard_generation": {"plan_id": "plan_1"}
    }


def test_set_storyboard_preview_snapshot_clears_existing_snapshot():
    session_state = {
        STORYBOARD_PREVIEW_SNAPSHOT_KEY: {
            "storyboard_generation": {"plan_id": "plan_1"}
        }
    }

    changed = set_storyboard_preview_snapshot(session_state, None)

    assert changed is True
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] is None


def test_get_storyboard_preview_snapshot_normalizes_non_mapping_values_to_none():
    session_state = {STORYBOARD_PREVIEW_SNAPSHOT_KEY: "invalid"}

    assert get_storyboard_preview_snapshot(session_state) is None


def test_build_demo_planning_snapshot_satisfies_data_contract():
    from web.components.storyboard_preview import build_storyboard_preview_rows
    from web.state.storyboard_demo_snapshot import build_demo_planning_snapshot

    demo = build_demo_planning_snapshot()
    rows = build_storyboard_preview_rows(demo)
    assert len(rows) == 3
    first = rows[0]
    assert first["plan_id"].startswith("demo_plan_")
    assert first["plan_revision"] == 1
    assert len(first["source_digest"]) == 64
    assert first["frame_id"].startswith("demo_frame_")
    assert first["values"]["shot_type"] != ""


def test_build_demo_planning_snapshot_is_idempotent():
    import json

    from web.state.storyboard_demo_snapshot import build_demo_planning_snapshot

    d1 = json.dumps(build_demo_planning_snapshot(), sort_keys=True)
    d2 = json.dumps(build_demo_planning_snapshot(), sort_keys=True)
    assert d1 == d2
