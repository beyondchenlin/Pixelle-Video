import asyncio
from pathlib import Path
from types import SimpleNamespace

from pixelle_video.models.progress import ProgressI18nMessage
from web.components import output_preview
from web.components.prompt_generation_performance import (
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
    LLM_PROMPT_BATCH_SIZE_PARAM,
)
from web.utils import batch_manager as batch_manager_module
from web.utils.streamlit_helpers import RefreshableSlot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_refreshable_slot_uses_stable_initial_suffix_and_refresh_suffix():
    captured = {"emptied": 0, "entered": 0, "suffixes": []}

    class _FakeContainer:
        def __enter__(self):
            captured["entered"] += 1
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeSlot:
        def empty(self):
            captured["emptied"] += 1

        def container(self):
            return _FakeContainer()

    slot = RefreshableSlot(_FakeSlot())

    assert slot.render(lambda suffix: captured["suffixes"].append(suffix)) is None
    assert slot.render(lambda suffix: captured["suffixes"].append(suffix), refresh=True) is None

    assert captured == {
        "emptied": 1,
        "entered": 2,
        "suffixes": ["", "_refresh_2"],
    }


def test_build_video_preview_css_overrides_streamlit_inline_width():
    css = output_preview.build_video_preview_css("output_preview_media", width="50%")

    assert ".st-key-output_preview_media [data-testid=\"stVideo\"]" in css
    assert "width: 50% !important;" in css
    assert "max-width: 100% !important;" in css
    assert "margin-inline: auto;" in css
    assert "display: block;" in css


def test_localize_progress_extra_info_supports_structured_i18n_message(monkeypatch):
    monkeypatch.setattr(
        output_preview,
        "tr",
        lambda key, fallback=None, **kwargs: (
            f"批次 {kwargs.get('current')}/{kwargs.get('total')} 已完成"
            if key == "progress.batch_completed"
            else (fallback or key)
        ),
    )

    message = output_preview._localize_progress_extra_info(
        ProgressI18nMessage(
            key="progress.batch_completed",
            params={"current": 2, "total": 3},
            fallback="Batch 2/3 completed",
        )
    )

    assert message == "批次 2/3 已完成"


def test_render_scaled_video_preview_uses_scoped_container(monkeypatch):
    captured = {}

    class _FakeContainer:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit:
        def markdown(self, body, *, unsafe_allow_html):
            captured["markdown"] = (body, unsafe_allow_html)

        def container(self, *, key):
            captured["container_key"] = key
            return _FakeContainer()

        def video(self, path, *, width):
            captured["video"] = (path, width)

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())

    output_preview.render_scaled_video_preview("final.mp4")

    css, unsafe = captured["markdown"]
    assert unsafe is True
    assert ".st-key-output_video_preview [data-testid=\"stVideo\"]" in css
    assert captured["container_key"] == "output_video_preview"
    assert captured["video"] == ("final.mp4", "stretch")


def test_video_generation_pipelines_use_shared_scaled_preview_renderer():
    files = [
        PROJECT_ROOT / "web" / "components" / "output_preview.py",
        PROJECT_ROOT / "web" / "pipelines" / "asset_based.py",
        PROJECT_ROOT / "web" / "pipelines" / "i2v.py",
        PROJECT_ROOT / "web" / "pipelines" / "digital_human.py",
        PROJECT_ROOT / "web" / "pipelines" / "action_transfer.py",
    ]

    for path in files:
        source = path.read_text(encoding="utf-8")
        assert "render_scaled_video_preview(" in source, f"{path.name} should use shared preview renderer"


def test_single_video_result_summary_uses_canvas_contract_dimensions():
    result = SimpleNamespace(
        video_path="final.mp4",
        file_size=1024 * 1024,
        storyboard=SimpleNamespace(
            config=SimpleNamespace(
                frame_template="1080x1920/image_default.html",
                canvas_width=1280,
                canvas_height=720,
            ),
            frames=[object(), object()],
        ),
    )

    summary = output_preview._build_single_video_result_summary(
        result,
        total_generation_time=12.5,
    )

    assert (summary["video_width"], summary["video_height"]) == (1280, 720)


def test_build_single_generation_request_includes_render_backend():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "bgm_path": None,
            "bgm_volume": 0.3,
            "tts_inference_mode": "local",
            "tts_voice": "zh-CN-YunjianNeural",
            "tts_speed": 1.2,
            "tts_audio_strategy": "master_track",
            "template_params": {"accent_color": "#fff"},
            "render_backend": "hyperframes_compiled",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["render_backend"] == "hyperframes_compiled"
    assert request["tts_audio_strategy"] == "master_track"
    assert request["progress_callback"] is _progress


