import json
from pathlib import Path

import yaml

from pixelle_video.config.schema import RenderConfig
from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.pipelines.storyboard_config import resolve_storyboard_render_kwargs
from pixelle_video.render_backend import DEFAULT_RENDER_BACKEND

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_render_backend_defaults_share_one_runtime_contract():
    assert DEFAULT_RENDER_BACKEND == "ffmpeg_manifest"
    assert RenderConfig().backend == DEFAULT_RENDER_BACKEND
    assert (
        StoryboardConfig(media_width=1280, media_height=720).render_backend
        == DEFAULT_RENDER_BACKEND
    )


def test_example_config_matches_runtime_render_backend_default():
    example_config = yaml.safe_load(
        (REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8")
    )

    assert example_config["render"]["backend"] == DEFAULT_RENDER_BACKEND


def test_omitted_runtime_and_request_backend_resolve_to_the_shared_default():
    assert (
        resolve_storyboard_render_kwargs({}, {})["render_backend"]
        == DEFAULT_RENDER_BACKEND
    )


def test_explicit_runtime_and_request_backends_keep_precedence():
    assert (
        resolve_storyboard_render_kwargs(
            {"render": {"backend": "hyperframes_compiled"}},
            {},
        )["render_backend"]
        == "hyperframes_compiled"
    )
    assert (
        resolve_storyboard_render_kwargs(
            {"render": {"backend": "hyperframes_compiled"}},
            {"render_backend": "ffmpeg_manifest"},
        )["render_backend"]
        == "ffmpeg_manifest"
    )


def test_default_backend_is_not_described_as_experimental_in_the_ui():
    captions = []
    for locale in ("en_US", "zh_CN"):
        payload = json.loads(
            (REPO_ROOT / "web" / "i18n" / "locales" / f"{locale}.json").read_text(
                encoding="utf-8"
            )
        )
        captions.append(payload["t"][f"render_backend.caption.{DEFAULT_RENDER_BACKEND}"])

    assert "experimental" not in captions[0].lower()
    assert "实验" not in captions[1]


def test_default_backend_changes_trigger_the_render_golden_gate():
    workflow = (REPO_ROOT / ".github" / "workflows" / "render-golden-ci.yml").read_text(
        encoding="utf-8"
    )

    for guarded_path in (
        "config.example.yaml",
        "pixelle_video/render_backend.py",
        "tests/test_render_backend_defaults.py",
        "tests/test_render_backend_ui.py",
        "web/i18n/locales/en_US.json",
        "web/i18n/locales/zh_CN.json",
    ):
        assert workflow.count(f'- "{guarded_path}"') == 2

    workflow_lines = [line.strip() for line in workflow.splitlines()]
    assert any(
        line.startswith("tests/test_render_backend_defaults.py")
        for line in workflow_lines
    )
    assert any(
        line.startswith("tests/test_render_backend_ui.py") for line in workflow_lines
    )
