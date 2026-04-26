import importlib.util
import sys
from pathlib import Path

from pixelle_video.config import config_manager
from web.components.storyboard_preview import (
    build_frame_override_payload,
    build_storyboard_preview_rows,
    build_storyboard_preview_state_namespace,
    collect_storyboard_preview_overrides,
)
from web.i18n import tr


def load_history_page():
    pages_dir = Path(__file__).resolve().parents[1] / "web" / "pages"
    history_pages = sorted(pages_dir.glob("*_History.py"))
    assert len(history_pages) == 1
    module_path = history_pages[0]
    spec = importlib.util.spec_from_file_location("history_page_test_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["web.pages.history_page_test_module"] = module
    return module


HISTORY_PAGE = load_history_page()


def expected_preset_label(item):
    translation_key = item.get("display_name_key") or item.get("translation_key")
    if translation_key:
        localized_label = tr(translation_key)
        if localized_label != translation_key:
            return localized_label
    return item.get("display_name") or item.get("preset_id") or ""


def test_build_frame_override_payload_only_keeps_locked_fields():
    payload = build_frame_override_payload(
        plan_id="plan_abc",
        plan_revision=2,
        frame_id="frame_0001",
        source_digest="a" * 64,
        locked_fields=["shot_type", "world_elements"],
        values={
            "shot_type": "medium_shot",
            "world_elements": ["strategy board"],
            "prompt_intent": "should be ignored",
        },
        override_source="user_preview",
    )

    assert payload == {
        "plan_id": "plan_abc",
        "plan_revision": 2,
        "frame_id": "frame_0001",
        "source_digest": "a" * 64,
        "locked_fields": ["shot_type", "world_elements"],
        "shot_type": "medium_shot",
        "world_elements": ["strategy board"],
        "override_source": "user_preview",
    }


def test_collect_storyboard_preview_overrides_skips_empty_entries():
    planning_snapshot = {
        "storyboard_generation": {
            "plan_id": "plan_abc",
            "revision": 2,
            "source_digest": "b" * 64,
            "frames": [
                {
                    "frame_id": "frame_0001",
                    "index": 1,
                    "shot_type": "medium_shot",
                    "shot_purpose": "context",
                    "primary_subject": "coach",
                    "world_elements": ["strategy board"],
                    "continuity_anchors": ["desk"],
                    "focus_detail": "marker notes",
                    "prompt_intent": "teach concept A",
                }
            ],
        },
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
    rows = build_storyboard_preview_rows(planning_snapshot)
    overrides = collect_storyboard_preview_overrides(
        [
            {
                **rows[0],
                "locked_fields": ["shot_type"],
                "values": {"shot_type": "medium_shot"},
            },
            {
                **rows[0],
                "frame_id": "frame_0002",
                "locked_fields": [],
                "values": {"shot_type": "close_up"},
            },
        ],
    )

    assert overrides == [
        {
            "plan_id": "plan_abc",
            "plan_revision": 2,
            "frame_id": "frame_0001",
            "source_digest": "b" * 64,
            "locked_fields": ["shot_type"],
            "shot_type": "medium_shot",
            "override_source": "user_preview",
        }
    ]


def test_storyboard_preview_rows_require_plan_identity():
    planning_snapshot = {
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

    assert build_storyboard_preview_rows(planning_snapshot) == []


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


def test_history_storyboard_summary_localizes_preset_labels():
    snapshot = {
        "world_preset_id": "neutral_knowledge_storyboard",
        "requested_shot_preset_id": "balanced_explainer",
    }

    summary = dict(HISTORY_PAGE.summarize_storyboard_planning_snapshot(snapshot))
    world_library = config_manager.get_storyboard_world_preset_library()
    shot_library = config_manager.get_storyboard_shot_preset_library()

    world_item = next(
        item for item in world_library["items"] if item["preset_id"] == "neutral_knowledge_storyboard"
    )
    shot_item = next(
        item for item in shot_library["items"] if item["preset_id"] == "balanced_explainer"
    )

    assert summary["history.detail.storyboard_world_preset"] == expected_preset_label(world_item)
    assert summary["history.detail.storyboard_shot_preset"] == expected_preset_label(shot_item)


def test_history_storyboard_summary_prefers_effective_shot_label_over_stale_request():
    shot_library = config_manager.get_storyboard_shot_preset_library()
    effective_item = next(
        item for item in shot_library["items"] if item["preset_id"] == "balanced_explainer"
    )

    snapshot = {
        "requested_shot_preset_id": "stale_requested_shot",
        "effective_final_shot_preset": "balanced_explainer",
    }

    summary = dict(HISTORY_PAGE.summarize_storyboard_planning_snapshot(snapshot))

    assert summary["history.detail.storyboard_shot_preset"] == expected_preset_label(
        effective_item
    )
    assert summary["history.detail.storyboard_shot_preset"] != "stale_requested_shot"


def test_history_storyboard_summary_prefers_persisted_preset_payloads(monkeypatch):
    monkeypatch.setattr(
        HISTORY_PAGE.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "items": [
                {
                    "preset_id": "neutral_knowledge_storyboard",
                    "display_name": "Library World Label",
                }
            ]
        },
    )
    monkeypatch.setattr(
        HISTORY_PAGE.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "items": [
                {
                    "preset_id": "balanced_explainer",
                    "display_name": "Library Shot Label",
                }
            ]
        },
    )

    snapshot = {
        "world_preset_id": "neutral_knowledge_storyboard",
        "world_preset": {
            "preset_id": "neutral_knowledge_storyboard",
            "display_name": "Persisted World Label",
        },
        "requested_shot_preset_id": "balanced_explainer",
        "effective_final_shot_preset": "balanced_explainer",
        "shot_preset_id": "balanced_explainer",
        "shot_preset": {
            "preset_id": "balanced_explainer",
            "display_name": "Persisted Shot Label",
        },
    }

    summary = dict(HISTORY_PAGE.summarize_storyboard_planning_snapshot(snapshot))

    assert summary["history.detail.storyboard_world_preset"] == "Persisted World Label"
    assert summary["history.detail.storyboard_shot_preset"] == "Persisted Shot Label"
    assert summary["history.detail.storyboard_world_preset"] != "Library World Label"
    assert summary["history.detail.storyboard_shot_preset"] != "Library Shot Label"


def test_history_storyboard_summary_localizes_remaining_enum_values():
    snapshot = {
        "content_mode": "theme_mapping",
        "consistency_strength": "standard",
        "role_strategy": "theme_mapping",
        "shot_strategy": "adaptive",
    }

    summary = dict(HISTORY_PAGE.summarize_storyboard_planning_snapshot(snapshot))

    assert summary["history.detail.storyboard_content_mode"] == tr(
        "storyboard.option.content_mode.theme_mapping"
    )
    assert summary["history.detail.storyboard_consistency"] == tr(
        "storyboard.option.consistency.standard"
    )
    assert summary["history.detail.storyboard_role_strategy"] == tr(
        "storyboard.option.role_strategy.theme_mapping"
    )
    assert summary["history.detail.storyboard_shot_strategy"] == tr(
        "storyboard.option.shot_strategy.adaptive"
    )
