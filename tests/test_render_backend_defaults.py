from pathlib import Path

import yaml

from pixelle_video.config.schema import RenderConfig
from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.render_backend import DEFAULT_RENDER_BACKEND

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_render_backend_defaults_share_one_runtime_contract():
    assert DEFAULT_RENDER_BACKEND == "hyperframes_compiled"
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