def test_build_single_generation_request_uses_size_contract_not_template_session():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 768,
            "media_height": 768,
            "video_orientation": "landscape",
            "video_resolution_preset": "1k",
            "media_orientation": "square",
            "media_resolution_preset": "768",
            "sync_media_size_to_canvas": False,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["canvas_width"] == 1280
    assert request["canvas_height"] == 720
    assert request["media_width"] == 768
    assert request["media_height"] == 768
    assert request["video_orientation"] == "landscape"
    assert request["video_resolution_preset"] == "1k"
    assert request["media_orientation"] == "square"
    assert request["media_resolution_preset"] == "768"
    assert request["sync_media_size_to_canvas"] is False


def test_build_single_generation_request_syncs_media_size_to_canvas():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "video_orientation": "portrait",
            "video_resolution_preset": "2k",
            "media_orientation": "landscape",
            "media_resolution_preset": "1k",
            "sync_media_size_to_canvas": True,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert (request["canvas_width"], request["canvas_height"]) == (1080, 1920)
    assert (request["media_width"], request["media_height"]) == (1080, 1920)
    assert request["media_orientation"] == "landscape"
    assert request["media_resolution_preset"] == "1k"


def test_build_single_generation_request_defaults_to_comfyui_tts_mode():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {"text": "demo", "mode": "generate"},
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["tts_inference_mode"] == "comfyui"
    assert "tts_voice" not in request


def test_build_batch_shared_config_defaults_to_comfyui_tts_mode():
    shared_config = output_preview.build_batch_shared_config({"title_prefix": "Series"})

    assert shared_config["tts_inference_mode"] == "comfyui"
    assert "tts_voice" not in shared_config


def test_build_single_generation_request_uses_storyboard_generation_contract_fields():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 4,
            "script_length_mode": "custom",
            "script_target_words": 180,
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["storyboard_mode"] == "smart"
    assert request["storyboard_count_mode"] == "manual"
    assert request["storyboard_scene_count"] == 4
    assert request["script_length_mode"] == "custom"
    assert request["script_target_words"] == 180
    assert "n_scenes" not in request
    assert "split_mode" not in request


def test_build_single_generation_request_includes_punctuation_max_scene_count():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "storyboard_mode": "punctuation",
            "storyboard_count_mode": "auto",
            "storyboard_max_scene_count": 90,
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["storyboard_mode"] == "punctuation"
    assert request["storyboard_max_scene_count"] == 90


def test_storyboard_generation_option_keys_include_prompt_language():
    assert "storyboard_prompt_language" in output_preview.STORYBOARD_GENERATION_OPTION_KEYS
    assert "storyboard_max_scene_count" in output_preview.STORYBOARD_GENERATION_OPTION_KEYS


def test_build_single_generation_request_passes_request_and_session_ids():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            "request_id": "req_1234",
            "session_id": "sess_5678",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["request_id"] == "req_1234"
    assert request["session_id"] == "sess_5678"


def test_build_single_generation_request_includes_storyboard_controls_and_frame_overrides():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "storyboard_prompt_language": "zh_CN",
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "frame_overrides": [
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["visual_goal"],
                    "visual_goal": "Locked visual goal.",
                }
            ],
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["world_preset_id"] == "neutral_knowledge_storyboard"
    assert request["shot_preset_id"] == "balanced_explainer"
    assert request["storyboard_prompt_language"] == "zh_CN"
    assert request["consistency_strength"] == "strong"
    assert request["content_mode"] == "concept_explainer"
    assert request["role_strategy"] == "auto"
    assert request["role_locking_strength"] == "strong"
    assert request["shot_strategy"] == "strict"
    assert request["frame_overrides"] == [
        {
            "plan_id": "plan_abc",
            "plan_revision": 1,
            "frame_id": "frame_0001",
            "source_digest": "a" * 64,
            "locked_fields": ["visual_goal"],
            "visual_goal": "Locked visual goal.",
        }
    ]


def test_build_single_generation_request_drops_legacy_scene_identity_overrides():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "frame_overrides": [
                {
                    "scene_id": "scene-1",
                    "snapshot_identity": "snapshot:scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert "frame_overrides" not in request


def test_build_single_generation_request_includes_text_rendering_policy():
    def _progress(_event):
        return None

    text_rendering = {
        "overlay": {"enabled": False},
        "image_text": {
            "suppress_embedded_text": True,
            "positive_prompt": "avoid generated lettering",
        },
    }

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "text_rendering": text_rendering,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["text_rendering"] == text_rendering
    assert "forbid_embedded_text_in_image" not in request
    assert "text_layer" not in request


def test_build_single_generation_request_ignores_legacy_text_fields():
    def _progress(_event):
        return None

    text_layer = {
        "enabled": True,
        "mode": "hybrid",
        "renderer_targets": ["hyperframes", "ass"],
        "density": "low",
        "max_items_per_frame": 1,
    }

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "text_layer": text_layer,
            "forbid_embedded_text_in_image": False,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert "text_layer" not in request
    assert "forbid_embedded_text_in_image" not in request


def test_build_single_generation_request_omits_text_rendering_when_absent():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert "text_rendering" not in request


def test_build_single_generation_request_includes_prompt_generation_performance_overrides():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            LLM_PROMPT_BATCH_SIZE_PARAM: 8,
            LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM: 3,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request[LLM_PROMPT_BATCH_SIZE_PARAM] == 8
    assert request[LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM] == 3


def test_build_single_generation_request_omits_prompt_generation_performance_when_absent():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert LLM_PROMPT_BATCH_SIZE_PARAM not in request
    assert LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM not in request


def test_build_batch_shared_config_includes_render_backend():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "bgm_path": None,
            "bgm_volume": 0.2,
            "tts_inference_mode": "local",
            "tts_voice": "zh-CN-YunjianNeural",
            "tts_speed": 1.1,
            "tts_audio_strategy": "master_track",
            "template_params": {"accent_color": "#fff"},
            "media_width": 1080,
            "media_height": 1920,
            "render_backend": "hyperframes_compiled",
        }
    )

    assert shared_config["render_backend"] == "hyperframes_compiled"
    assert shared_config["tts_audio_strategy"] == "master_track"


