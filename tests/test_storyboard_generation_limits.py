from pixelle_video.models.storyboard_limits import (
    DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_DEFAULT,
    DEFAULT_STORYBOARD_GENERATION_LIMITS,
    StoryboardGenerationLimits,
    current_storyboard_generation_limits,
    storyboard_generation_limits_from_config,
)
from pixelle_video.models.video_generation_contract import (
    STORYBOARD_GENERATION_LIMITS,
    StoryboardControlsContract,
)
from pixelle_video.services.storyboard_generation import StoryboardGenerationService
import web.components.content_input as content_input
from pixelle_video.config import config_manager


def test_storyboard_generation_limits_keep_default_product_constant_for_schema():
    assert STORYBOARD_GENERATION_LIMITS == DEFAULT_STORYBOARD_GENERATION_LIMITS


def test_storyboard_generation_limits_normalize_config_values():
    limits = storyboard_generation_limits_from_config(
        {
            "min_scene_count": 2,
            "max_scene_count": 8,
            "deterministic_max_scene_count_limit": 80,
        }
    )

    assert limits == StoryboardGenerationLimits(
        min_scene_count=2,
        max_scene_count=8,
        deterministic_max_scene_count_limit=80,
    )


def test_storyboard_generation_service_uses_central_default_limits():
    service = StoryboardGenerationService()

    assert service.limits == DEFAULT_STORYBOARD_GENERATION_LIMITS


def test_current_storyboard_generation_limits_reads_config_manager(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        type(
            "Config",
            (),
            {
                "storyboard": {
                    "min_scene_count": 2,
                    "max_scene_count": 8,
                    "deterministic_max_scene_count_limit": 90,
                }
            },
        )(),
    )

    assert current_storyboard_generation_limits() == StoryboardGenerationLimits(
        min_scene_count=2,
        max_scene_count=8,
        deterministic_max_scene_count_limit=90,
    )


def test_content_input_reads_current_storyboard_generation_limits(monkeypatch):
    monkeypatch.setattr(
        content_input,
        "current_storyboard_generation_limits",
        lambda: StoryboardGenerationLimits(
            min_scene_count=2,
            max_scene_count=8,
            deterministic_max_scene_count_limit=80,
        ),
    )

    assert content_input.get_storyboard_generation_limits() == StoryboardGenerationLimits(
        min_scene_count=2,
        max_scene_count=8,
        deterministic_max_scene_count_limit=80,
    )


def test_storyboard_generation_limits_default_deterministic_scene_cap_matches_product_default():
    assert (
        DEFAULT_STORYBOARD_GENERATION_LIMITS.default_deterministic_max_scene_count
        == DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_DEFAULT
    )


def test_storyboard_controls_contract_does_not_inject_deterministic_ui_default():
    contract = StoryboardControlsContract.from_mapping(
        {
            "storyboard_mode": "sentence",
            "storyboard_count_mode": "auto",
        }
    )

    assert contract.storyboard_scene_count is None
    assert contract.storyboard_max_scene_count is None
