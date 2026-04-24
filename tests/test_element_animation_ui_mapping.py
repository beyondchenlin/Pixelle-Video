import pytest

from pixelle_video.config.schema import RenderConfig
from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.pipelines.storyboard_config import resolve_storyboard_render_kwargs
from pixelle_video.services.persistence import PersistenceService
from web.components.output_preview import (
    build_batch_shared_config,
    build_single_generation_request,
)

ELEMENT_ANIMATION_PARAMS = {
    "element_animation_enabled": True,
    "element_animation_backend": "python_ffmpeg",
    "element_animation_subject_count": 4,
    "element_animation_candidate_limit": 6,
    "element_animation_prompt": "animate the main product and title",
    "element_animation_intensity": "high",
    "element_animation_workflow": "custom_segment.json",
}


def test_build_single_generation_request_includes_element_animation_options():
    def _progress(_event):
        return None

    request = build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            **ELEMENT_ANIMATION_PARAMS,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    for key, value in ELEMENT_ANIMATION_PARAMS.items():
        assert request[key] == value


def test_build_batch_shared_config_includes_element_animation_options():
    shared_config = build_batch_shared_config(
        {
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            **ELEMENT_ANIMATION_PARAMS,
        }
    )

    for key, value in ELEMENT_ANIMATION_PARAMS.items():
        assert shared_config[key] == value


def test_build_single_generation_request_skips_none_element_animation_options():
    def _progress(_event):
        return None

    request = build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            "element_animation_enabled": False,
            "element_animation_backend": None,
            "element_animation_subject_count": None,
            "element_animation_candidate_limit": None,
            "element_animation_prompt": None,
            "element_animation_intensity": None,
            "element_animation_workflow": None,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["element_animation_enabled"] is False
    assert "element_animation_backend" not in request
    assert "element_animation_subject_count" not in request
    assert "element_animation_candidate_limit" not in request
    assert "element_animation_prompt" not in request
    assert "element_animation_intensity" not in request
    assert "element_animation_workflow" not in request


def test_build_batch_shared_config_skips_none_element_animation_options():
    shared_config = build_batch_shared_config(
        {
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            "element_animation_enabled": False,
            "element_animation_backend": None,
            "element_animation_subject_count": None,
            "element_animation_candidate_limit": None,
            "element_animation_prompt": None,
            "element_animation_intensity": None,
            "element_animation_workflow": None,
        }
    )

    assert shared_config["element_animation_enabled"] is False
    assert "element_animation_backend" not in shared_config
    assert "element_animation_subject_count" not in shared_config
    assert "element_animation_candidate_limit" not in shared_config
    assert "element_animation_prompt" not in shared_config
    assert "element_animation_intensity" not in shared_config
    assert "element_animation_workflow" not in shared_config


def test_resolve_storyboard_render_kwargs_copies_request_element_animation_options():
    kwargs = resolve_storyboard_render_kwargs(
        runtime_config={},
        request_params=ELEMENT_ANIMATION_PARAMS,
    )

    for key, value in ELEMENT_ANIMATION_PARAMS.items():
        assert kwargs[key] == value


def test_resolve_storyboard_render_kwargs_reads_configured_element_animation_defaults():
    kwargs = resolve_storyboard_render_kwargs(
        runtime_config={
            "render": {
                "element_animation": {
                    "enabled": True,
                    "backend": "python_ffmpeg",
                    "subject_count": 5,
                    "candidate_limit": 8,
                    "prompt": "configured motion",
                    "intensity": "low",
                    "workflow": "configured_segment.json",
                }
            }
        },
        request_params={},
    )

    assert kwargs["element_animation_enabled"] is True
    assert kwargs["element_animation_backend"] == "python_ffmpeg"
    assert kwargs["element_animation_subject_count"] == 5
    assert kwargs["element_animation_candidate_limit"] == 8
    assert kwargs["element_animation_prompt"] == "configured motion"
    assert kwargs["element_animation_intensity"] == "low"
    assert kwargs["element_animation_workflow"] == "configured_segment.json"


def test_storyboard_config_has_element_animation_defaults():
    config = StoryboardConfig(media_width=1080, media_height=1920)

    assert config.element_animation_enabled is False
    assert config.element_animation_backend == "hyperframes_canvas"
    assert config.element_animation_subject_count == 3
    assert config.element_animation_candidate_limit == 3
    assert config.element_animation_prompt is None
    assert config.element_animation_intensity == "medium"
    assert config.element_animation_workflow == "image_sam31_segment.json"


def test_storyboard_config_rejects_candidate_limit_below_subject_count():
    with pytest.raises(ValueError, match="candidate_limit"):
        StoryboardConfig(
            media_width=1080,
            media_height=1920,
            element_animation_subject_count=4,
            element_animation_candidate_limit=3,
        )


def test_render_config_has_element_animation_defaults():
    config = RenderConfig()

    assert config.element_animation.enabled is False
    assert config.element_animation.backend == "hyperframes_canvas"
    assert config.element_animation.subject_count == 3
    assert config.element_animation.candidate_limit == 3
    assert config.element_animation.prompt is None
    assert config.element_animation.intensity == "medium"
    assert config.element_animation.workflow == "image_sam31_segment.json"


def test_render_config_rejects_candidate_limit_below_subject_count():
    with pytest.raises(ValueError, match="candidate_limit"):
        RenderConfig.model_validate(
            {
                "element_animation": {
                    "subject_count": 4,
                    "candidate_limit": 3,
                }
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("backend", "unsupported_backend"),
        ("intensity", "extreme"),
    ],
)
def test_render_config_rejects_invalid_element_animation_values(field, value):
    with pytest.raises(ValueError, match=field):
        RenderConfig.model_validate({"element_animation": {field: value}})


def test_persistence_service_round_trips_element_animation_config(tmp_path):
    service = PersistenceService(output_dir=str(tmp_path))
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        element_animation_enabled=True,
        element_animation_backend="python_ffmpeg",
        element_animation_subject_count=4,
        element_animation_candidate_limit=7,
        element_animation_prompt="persisted motion prompt",
        element_animation_intensity="high",
        element_animation_workflow="persisted_segment.json",
    )

    restored = service._dict_to_config(service._config_to_dict(config))

    assert restored.element_animation_enabled is True
    assert restored.element_animation_backend == "python_ffmpeg"
    assert restored.element_animation_subject_count == 4
    assert restored.element_animation_candidate_limit == 7
    assert restored.element_animation_prompt == "persisted motion prompt"
    assert restored.element_animation_intensity == "high"
    assert restored.element_animation_workflow == "persisted_segment.json"