def test_build_batch_shared_config_uses_size_contract_defaults_and_overrides():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "video_orientation": "square",
            "video_resolution_preset": "2k",
            "media_orientation": "portrait",
            "media_resolution_preset": "4k",
            "sync_media_size_to_canvas": False,
        }
    )

    assert (shared_config["canvas_width"], shared_config["canvas_height"]) == (
        2048,
        2048,
    )
    assert (shared_config["media_width"], shared_config["media_height"]) == (
        2160,
        3840,
    )
    assert shared_config["video_orientation"] == "square"
    assert shared_config["video_resolution_preset"] == "2k"
    assert shared_config["media_orientation"] == "portrait"
    assert shared_config["media_resolution_preset"] == "4k"
    assert shared_config["sync_media_size_to_canvas"] is False


def test_build_batch_shared_config_uses_storyboard_generation_contract_fields():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 6,
            "script_length_mode": "long",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        }
    )

    assert shared_config["storyboard_mode"] == "smart"
    assert shared_config["storyboard_count_mode"] == "manual"
    assert shared_config["storyboard_scene_count"] == 6
    assert shared_config["script_length_mode"] == "long"
    assert "script_target_words" not in shared_config
    assert "n_scenes" not in shared_config
    assert "split_mode" not in shared_config


def test_build_batch_shared_config_includes_prompt_generation_performance_overrides():
    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            LLM_PROMPT_BATCH_SIZE_PARAM: 8,
            LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM: 3,
        }
    )

    assert shared_config[LLM_PROMPT_BATCH_SIZE_PARAM] == 8
    assert shared_config[LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM] == 3


def test_build_batch_shared_config_omits_prompt_generation_performance_when_absent():
    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        }
    )

    assert LLM_PROMPT_BATCH_SIZE_PARAM not in shared_config
    assert LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM not in shared_config


def test_build_batch_shared_config_passes_session_id():
    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            "session_id": "sess_5678",
        }
    )

    assert shared_config["session_id"] == "sess_5678"


def test_build_batch_shared_config_includes_storyboard_controls_and_frame_overrides():
    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "storyboard_prompt_language": "zh_CN",
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "frame_overrides": [
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["visual_goal"],
                    "visual_goal": "Locked visual goal.",
                }
            ],
        }
    )

    assert shared_config["world_preset_id"] == "neutral_knowledge_storyboard"
    assert shared_config["shot_preset_id"] == "balanced_explainer"
    assert shared_config["storyboard_prompt_language"] == "zh_CN"
    assert shared_config["consistency_strength"] == "strong"
    assert shared_config["content_mode"] == "concept_explainer"
    assert shared_config["role_strategy"] == "auto"
    assert shared_config["role_locking_strength"] == "strong"
    assert shared_config["shot_strategy"] == "strict"
    assert shared_config["frame_overrides"] == [
        {
            "plan_id": "plan_abc",
            "plan_revision": 1,
            "frame_id": "frame_0001",
            "source_digest": "a" * 64,
            "locked_fields": ["visual_goal"],
            "visual_goal": "Locked visual goal.",
        }
    ]


def test_build_batch_shared_config_drops_legacy_scene_identity_overrides():
    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "frame_overrides": [
                {
                    "scene_id": "scene-1",
                    "snapshot_identity": "snapshot:scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        }
    )

    assert "frame_overrides" not in shared_config


def test_build_batch_shared_config_includes_text_rendering_policy():
    text_rendering = {
        "overlay": {"enabled": True, "mode": "programmatic_only"},
        "image_text": {"suppress_embedded_text": False},
    }

    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "text_rendering": text_rendering,
        }
    )

    assert shared_config["text_rendering"] == text_rendering
    assert "forbid_embedded_text_in_image" not in shared_config
    assert "text_layer" not in shared_config


