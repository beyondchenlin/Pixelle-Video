import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from web.state.storyboard_capture import (
    capture_snapshot_from_result,
    capture_snapshot_from_task_dir,
)
from web.state.storyboard_preview import STORYBOARD_PREVIEW_SNAPSHOT_KEY


@dataclass
class _FakeStoryboard:
    planning_snapshot: dict[str, Any] | None = None


@dataclass
class _FakeResult:
    storyboard: _FakeStoryboard | None = None
    video_path: str | None = None
    final_video_path: str | None = None


_PLANNING_SNAPSHOT: dict[str, Any] = {
    "storyboard_generation": {
        "plan_id": "plan_1",
        "revision": 1,
        "source_digest": "a" * 64,
        "frames": [{"frame_id": "frame_0001", "index": 1}],
    },
    "frames": [{"scene_id": "scene-1"}],
}


# ── capture_snapshot_from_result ──────────────────────────────────────


def test_capture_from_result_with_valid_storyboard_snapshot():
    session_state: dict[str, Any] = {}
    result = _FakeResult(
        storyboard=_FakeStoryboard(planning_snapshot=_PLANNING_SNAPSHOT),
    )
    changed = capture_snapshot_from_result(result, session_state)
    assert changed is True
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] == _PLANNING_SNAPSHOT


def test_capture_from_result_with_none_result():
    session_state: dict[str, Any] = {}
    changed = capture_snapshot_from_result(None, session_state)
    assert changed is False
    assert STORYBOARD_PREVIEW_SNAPSHOT_KEY not in session_state


def test_capture_from_result_with_no_storyboard():
    session_state: dict[str, Any] = {}
    result = _FakeResult(storyboard=None)
    changed = capture_snapshot_from_result(result, session_state)
    assert changed is False


def test_capture_from_result_with_none_planning_snapshot():
    session_state: dict[str, Any] = {}
    result = _FakeResult(storyboard=_FakeStoryboard(planning_snapshot=None))
    changed = capture_snapshot_from_result(result, session_state)
    assert changed is False


def test_capture_from_result_falls_back_to_task_dir_from_video_path():
    session_state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as task_dir:
        storyboard_path = os.path.join(task_dir, "storyboard.json")
        with open(storyboard_path, "w", encoding="utf-8") as fh:
            json.dump({"planning_snapshot": _PLANNING_SNAPSHOT}, fh)

        result = _FakeResult(video_path=os.path.join(task_dir, "output.mp4"))
        changed = capture_snapshot_from_result(result, session_state)

    assert changed is True
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] == _PLANNING_SNAPSHOT


def test_capture_from_result_falls_back_to_task_dir_from_final_video_path():
    session_state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as task_dir:
        storyboard_path = os.path.join(task_dir, "storyboard.json")
        with open(storyboard_path, "w", encoding="utf-8") as fh:
            json.dump({"planning_snapshot": _PLANNING_SNAPSHOT}, fh)

        result = _FakeResult(final_video_path=os.path.join(task_dir, "output.mp4"))
        changed = capture_snapshot_from_result(result, session_state)

    assert changed is True
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] == _PLANNING_SNAPSHOT


def test_capture_from_result_fallback_returns_false_when_no_storyboard_json():
    session_state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as task_dir:
        result = _FakeResult(video_path=os.path.join(task_dir, "output.mp4"))
        changed = capture_snapshot_from_result(result, session_state)

    assert changed is False


# ── capture_snapshot_from_task_dir ────────────────────────────────────


def test_capture_from_task_dir_with_valid_file():
    session_state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as task_dir:
        storyboard_path = os.path.join(task_dir, "storyboard.json")
        with open(storyboard_path, "w", encoding="utf-8") as fh:
            json.dump({"planning_snapshot": _PLANNING_SNAPSHOT}, fh)

        changed = capture_snapshot_from_task_dir(task_dir, session_state)

    assert changed is True
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] == _PLANNING_SNAPSHOT


def test_capture_from_task_dir_with_missing_file():
    session_state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as task_dir:
        changed = capture_snapshot_from_task_dir(task_dir, session_state)

    assert changed is False
    assert STORYBOARD_PREVIEW_SNAPSHOT_KEY not in session_state


def test_capture_from_task_dir_with_missing_planning_snapshot_key():
    session_state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as task_dir:
        storyboard_path = os.path.join(task_dir, "storyboard.json")
        with open(storyboard_path, "w", encoding="utf-8") as fh:
            json.dump({"other_key": "value"}, fh)

        changed = capture_snapshot_from_task_dir(task_dir, session_state)

    assert changed is False


def test_capture_from_task_dir_with_planning_snapshot_not_a_dict():
    session_state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as task_dir:
        storyboard_path = os.path.join(task_dir, "storyboard.json")
        with open(storyboard_path, "w", encoding="utf-8") as fh:
            json.dump({"planning_snapshot": "not_a_dict"}, fh)

        changed = capture_snapshot_from_task_dir(task_dir, session_state)

    assert changed is False


def test_capture_from_task_dir_with_invalid_json():
    session_state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as task_dir:
        storyboard_path = os.path.join(task_dir, "storyboard.json")
        with open(storyboard_path, "w", encoding="utf-8") as fh:
            fh.write("not valid json")

        changed = capture_snapshot_from_task_dir(task_dir, session_state)

    assert changed is False


def test_capture_from_task_dir_clears_previous_snapshot():
    old_snapshot = {"storyboard_generation": {"plan_id": "old"}}
    session_state: dict[str, Any] = {
        STORYBOARD_PREVIEW_SNAPSHOT_KEY: old_snapshot,
    }
    with tempfile.TemporaryDirectory() as task_dir:
        storyboard_path = os.path.join(task_dir, "storyboard.json")
        with open(storyboard_path, "w", encoding="utf-8") as fh:
            json.dump({"planning_snapshot": _PLANNING_SNAPSHOT}, fh)

        changed = capture_snapshot_from_task_dir(task_dir, session_state)

    assert changed is True
    assert session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] == _PLANNING_SNAPSHOT
