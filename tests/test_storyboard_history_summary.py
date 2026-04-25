from types import SimpleNamespace

from web.utils.storyboard_history import resolve_history_storyboard_scene_count


def test_history_scene_count_uses_storyboard_generation_snapshot_for_new_tasks():
    detail = {
        "metadata": {"input": {"storyboard_scene_count": 9, "n_scenes": 5}},
        "storyboard": SimpleNamespace(
            planning_snapshot={
                "storyboard_generation": {
                    "resolved_scene_count": 3,
                }
            }
        ),
    }

    assert resolve_history_storyboard_scene_count(detail) == 3


def test_history_scene_count_falls_back_to_legacy_n_scenes_for_old_tasks():
    detail = {
        "metadata": {"input": {"n_scenes": 5}},
        "storyboard": SimpleNamespace(planning_snapshot=None),
    }

    assert resolve_history_storyboard_scene_count(detail) == 5