def test_build_batch_shared_config_ignores_legacy_text_fields():
    text_layer = {
        "enabled": True,
        "mode": "programmatic_only",
        "renderer_targets": ["ass"],
        "density": "medium",
        "max_items_per_frame": 2,
    }

    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "text_layer": text_layer,
            "forbid_embedded_text_in_image": False,
        }
    )

    assert "text_layer" not in shared_config
    assert "forbid_embedded_text_in_image" not in shared_config


def test_build_single_generation_request_includes_tts_speed_for_comfyui():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "bgm_path": None,
            "bgm_volume": 0.3,
            "tts_inference_mode": "comfyui",
            "tts_workflow": "selfhost/tts_index2.json",
            "tts_speed": 1.2,
            "ref_audio": "temp/ref.wav",
            "render_backend": "hyperframes_compiled",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["tts_speed"] == 1.2
    assert request["tts_workflow"] == "selfhost/tts_index2.json"


def test_build_batch_shared_config_includes_tts_speed_for_comfyui():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "bgm_path": None,
            "bgm_volume": 0.2,
            "tts_inference_mode": "comfyui",
            "tts_workflow": "selfhost/tts_index2.json",
            "tts_speed": 1.2,
            "ref_audio": "temp/ref.wav",
        }
    )

    assert shared_config["tts_workflow"] == "selfhost/tts_index2.json"
    assert shared_config["tts_speed"] == 1.2


def test_render_single_output_passes_storyboard_controls_to_generate_video(monkeypatch, tmp_path):
    captured = {}
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def text(self, _value):
            return None

        def empty(self):
            return None

        def markdown(self, _value):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            return True

        def error(self, message):
            raise AssertionError(message)

        def stop(self):
            raise AssertionError("st.stop should not be called")

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def download_button(self, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                video_path=str(video_path),
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    planning_snapshot={"world_preset_id": "neutral_knowledge_storyboard"},
                    config=SimpleNamespace(frame_template="1080x1920/image_default.html"),
                    frames=[object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "render_scaled_video_preview", lambda _path: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "tts_inference_mode": "local",
            "tts_voice": "zh-CN-YunjianNeural",
            "render_backend": "hyperframes_compiled",
            "tts_audio_strategy": "master_track",
            "tts_split_mode": "external_only",
            "max_chars_per_tts_segment": 64,
            "tts_split_overflow_policy": "error",
            "tts_boundary_search_radius": 12,
            "tts_soft_overflow_chars": 4,
            "tts_audio_boundary_fade_ms": 16,
            "text_rendering": {
                "overlay": {
                    "enabled": True,
                    "mode": "hybrid",
                    "renderer_targets": ["hyperframes", "ass"],
                },
                "image_text": {
                    "suppress_embedded_text": True,
                    "positive_prompt": "avoid generated lettering",
                },
            },
            "element_animation_enabled": True,
            "element_animation_backend": "python_ffmpeg",
            "element_animation_subject_count": 4,
            "element_animation_candidate_limit": 6,
            "element_animation_prompt": "animate the main product",
            "element_animation_intensity": "high",
            "element_animation_workflow": "custom_segment.json",
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "frame_overrides": [
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["visual_goal"],
                    "visual_goal": "Locked visual goal.",
                }
            ],
        },
    )

    assert captured["request"]["world_preset_id"] == "neutral_knowledge_storyboard"
    assert captured["request"]["shot_preset_id"] == "balanced_explainer"
    assert captured["request"]["consistency_strength"] == "strong"
    assert captured["request"]["content_mode"] == "concept_explainer"
    assert captured["request"]["role_strategy"] == "auto"
    assert captured["request"]["role_locking_strength"] == "strong"
    assert captured["request"]["shot_strategy"] == "strict"
    assert captured["request"]["tts_split_mode"] == "external_only"
    assert captured["request"]["max_chars_per_tts_segment"] == 64
    assert captured["request"]["tts_split_overflow_policy"] == "error"
    assert captured["request"]["tts_boundary_search_radius"] == 12
    assert captured["request"]["tts_soft_overflow_chars"] == 4
    assert captured["request"]["tts_audio_boundary_fade_ms"] == 16
    assert captured["request"]["text_rendering"] == {
        "overlay": {
            "enabled": True,
            "mode": "hybrid",
            "renderer_targets": ["hyperframes", "ass"],
        },
        "image_text": {
            "suppress_embedded_text": True,
            "positive_prompt": "avoid generated lettering",
        },
    }
    assert captured["request"]["element_animation_enabled"] is True
    assert captured["request"]["element_animation_backend"] == "python_ffmpeg"
    assert captured["request"]["element_animation_subject_count"] == 4
    assert captured["request"]["element_animation_candidate_limit"] == 6
    assert captured["request"]["element_animation_prompt"] == "animate the main product"
    assert captured["request"]["element_animation_intensity"] == "high"
    assert captured["request"]["element_animation_workflow"] == "custom_segment.json"
    assert "forbid_embedded_text_in_image" not in captured["request"]
    assert "text_layer" not in captured["request"]
    assert captured["request"]["frame_overrides"] == [
        {
            "plan_id": "plan_abc",
            "plan_revision": 1,
            "frame_id": "frame_0001",
            "source_digest": "a" * 64,
            "locked_fields": ["visual_goal"],
            "visual_goal": "Locked visual goal.",
        }
    ]


