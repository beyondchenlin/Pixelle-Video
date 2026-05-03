import importlib.util
import sys
from pathlib import Path
from typing import Any


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeUI:
    def __init__(self):
        self.session_state: dict[str, Any] = {}
        self.markdowns: list[dict[str, Any]] = []
        self.captions: list[str] = []
        self.infos: list[str] = []

    def container(self, **_kwargs):
        return _NoopContext()

    def markdown(self, message, **kwargs):
        self.markdowns.append({"message": message, **kwargs})

    def caption(self, message):
        self.captions.append(message)

    def info(self, message):
        self.infos.append(message)


def _load_workbench_page():
    pages_dir = Path(__file__).resolve().parents[1] / "web" / "pages"
    module_path = pages_dir / "3_🧭_Storyboard_Workbench.py"
    spec = importlib.util.spec_from_file_location("storyboard_workbench_page_test_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["storyboard_workbench_page_test_module"] = module
    return module


def _planning_snapshot() -> dict[str, Any]:
    return {
        "storyboard_generation": {
            "plan_id": "prompt_plan_1",
            "revision": 2,
            "source_digest": "a" * 64,
            "frames": [
                {
                    "frame_id": "frame_0001",
                    "index": 1,
                    "shot_type": "medium_shot",
                    "shot_purpose": "context",
                    "primary_subject": "coach",
                    "world_elements": ["board"],
                    "continuity_anchors": ["desk"],
                    "focus_detail": "marker notes",
                    "prompt_intent": "teach concept A",
                    "locked_fields": ["shot_type"],
                }
            ],
        },
        "frames": [
            {
                "scene_id": "scene-1",
                "shot_type": "medium_shot",
                "shot_purpose": "context",
                "primary_subject": "coach",
                "world_elements": ["board"],
                "continuity_anchors": ["desk"],
                "focus_detail": "marker notes",
                "prompt_intent": "teach concept A",
            }
        ],
    }


def test_storyboard_workbench_page_renders_preview_overrides_in_main_area(monkeypatch):
    page = _load_workbench_page()
    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "storyboard_preview_snapshot": _planning_snapshot(),
            "api_base_url": "http://localhost:8000/api",
            "project_id": "project_1",
            "workspace_id": "workspace_1",
        }
    )
    calls: list[dict[str, Any]] = []

    def preview_renderer(snapshot, *, stale_context=None):
        calls.append({"snapshot": snapshot, "stale_context": stale_context})
        return []

    page.render_storyboard_workbench_page(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        preview_renderer=preview_renderer,
    )

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
        + fake_ui.infos
    )
    assert "storyboard.workbench.page_title" in rendered
    assert "storyboard.workbench.page_caption" in rendered
    assert calls == [
        {
            "snapshot": _planning_snapshot(),
            "stale_context": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "workspace_1",
            },
        }
    ]


def test_storyboard_workbench_page_shows_empty_state_without_snapshot(monkeypatch):
    page = _load_workbench_page()
    fake_ui = _FakeUI()

    def fail_preview(**_kwargs):
        raise AssertionError("preview renderer must not run without a snapshot")

    page.render_storyboard_workbench_page(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        preview_renderer=fail_preview,
    )

    assert fake_ui.infos == ["storyboard.workbench.empty_state"]
