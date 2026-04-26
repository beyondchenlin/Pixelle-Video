from pixelle_video.models.storyboard_limits import (
    DEFAULT_STORYBOARD_GENERATION_LIMITS,
    StoryboardGenerationLimits,
    current_storyboard_generation_limits,
    storyboard_generation_limits_from_config,
)
from pixelle_video.models.video_generation_contract import STORYBOARD_GENERATION_LIMITS
from pixelle_video.services.storyboard_generation import StoryboardGenerationService
import web.components.content_input as content_input
from pixelle_video.config import config_manager


def test_storyboard_generation_limits_keep_default_product_constant_for_schema():
    assert STORYBOARD_GENERATION_LIMITS == DEFAULT_STORYBOARD_GENERATION_LIMITS


def test_storyboard_generation_limits_normalize_config_values():
    limits = storyboard_generation_limits_from_config(
        {"min_scene_count": 2, "max_scene_count": 8}
    )

    assert limits == StoryboardGenerationLimits(min_scene_count=2, max_scene_count=8)


def test_storyboard_generation_service_uses_central_default_limits():
    service = StoryboardGenerationService()

    assert service.limits == DEFAULT_STORYBOARD_GENERATION_LIMITS


def test_current_storyboard_generation_limits_reads_config_manager(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        type("Config", (), {"storyboard": {"min_scene_count": 2, "max_scene_count": 8}})(),
    )

    assert current_storyboard_generation_limits() == StoryboardGenerationLimits(
        min_scene_count=2,
        max_scene_count=8,
    )


def test_content_input_reads_current_storyboard_generation_limits(monkeypatch):
    monkeypatch.setattr(
        content_input,
        "current_storyboard_generation_limits",
        lambda: StoryboardGenerationLimits(min_scene_count=2, max_scene_count=8),
    )

    assert content_input.get_storyboard_generation_limits() == StoryboardGenerationLimits(
        min_scene_count=2,
        max_scene_count=8,
    )