def test_render_single_output_translates_progress_extra_info(monkeypatch, tmp_path):
    captured = {"status_messages": []}
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def text(self, value):
            captured["status_messages"].append(value)

        def empty(self):
            return None

        def markdown(self, _value):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            return True

        def error(self, message):
            raise AssertionError(message)

        def stop(self):
            raise AssertionError("st.stop should not be called")

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def download_button(self, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **kwargs):
            kwargs["progress_callback"](
                output_preview.ProgressEvent(
                    event_type="generating_image_prompts",
                    progress=0.15,
                    extra_info="progress.detail.style_resolution",
                )
            )
            return SimpleNamespace(
                video_path=str(video_path),
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    planning_snapshot=None,
                    config=SimpleNamespace(frame_template="1080x1920/image_default.html"),
                    frames=[object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(
        output_preview,
        "tr",
        lambda key, **kwargs: {
            "section.video_generation": "section.video_generation",
            "btn.generate": "btn.generate",
            "progress.generating_image_prompts": "Generating image prompts...",
            "progress.detail.style_resolution": "resolving style profile",
            "status.success": "success",
            "status.video_generated": "video generated",
            "info.generation_time": "time",
            "info.scenes_unit": " scenes",
        }.get(key, key),
    )
    monkeypatch.setattr(output_preview, "render_scaled_video_preview", lambda _path: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "tts_inference_mode": "local",
            "tts_voice": "zh-CN-YunjianNeural",
        },
    )

    assert "Generating image prompts... - resolving style profile" in captured["status_messages"]


def test_render_single_output_stores_recent_generated_video_and_renders_gallery(monkeypatch, tmp_path):
    captured = {"events": []}
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def text(self, _value):
            return None

        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            captured["events"].append("button")
            return True

        def error(self, message):
            raise AssertionError(message)

        def stop(self):
            raise AssertionError("st.stop should not be called")

        def progress(self, _value):
            captured["events"].append("progress")
            return _FakeProgressBar()

        def empty(self):
            captured["events"].append("empty")
            return _FakeStatus()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def download_button(self, **_kwargs):
            raise AssertionError("single download button should be replaced by gallery card")

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            captured["events"].append("generate")
            return SimpleNamespace(
                video_path=str(video_path),
                duration=8.5,
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    title="Generated",
                    planning_snapshot=None,
                    config=SimpleNamespace(
                        task_id="task-generated",
                        frame_template="1080x1920/image_default.html",
                    ),
                    frames=[object(), object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(
        output_preview,
        "render_scaled_video_preview",
        lambda _path: (_ for _ in ()).throw(AssertionError("old preview should not render")),
    )
    monkeypatch.setattr(
        output_preview,
        "store_recent_generated_video",
        lambda result, session_state: captured["events"].append("store"),
        raising=False,
    )
    monkeypatch.setattr(
        output_preview,
        "render_recent_video_gallery",
        lambda pixelle_video, **_kwargs: captured["events"].append("gallery"),
        raising=False,
    )

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "tts_inference_mode": "local",
            "tts_voice": "zh-CN-YunjianNeural",
        },
    )

    assert captured["events"] == [
        "empty",
        "button",
        "progress",
        "empty",
        "empty",
        "empty",
        "gallery",
        "generate",
        "store",
        "gallery",
        "button",
    ]


def test_render_single_output_preserves_ui_size_contract_when_generating(
    monkeypatch,
    tmp_path,
):
    captured = {"button_calls": 0, "request": None}
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeSlot:
        def text(self, _value):
            return None

        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {}

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            captured["button_calls"] += 1
            return captured["button_calls"] == 1

        def error(self, message):
            raise AssertionError(message)

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeSlot()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def info(self, *_args, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                video_path=str(video_path),
                duration=8.5,
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    title="Generated",
                    planning_snapshot=None,
                    config=SimpleNamespace(
                        task_id="task-generated",
                        frame_template="1080x1920/image_default.html",
                        canvas_width=kwargs["canvas_width"],
                        canvas_height=kwargs["canvas_height"],
                    ),
                    frames=[object(), object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "tts_inference_mode": "local",
            "tts_voice": "zh-CN-YunjianNeural",
            "video_orientation": "landscape",
            "video_resolution_preset": "1k",
            "media_orientation": "landscape",
            "media_resolution_preset": "1k",
            "sync_media_size_to_canvas": False,
        },
    )

    assert captured["request"] is not None
    assert (captured["request"]["canvas_width"], captured["request"]["canvas_height"]) == (
        1280,
        720,
    )
    assert (captured["request"]["media_width"], captured["request"]["media_height"]) == (
        1280,
        720,
    )
    assert captured["request"]["media_orientation"] == "landscape"
    assert captured["request"]["media_resolution_preset"] == "1k"


def test_render_single_output_places_success_summary_before_recent_gallery(
    monkeypatch,
    tmp_path,
):
    captured = {
        "button_calls": 0,
        "current_slot": None,
        "events": [],
        "slot_order": [],
    }
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __init__(self, slot_name=None):
            self.slot_name = slot_name
            self.previous_slot = None

        def __enter__(self):
            self.previous_slot = captured["current_slot"]
            if self.slot_name is not None:
                captured["current_slot"] = self.slot_name
            return self

        def __exit__(self, exc_type, exc, tb):
            captured["current_slot"] = self.previous_slot
            return False

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeSlot:
        def __init__(self, name):
            self.name = name

        def text(self, value):
            captured["events"].append(("status", self.name, value))

        def empty(self):
            captured["events"].append(("slot_empty", self.name))

        def container(self):
            return _FakeContext(self.name)

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "template_media_width": 1280,
                "template_media_height": 720,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            captured["button_calls"] += 1
            return captured["button_calls"] == 1

        def error(self, message):
            raise AssertionError(message)

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            slot_name = f"slot_{len(captured['slot_order']) + 1}"
            captured["slot_order"].append(slot_name)
            return _FakeSlot(slot_name)

        def success(self, message, **_kwargs):
            captured["events"].append(("summary_success", captured["current_slot"], message))

        def caption(self, message, **_kwargs):
            captured["events"].append(("summary_caption", captured["current_slot"], message))

        def info(self, *_args, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            return SimpleNamespace(
                video_path=str(video_path),
                duration=8.5,
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    title="Generated",
                    planning_snapshot=None,
                    config=SimpleNamespace(
                        task_id="task-generated",
                        frame_template="1080x1920/image_default.html",
                        canvas_width=1280,
                        canvas_height=720,
                    ),
                    frames=[object(), object()],
                ),
            )

    def _render_recent_gallery(_pixelle_video, **kwargs):
        captured["events"].append(
            ("gallery", captured["current_slot"], kwargs.get("key_suffix", ""))
        )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", _render_recent_gallery)

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
        },
    )

    summary_event = next(event for event in captured["events"] if event[0] == "summary_success")
    success_status_event = next(
        event
        for event in captured["events"]
        if event[0] == "status" and event[2] == "status.success"
    )
    refreshed_gallery_event = next(
        event for event in captured["events"] if event[0] == "gallery" and event[2]
    )
    initial_gallery_event = next(
        event for event in captured["events"] if event[0] == "gallery" and not event[2]
    )

    assert summary_event[1] in captured["slot_order"]
    assert refreshed_gallery_event[1] in captured["slot_order"]
    assert initial_gallery_event[1] == refreshed_gallery_event[1]
    assert captured["slot_order"].index(summary_event[1]) < captured["slot_order"].index(
        refreshed_gallery_event[1]
    )
    assert captured["events"].index(success_status_event) < captured["events"].index(
        summary_event
    )
    assert captured["events"].index(summary_event) < captured["events"].index(
        refreshed_gallery_event
    )


def test_render_single_output_shows_gallery_before_blocking_generation(monkeypatch, tmp_path):
    captured = {"events": []}
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def text(self, _value):
            return None

        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **kwargs):
            kwargs["on_click"]()
            captured["events"].append("button")
            return True

        def error(self, message):
            raise AssertionError(message)

        def progress(self, _value):
            captured["events"].append("progress")
            return _FakeProgressBar()

        def empty(self):
            captured["events"].append("empty")
            return _FakeStatus()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            captured["events"].append("generate")
            assert "gallery" in captured["events"]
            return SimpleNamespace(
                video_path=str(video_path),
                duration=8.5,
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    title="Generated",
                    planning_snapshot=None,
                    config=SimpleNamespace(
                        task_id="task-generated",
                        frame_template="1080x1920/image_default.html",
                    ),
                    frames=[object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: None)
    monkeypatch.setattr(
        output_preview,
        "render_recent_video_gallery",
        lambda _pixelle_video, **_kwargs: captured["events"].append("gallery"),
    )

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
        },
    )


def test_render_single_output_keeps_existing_recent_video_during_generation(
    monkeypatch,
    tmp_path,
):
    captured = {"current_visible_before_generate": None}
    previous_video = tmp_path / "previous.mp4"
    previous_video.write_bytes(b"previous")
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def text(self, _value):
            return None

        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "recent_generated_video": {
                    "task_id": "task-previous",
                    "title": "Previous",
                    "video_path": str(previous_video),
                },
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **kwargs):
            kwargs["on_click"]()
            return True

        def error(self, message):
            raise AssertionError(message)

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            assert captured["current_visible_before_generate"] is True
            return SimpleNamespace(
                video_path=str(video_path),
                duration=8.5,
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    title="Generated",
                    planning_snapshot=None,
                    config=SimpleNamespace(
                        task_id="task-generated",
                        frame_template="1080x1920/image_default.html",
                    ),
                    frames=[object()],
                ),
            )

    fake_st = FakeStreamlit()

    def _render_gallery(_pixelle_video, **_kwargs):
        if captured["current_visible_before_generate"] is None:
            captured["current_visible_before_generate"] = (
                "recent_generated_video" in fake_st.session_state
            )

    monkeypatch.setattr(output_preview, "st", fake_st)
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", _render_gallery)

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
        },
    )


def test_render_single_output_reenables_button_after_generation_finishes(
    monkeypatch,
    tmp_path,
):
    captured = {"button_disabled": [], "generated": False}
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeSlot:
        def text(self, _value):
            return None

        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                output_preview.SINGLE_VIDEO_GENERATING_KEY: True,
                output_preview.SINGLE_VIDEO_REQUESTED_KEY: True,
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **kwargs):
            captured["button_disabled"].append(kwargs["disabled"])
            return False

        def error(self, message):
            raise AssertionError(message)

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeSlot()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def info(self, *_args, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            captured["generated"] = True
            return SimpleNamespace(
                video_path=str(video_path),
                duration=8.5,
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    title="Generated",
                    planning_snapshot=None,
                    config=SimpleNamespace(
                        task_id="task-generated",
                        frame_template="1080x1920/image_default.html",
                    ),
                    frames=[object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
        },
    )

    assert captured["generated"] is True
    assert captured["button_disabled"] == [True, False]


def test_render_single_output_marks_button_disabled_while_generation_runs(monkeypatch, tmp_path):
    captured = {
        "button_disabled": [],
        "button_kwargs": None,
        "generated": False,
        "store": False,
    }
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def text(self, _value):
            return None

        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **kwargs):
            captured["button_disabled"].append(kwargs["disabled"])
            captured["button_kwargs"] = kwargs
            if len(captured["button_disabled"]) == 1:
                kwargs["on_click"]()
            return True

        def error(self, message):
            raise AssertionError(message)

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def info(self, *_args, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            captured["generated"] = True
            assert output_preview.st.session_state[output_preview.SINGLE_VIDEO_GENERATING_KEY] is True
            return SimpleNamespace(
                video_path=str(video_path),
                duration=8.5,
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    title="Generated",
                    planning_snapshot=None,
                    config=SimpleNamespace(
                        task_id="task-generated",
                        frame_template="1080x1920/image_default.html",
                    ),
                    frames=[object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(
        output_preview,
        "store_recent_generated_video",
        lambda result, session_state: captured.update(store=True),
        raising=False,
    )
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "media_workflow": "runninghub/image_flux.json",
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "clean",
            "tts_inference_mode": "local",
            "tts_voice": "zh-CN-YunjianNeural",
        },
    )

    assert captured["button_kwargs"]["disabled"] is False
    assert captured["button_disabled"] == [False, False]
    assert output_preview.st.session_state[output_preview.SINGLE_VIDEO_GENERATING_KEY] is False
    assert output_preview.st.session_state[output_preview.SINGLE_VIDEO_REQUESTED_KEY] is False
    assert captured["generated"] is True
    assert captured["store"] is True


def test_render_single_output_ignores_duplicate_click_while_generation_active(monkeypatch):
    captured = {"generated": False, "info_messages": []}

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeSlot:
        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                output_preview.SINGLE_VIDEO_GENERATING_KEY: True,
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **kwargs):
            assert kwargs["disabled"] is True
            kwargs["on_click"]()
            return True

        def error(self, message):
            raise AssertionError(message)

        def empty(self):
            return _FakeSlot()

        def info(self, message):
            captured["info_messages"].append(message)

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            captured["generated"] = True

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
        },
    )

    assert captured["generated"] is False
    assert output_preview.st.session_state.get(output_preview.SINGLE_VIDEO_REQUESTED_KEY) is not True
    assert captured["info_messages"] == ["status.generation_in_progress"]


def test_render_single_output_consumes_request_before_long_generation(monkeypatch, tmp_path):
    captured = {"button_disabled": [], "generated": False}
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def text(self, _value):
            return None

        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                output_preview.SINGLE_VIDEO_GENERATING_KEY: True,
                output_preview.SINGLE_VIDEO_REQUESTED_KEY: True,
                "template_media_width": 1080,
                "template_media_height": 1920,
            }

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **kwargs):
            captured["button_disabled"].append(kwargs["disabled"])
            return False

        def error(self, message):
            raise AssertionError(message)

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

        def success(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def info(self, *_args, **_kwargs):
            return None

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            captured["generated"] = True
            assert output_preview.st.session_state[output_preview.SINGLE_VIDEO_GENERATING_KEY] is True
            assert output_preview.st.session_state[output_preview.SINGLE_VIDEO_REQUESTED_KEY] is False
            return SimpleNamespace(
                video_path=str(video_path),
                duration=8.5,
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    title="Generated",
                    planning_snapshot=None,
                    config=SimpleNamespace(
                        task_id="task-generated",
                        frame_template="1080x1920/image_default.html",
                    ),
                    frames=[object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
        },
    )

    assert captured["generated"] is True
    assert captured["button_disabled"] == [True, False]


def test_render_single_output_does_not_stop_before_gallery_on_input_error(monkeypatch):
    captured = {"gallery": False, "generated": False}

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeSlot:
        def empty(self):
            return None

        def container(self):
            return _FakeContext()

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {}

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            return True

        def error(self, _message):
            return None

        def stop(self):
            raise AssertionError("st.stop should not be called")

        def empty(self):
            return _FakeSlot()

    class _FakePixelleVideo:
        async def generate_video(self, **_kwargs):
            captured["generated"] = True

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(
        output_preview,
        "render_recent_video_gallery",
        lambda pixelle_video, **_kwargs: captured.update(gallery=True),
        raising=False,
    )

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
        },
    )

    assert captured == {"gallery": True, "generated": False}


def test_render_batch_output_writes_last_successful_planning_snapshot(monkeypatch):
    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def markdown(self, _value):
            return None

        def text(self, _value):
            return None

        def empty(self):
            return None

    class _FakeColumn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def metric(self, *_args, **_kwargs):
            return None

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {"storyboard_preview_snapshot": {"stale": True}}

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def info(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            return True

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

        def columns(self, spec):
            count = spec if isinstance(spec, int) else len(spec)
            return [_FakeColumn() for _ in range(count)]

        def success(self, *_args, **_kwargs):
            return None

        def error(self, message):
            raise AssertionError(message)

        def expander(self, *_args, **_kwargs):
            return _FakeContext()

        def code(self, *_args, **_kwargs):
            return None

    class _FakeBatchManager:
        def execute_batch(self, **_kwargs):
            return {
                "results": [
                    {
                        "index": 1,
                        "topic": "demo one",
                        "status": "success",
                        "planning_snapshot": {"world_preset_id": "first"},
                    },
                    {
                        "index": 2,
                        "topic": "demo two",
                        "status": "success",
                        "planning_snapshot": {"world_preset_id": "last"},
                    },
                ],
                "errors": [],
                "total_count": 2,
                "success_count": 2,
                "failed_count": 0,
            }

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(batch_manager_module, "SimpleBatchManager", _FakeBatchManager)

    output_preview.render_batch_output(
        object(),
        {
            "topics": ["demo one", "demo two"],
            "tts_inference_mode": "local",
        },
    )

    assert output_preview.st.session_state["storyboard_preview_snapshot"] == {
        "world_preset_id": "last"
    }


def test_render_batch_output_clears_stale_snapshot_when_successes_have_no_planning_snapshot(
    monkeypatch,
):
    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

    class _FakeProgressBar:
        def progress(self, _value):
            return None

        def empty(self):
            return None

    class _FakeStatus:
        def markdown(self, _value):
            return None

        def text(self, _value):
            return None

        def empty(self):
            return None

    class _FakeColumn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def metric(self, *_args, **_kwargs):
            return None

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {"storyboard_preview_snapshot": {"stale": True}}

        def container(self, **_kwargs):
            return _FakeContext()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def info(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            return True

        def progress(self, _value):
            return _FakeProgressBar()

        def empty(self):
            return _FakeStatus()

        def columns(self, spec):
            count = spec if isinstance(spec, int) else len(spec)
            return [_FakeColumn() for _ in range(count)]

        def success(self, *_args, **_kwargs):
            return None

        def error(self, message):
            raise AssertionError(message)

        def expander(self, *_args, **_kwargs):
            return _FakeContext()

        def code(self, *_args, **_kwargs):
            return None

    class _FakeBatchManager:
        def execute_batch(self, **_kwargs):
            return {
                "results": [
                    {
                        "index": 1,
                        "topic": "demo one",
                        "status": "success",
                        "planning_snapshot": None,
                    },
                    {
                        "index": 2,
                        "topic": "demo two",
                        "status": "success",
                        "planning_snapshot": None,
                    },
                ],
                "errors": [],
                "total_count": 2,
                "success_count": 2,
                "failed_count": 0,
            }

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(batch_manager_module, "SimpleBatchManager", _FakeBatchManager)

    output_preview.render_batch_output(
        object(),
        {
            "topics": ["demo one", "demo two"],
            "tts_inference_mode": "local",
        },
    )

    assert output_preview.st.session_state["storyboard_preview_snapshot"] is None
