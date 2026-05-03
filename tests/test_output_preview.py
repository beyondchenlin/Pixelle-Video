import ast
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
from web.utils import progress_i18n
from web.utils.streamlit_helpers import RefreshableSlot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _layered_template_spec_payload(**overrides):
    layers = overrides.pop(
        "layers",
        [
            {
                "id": "media",
                "type": "generated_media",
                "name": "Generated media",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 1,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {
                    "kind": "generated_media",
                    "ref": "generated://primary",
                    "metadata": {},
                },
                "style": {},
                "role": None,
            }
        ],
    )
    payload = {
        "version": "layered_template.v1",
        "template_id": "portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
        "layers": layers,
        "metadata": {"orientation": "portrait"},
    }
    payload.update(overrides)
    return payload


def _disable_layout_preview_recent_presets(monkeypatch):
    monkeypatch.setattr(
        output_preview,
        "_list_layout_preview_recent_presets",
        lambda _params: [],
    )


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
        progress_i18n,
        "tr",
        lambda key, fallback=None, **kwargs: (
            f"批次 {kwargs.get('current')}/{kwargs.get('total')} 已完成"
            if key == "progress.batch_completed"
            else (fallback or key)
        ),
    )

    message = progress_i18n.localize_progress_extra_info(
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


def test_single_generation_runner_initializes_rerun_flag_before_try_block():
    source = (PROJECT_ROOT / "web" / "components" / "output_preview.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    run_generation = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "run_generation"
    )
    first_try_index = next(
        index for index, node in enumerate(run_generation.body)
        if isinstance(node, ast.Try)
    )
    assigned_before_try = {
        target.id
        for node in run_generation.body[:first_try_index]
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert "rerun_after_generation" in assigned_before_try


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


def test_build_single_generation_request_omits_empty_layered_template_snapshot():
    def _progress(_event):
        return None

    spec = {
        "version": "layered_template.v1",
        "template_id": "demo",
        "template_name": "Demo",
        "template_type": "image",
        "canvas_width": 1080,
        "canvas_height": 1920,
        "media_width": 1080,
        "media_height": 1920,
        "safe_area": {"x": 64, "y": 64, "width": 952, "height": 1792, "unit": "px"},
        "layers": [],
        "metadata": {},
    }

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "layered_template_spec": spec,
            "selected_template_preset_id": "demo-preset",
        },
        progress_callback=_progress,
        session_state={},
    )

    assert "layered_template_spec" not in request
    assert "selected_template_preset_id" not in request


def test_build_single_generation_request_includes_layered_template_snapshot_with_layers():
    def _progress(_event):
        return None

    spec = _layered_template_spec_payload()

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "layered_template_spec": spec,
            "selected_template_preset_id": "demo-preset",
        },
        progress_callback=_progress,
        session_state={},
    )

    assert request["layered_template_spec"] == spec
    assert request["selected_template_preset_id"] == "demo-preset"


def test_build_single_generation_request_propagates_business_context_from_session_state():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "session_id": "sess_runtime_only",
        },
        progress_callback=_progress,
        session_state={
            "workspace_id": "workspace_business",
            "project_id": "project_business",
        },
    )

    assert request["workspace_id"] == "workspace_business"
    assert request["project_id"] == "project_business"
    assert request["session_id"] == "sess_runtime_only"


def test_build_single_generation_request_prefers_explicit_business_context():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "workspace_id": "workspace_explicit",
            "project_id": "project_explicit",
        },
        progress_callback=_progress,
        session_state={
            "workspace_id": "workspace_session",
            "project_id": "project_session",
        },
    )

    assert request["workspace_id"] == "workspace_explicit"
    assert request["project_id"] == "project_explicit"


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
            "video_resolution_preset": "landscape_hd",
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
    assert request["video_resolution_preset"] == "landscape_hd"
    assert request["media_orientation"] == "square"
    assert request["media_resolution_preset"] == "768"
    assert request["sync_media_size_to_canvas"] is False
    assert request["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "offset_x": 0,
        "offset_y": 0,
    }


def test_build_single_generation_request_uses_media_placement_payload():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "media_placement": {
                "basis": "canvas",
                "fit": "contain",
                "scale_percent": 90,
                "offset_x": 64,
                "offset_y": -32,
            },
        },
        progress_callback=_progress,
        session_state={
            "media_placement": {
                "basis": "canvas",
                "fit": "contain",
                "scale_percent": 70,
                "offset_x": -64,
                "offset_y": 32,
            }
        },
    )

    assert request["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "offset_x": 64,
        "offset_y": -32,
    }


def test_build_single_generation_request_omits_empty_layered_template_snapshot_duplicate():
    def _progress(_event):
        return None

    layered_template_spec = {
        "version": "layered_template.v1",
        "template_id": "portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
        "layers": [],
        "metadata": {"render_backend": "html_preview"},
    }

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "layered_template_spec": layered_template_spec,
            "selected_template_preset_id": "portrait_news",
        },
        progress_callback=_progress,
        session_state={},
    )

    assert "layered_template_spec" not in request
    assert "selected_template_preset_id" not in request


def test_build_batch_shared_config_omits_empty_layered_template_snapshot():
    layered_template_spec = {
        "version": "layered_template.v1",
        "template_id": "portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
        "layers": [],
        "metadata": {"render_backend": "html_preview"},
    }

    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "layered_template_spec": layered_template_spec,
            "selected_template_preset_id": "portrait_news",
        }
    )

    assert "layered_template_spec" not in shared_config
    assert "selected_template_preset_id" not in shared_config


def test_build_batch_shared_config_includes_layered_template_snapshot_with_layers():
    spec = _layered_template_spec_payload()

    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "layered_template_spec": spec,
            "selected_template_preset_id": "portrait_news",
        }
    )

    assert shared_config["layered_template_spec"] == spec
    assert shared_config["selected_template_preset_id"] == "portrait_news"


def test_build_single_generation_request_uses_full_hd_standard_preset():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_full_hd",
            "media_orientation": "square",
            "media_resolution_preset": "768",
            "sync_media_size_to_canvas": False,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert (request["canvas_width"], request["canvas_height"]) == (1920, 1080)
    assert (request["media_width"], request["media_height"]) == (768, 768)
    assert request["video_orientation"] == "landscape"
    assert request["video_resolution_preset"] == "landscape_full_hd"
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
            "video_resolution_preset": "portrait_full_hd",
            "media_orientation": "landscape",
            "media_resolution_preset": "1k",
            "sync_media_size_to_canvas": True,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert (request["canvas_width"], request["canvas_height"]) == (1080, 1920)
    assert (request["media_width"], request["media_height"]) == (1080, 1920)
    assert request["video_resolution_preset"] == "portrait_full_hd"
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
        "title_style": {
            "font_size": 84,
            "primary_color": "#2C3E50",
            "position": "top",
        },
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
    assert request["text_rendering"]["title_style"] is text_rendering["title_style"]
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


def test_build_batch_shared_config_omits_empty_layered_template_snapshot_duplicate():
    spec = {
        "version": "layered_template.v1",
        "template_id": "demo",
        "template_name": "Demo",
        "template_type": "image",
        "canvas_width": 1080,
        "canvas_height": 1920,
        "media_width": 1080,
        "media_height": 1920,
        "safe_area": {"x": 64, "y": 64, "width": 952, "height": 1792, "unit": "px"},
        "layers": [],
        "metadata": {},
    }

    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "layered_template_spec": spec,
            "selected_template_preset_id": "demo-preset",
        }
    )

    assert "layered_template_spec" not in shared_config
    assert "selected_template_preset_id" not in shared_config


def test_build_batch_shared_config_uses_size_contract_defaults_and_overrides():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "video_orientation": "square",
            "video_resolution_preset": "square_standard",
            "media_orientation": "portrait",
            "media_resolution_preset": "4k",
            "sync_media_size_to_canvas": False,
        }
    )

    assert (shared_config["canvas_width"], shared_config["canvas_height"]) == (
        1080,
        1080,
    )
    assert (shared_config["media_width"], shared_config["media_height"]) == (
        2160,
        3840,
    )
    assert shared_config["video_orientation"] == "square"
    assert shared_config["video_resolution_preset"] == "square_standard"
    assert shared_config["media_orientation"] == "portrait"
    assert shared_config["media_resolution_preset"] == "4k"
    assert shared_config["sync_media_size_to_canvas"] is False
    assert shared_config["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "offset_x": 0,
        "offset_y": 0,
    }


def test_build_batch_shared_config_uses_standard_video_preset():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "video_orientation": "portrait",
            "video_resolution_preset": "portrait_full_hd",
            "media_orientation": "square",
            "media_resolution_preset": "768",
        }
    )

    assert (shared_config["canvas_width"], shared_config["canvas_height"]) == (
        1080,
        1920,
    )
    assert (shared_config["media_width"], shared_config["media_height"]) == (768, 768)
    assert shared_config["video_orientation"] == "portrait"
    assert shared_config["video_resolution_preset"] == "portrait_full_hd"
    assert shared_config["media_orientation"] == "square"
    assert shared_config["media_resolution_preset"] == "768"
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


def test_build_batch_shared_config_propagates_business_context():
    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            "session_id": "sess_batch_runtime",
            "workspace_id": "workspace_batch",
            "project_id": "project_batch",
        }
    )

    assert shared_config["workspace_id"] == "workspace_batch"
    assert shared_config["project_id"] == "project_batch"
    assert shared_config["session_id"] == "sess_batch_runtime"


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
    _disable_layout_preview_recent_presets(monkeypatch)
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


def test_render_single_output_reruns_after_storyboard_snapshot_updates(
    monkeypatch,
    tmp_path,
):
    captured = {"rerun": False}
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"video")

    class _RerunRequested(Exception):
        pass

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
            return SimpleNamespace(
                video_path=str(video_path),
                file_size=len(video_path.read_bytes()),
                storyboard=SimpleNamespace(
                    planning_snapshot={"storyboard_generation": {"plan_id": "plan_new"}},
                    config=SimpleNamespace(frame_template="1080x1920/image_default.html"),
                    frames=[object()],
                ),
            )

    def _safe_rerun():
        captured["rerun"] = True
        raise _RerunRequested

    fake_st = FakeStreamlit()
    monkeypatch.setattr(output_preview, "st", fake_st)
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)
    monkeypatch.setattr(output_preview, "safe_rerun", _safe_rerun, raising=False)

    try:
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
    except _RerunRequested:
        pass

    assert fake_st.session_state["storyboard_preview_snapshot"] == {
        "storyboard_generation": {"plan_id": "plan_new"}
    }
    assert captured["rerun"] is True


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
    _disable_layout_preview_recent_presets(monkeypatch)
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    def fake_tr(key, **kwargs):
        return {
            "section.video_generation": "section.video_generation",
            "btn.generate": "btn.generate",
            "progress.generating_image_prompts": "Generating image prompts...",
            "progress.detail.style_resolution": "resolving style profile",
            "status.success": "success",
            "status.video_generated": "video generated",
            "info.generation_time": "time",
            "info.scenes_unit": " scenes",
        }.get(key, key)

    monkeypatch.setattr(output_preview, "tr", fake_tr)
    monkeypatch.setattr(progress_i18n, "tr", fake_tr)
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
    _disable_layout_preview_recent_presets(monkeypatch)
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


def test_render_single_output_renders_workbench_between_generation_and_recent(
    monkeypatch,
    tmp_path,
):
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
                "template_media_width": 720,
                "template_media_height": 1280,
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

        def info(self, *_args, **_kwargs):
            return None

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
                    frames=[object()],
                ),
            )

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    _disable_layout_preview_recent_presets(monkeypatch)
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: captured["events"].append("store"))
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: captured["events"].append("gallery"))
    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        lambda **_kwargs: captured["events"].append("workbench"),
    )

    output_preview.render_single_output(
        _FakePixelleVideo(),
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
            "layered_template_spec": {
                "version": "layered_template.v1",
                "template_id": "portrait_news",
                "template_name": "Portrait News",
                "template_type": "image",
                "canvas_width": 720,
                "canvas_height": 1280,
                "media_width": 640,
                "media_height": 960,
                "safe_area": {
                    "x": 0,
                    "y": 0,
                    "width": 720,
                    "height": 1280,
                    "unit": "px",
                },
                "layers": [],
                "metadata": {"render_backend": "html_preview"},
            },
            "layout_preview_recent_presets": [],
        },
    )

    first_workbench = captured["events"].index("workbench")
    first_gallery = captured["events"].index("gallery")
    refreshed_gallery = len(captured["events"]) - 1 - captured["events"][::-1].index("gallery")
    assert first_workbench < first_gallery
    assert captured["events"].index("store") < refreshed_gallery
    assert captured["events"][refreshed_gallery - 1] == "workbench"


def test_render_single_output_passes_key_suffix_to_workbench_refresh(
    monkeypatch,
    tmp_path,
):
    captured = {"workbench_suffixes": [], "pixelle_video": []}
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
                "template_media_width": 720,
                "template_media_height": 1280,
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
    _disable_layout_preview_recent_presets(monkeypatch)
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(output_preview, "store_recent_generated_video", lambda _result, _state: None)
    monkeypatch.setattr(output_preview, "render_recent_video_gallery", lambda _pixelle_video, **_kwargs: None)
    monkeypatch.setattr(
        output_preview,
        "_render_layout_preview_workbench_section",
        lambda video_params, *, key_suffix="": (
            captured["workbench_suffixes"].append(key_suffix),
            captured["pixelle_video"].append(video_params.get("pixelle_video")),
        ),
    )
    fake_pixelle_video = _FakePixelleVideo()

    output_preview.render_single_output(
        fake_pixelle_video,
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "local",
        },
    )

    assert captured["workbench_suffixes"][0] == ""
    assert any(suffix.startswith("_refresh_") for suffix in captured["workbench_suffixes"][1:])
    assert all(item is fake_pixelle_video for item in captured["pixelle_video"])


def test_render_layout_preview_workbench_section_uses_registry_recent_and_marks_selection(
    monkeypatch,
):
    spec_payload = _layered_template_spec_payload(
        template_id="user:portrait_news",
        metadata={"source_kind": "user"},
    )
    captured = {"list_recent": [], "mark_used": [], "recent_presets": None}

    class _FakeRegistry:
        def list_recent(self, *, limit):
            captured["list_recent"].append(limit)
            return [
                {
                    "preset_id": "user:portrait_news",
                    "template_name": "Portrait News",
                    "last_used_at": "2026-05-02T10:00:00Z",
                    "spec": spec_payload,
                }
            ]

        def mark_used(self, preset_id):
            captured["mark_used"].append(preset_id)

    def _fake_render_layout_preview_workbench(**kwargs):
        captured["recent_presets"] = kwargs["recent_presets"]
        return {
            "preset_id": "user:portrait_news",
            "spec_payload": spec_payload,
        }

    monkeypatch.setattr(output_preview, "TemplateRegistry", _FakeRegistry, raising=False)
    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        _fake_render_layout_preview_workbench,
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    monkeypatch.setattr(
        output_preview,
        "load_layered_template_spec_into_editor_state",
        lambda session_state, spec: session_state.update({"loaded_spec": spec}),
    )
    reruns = []
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(session_state={}, rerun=lambda: reruns.append(True)),
    )

    output_preview._render_layout_preview_workbench_section(
        {"layered_template_spec": spec_payload}
    )

    assert captured["list_recent"] == [5]
    assert captured["recent_presets"][0]["preset_id"] == "user:portrait_news"
    assert captured["mark_used"] == ["user:portrait_news"]
    assert output_preview.st.session_state["loaded_spec"] == spec_payload
    assert (
        output_preview.st.session_state["selected_template_preset_id"]
        == "user:portrait_news"
    )
    assert reruns == [True]


def test_render_layout_preview_workbench_section_renders_empty_state_without_spec(monkeypatch):
    captured = {}

    class _FakeRegistry:
        def list_recent(self, *, limit):
            captured["recent_limit"] = limit
            return []

    def _fake_render_layout_preview_workbench(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(output_preview, "TemplateRegistry", _FakeRegistry, raising=False)
    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        _fake_render_layout_preview_workbench,
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(session_state={}, rerun=lambda: None),
    )

    output_preview._render_layout_preview_workbench_section(
        {"frame_template": "1080x1920/image_default.html"}
    )

    assert captured["spec_payload"] is None
    default_summary = captured["default_layout_summary"]
    assert default_summary.canvas_width == 1280
    assert default_summary.canvas_height == 720
    assert default_summary.media_width == 768
    assert default_summary.media_height == 768
    assert default_summary.media_placement.to_dict() == {
        "scale_percent": 100,
        "offset_x": 0,
        "offset_y": 0,
        "basis": "canvas",
        "fit": "contain",
    }
    assert default_summary.render_summary is None
    assert default_summary.template_summary == "1080x1920/image_default.html"
    assert captured["recent_limit"] == 5
    assert captured["recent_presets"] == []
    assert captured["template_summary"] == "1080x1920/image_default.html"


def test_render_layout_preview_workbench_section_passes_media_placement(monkeypatch):
    spec_payload = _layered_template_spec_payload(
        template_id="user:portrait_news",
        metadata={"source_kind": "user"},
    )
    captured = {"media_placement": None}

    def _fake_render_layout_preview_workbench(**kwargs):
        captured["media_placement"] = kwargs["media_placement"]
        return None

    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        _fake_render_layout_preview_workbench,
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(session_state={}, rerun=lambda: None),
    )

    output_preview._render_layout_preview_workbench_section(
        {
            "layered_template_spec": spec_payload,
            "media_placement": {
                "basis": "canvas",
                "fit": "contain",
                "scale_percent": 76,
                "offset_x": 18,
                "offset_y": -24,
            },
        }
    )

    assert captured["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 76,
        "offset_x": 18,
        "offset_y": -24,
    }


def test_render_layout_preview_workbench_section_refreshes_real_preview_frame(monkeypatch):
    spec_payload = _layered_template_spec_payload(
        template_id="user:portrait_news",
        metadata={"source_kind": "user"},
    )
    captured = {"request": None}

    class _FakeLayeredTemplateService:
        def __init__(self, *args, **kwargs):
            return None

        async def render_preview_frame(self, request):
            captured["request"] = request
            return SimpleNamespace(
                storage_key="artifacts/workspace_demo/layout-preview.png",
                url="/api/files/artifacts/workspace_demo/layout-preview.png",
                fingerprint="preview-fingerprint",
            )

    monkeypatch.setattr(output_preview, "LayeredTemplateService", _FakeLayeredTemplateService)
    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        lambda **_kwargs: {"action": "refresh_preview_frame"},
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(
            session_state={},
            rerun=lambda: None,
            success=lambda *_args, **_kwargs: None,
            error=lambda message: (_ for _ in ()).throw(AssertionError(message)),
        ),
    )

    output_preview._render_layout_preview_workbench_section(
        {
            "layered_template_spec": spec_payload,
            "title": "Demo Title",
            "layout_preview_caption_text": "Demo Caption",
            "text_rendering": {"title_style": {"font_size": 88}},
            "workspace_id": "workspace_demo",
        }
    )

    assert captured["request"] is not None
    assert captured["request"].workspace_id == "workspace_demo"
    assert captured["request"].title_text == "Demo Title"
    assert captured["request"].caption_text == "Demo Caption"
    assert captured["request"].text_rendering == {"title_style": {"font_size": 88}}
    assert output_preview.st.session_state["layout_preview_real_preview_frame"] == {
        "storage_key": "artifacts/workspace_demo/layout-preview.png",
        "url": "/api/files/artifacts/workspace_demo/layout-preview.png",
        "fingerprint": "preview-fingerprint",
    }


def test_render_layout_preview_workbench_section_passes_real_preview_frame_to_workbench(
    monkeypatch,
):
    spec_payload = _layered_template_spec_payload(
        template_id="user:portrait_news",
        metadata={"source_kind": "user"},
    )
    captured = {"real_preview_frame": None}

    def _fake_render_layout_preview_workbench(**kwargs):
        captured["real_preview_frame"] = kwargs.get("real_preview_frame")
        return None

    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        _fake_render_layout_preview_workbench,
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(
            session_state={
                "layout_preview_real_preview_frame": {
                    "storage_key": "artifacts/workspace_demo/layout-preview.png",
                    "url": "/api/files/artifacts/workspace_demo/layout-preview.png",
                    "fingerprint": "preview-fingerprint",
                }
            },
            rerun=lambda: None,
            success=lambda *_args, **_kwargs: None,
            error=lambda message: (_ for _ in ()).throw(AssertionError(message)),
        ),
    )

    output_preview._render_layout_preview_workbench_section(
        {
            "layered_template_spec": spec_payload,
            "workspace_id": "workspace_demo",
        }
    )

    assert captured["real_preview_frame"] == {
        "storage_key": "artifacts/workspace_demo/layout-preview.png",
        "url": "/api/files/artifacts/workspace_demo/layout-preview.png",
        "fingerprint": "preview-fingerprint",
    }


def test_render_layout_preview_workbench_section_does_not_save_template_when_thumbnail_generation_fails(
    monkeypatch,
    tmp_path,
):
    spec_payload = _layered_template_spec_payload(
        template_id="user:portrait_news",
        metadata={"source_kind": "user"},
    )
    repo_root = tmp_path / "template-presets"
    captured = {"mark_used": []}

    class _FakeLayeredTemplateService:
        def __init__(self, *args, **kwargs):
            return None

        async def render_preview_frame(self, request):
            raise RuntimeError("thumbnail failed")

    class _FakeRegistry:
        def list_recent(self, *, limit=5):
            return []

        def mark_used(self, preset_id, used_at=None):
            captured["mark_used"].append(preset_id)

    monkeypatch.setattr(output_preview, "LayeredTemplateService", _FakeLayeredTemplateService)
    monkeypatch.setattr(output_preview, "TemplateRegistry", _FakeRegistry, raising=False)
    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        lambda **_kwargs: {"action": "save_template"},
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    errors = []
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(
            session_state={},
            rerun=lambda: None,
            success=lambda *_args, **_kwargs: None,
            error=lambda message: errors.append(message),
        ),
    )

    output_preview._render_layout_preview_workbench_section(
        {
            "layered_template_spec": spec_payload,
            "workspace_id": "workspace_demo",
            "template_presets_root": str(repo_root),
        }
    )

    assert errors
    assert not (repo_root / "presets.json").exists()
    assert captured["mark_used"] == []


def test_render_layout_preview_workbench_section_rejects_temporary_asset_sources_before_saving(
    monkeypatch,
    tmp_path,
):
    spec_payload = _layered_template_spec_payload(
        template_id="user:portrait_news",
        metadata={"source_kind": "user"},
        layers=[
            {
                "id": "uploaded-image",
                "type": "image",
                "name": "Uploaded Image",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 1,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {"kind": "asset", "ref": str(tmp_path / "upload.png"), "metadata": {}},
                "style": {},
                "role": None,
            }
        ],
    )
    repo_root = tmp_path / "template-presets"
    captured = {"render_preview_frame": False, "mark_used": []}

    class _FakeLayeredTemplateService:
        def __init__(self, *args, **kwargs):
            return None

        async def render_preview_frame(self, request):
            captured["render_preview_frame"] = True
            raise AssertionError("thumbnail generation must not run for invalid asset refs")

    class _FakeRegistry:
        def list_recent(self, *, limit=5):
            return []

        def mark_used(self, preset_id, used_at=None):
            captured["mark_used"].append(preset_id)

    monkeypatch.setattr(output_preview, "LayeredTemplateService", _FakeLayeredTemplateService)
    monkeypatch.setattr(output_preview, "TemplateRegistry", _FakeRegistry, raising=False)
    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        lambda **_kwargs: {"action": "save_template"},
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    errors = []
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(
            session_state={},
            rerun=lambda: None,
            success=lambda *_args, **_kwargs: None,
            error=lambda message: errors.append(message),
        ),
    )

    output_preview._render_layout_preview_workbench_section(
        {
            "layered_template_spec": spec_payload,
            "workspace_id": "workspace_demo",
            "template_presets_root": str(repo_root),
        }
    )

    assert errors == ["asset layers must reference repository asset keys before saving"]
    assert captured["render_preview_frame"] is False
    assert captured["mark_used"] == []
    assert not (repo_root / "presets.json").exists()


def test_render_layout_preview_workbench_section_saves_user_template_and_marks_recent(
    monkeypatch,
    tmp_path,
):
    spec_payload = _layered_template_spec_payload(
        template_id="user:portrait_news",
        metadata={"source_kind": "user"},
    )
    repo_root = tmp_path / "template-presets"
    preview_png = tmp_path / "preview.png"
    preview_png.write_bytes(b"png")
    captured = {"mark_used": []}

    class _FakeLayeredTemplateService:
        def __init__(self, *args, **kwargs):
            return None

        async def render_preview_frame(self, request):
            return SimpleNamespace(
                storage_key="artifacts/workspace_demo/layout-preview.png",
                url="/api/files/artifacts/workspace_demo/layout-preview.png",
                fingerprint="preview-fingerprint",
            )

    class _FakeObjectStore:
        async def get_local_file_uri(self, storage_key):
            assert storage_key == "artifacts/workspace_demo/layout-preview.png"
            return preview_png.as_uri()

    class _FakeRegistry:
        def list_recent(self, *, limit=5):
            return []

        def mark_used(self, preset_id, used_at=None):
            captured["mark_used"].append(preset_id)

    monkeypatch.setattr(output_preview, "LayeredTemplateService", _FakeLayeredTemplateService)
    monkeypatch.setattr(output_preview, "TemplateRegistry", _FakeRegistry, raising=False)
    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        lambda **_kwargs: {"action": "save_template"},
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    monkeypatch.setattr(output_preview, "run_async", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(
            session_state={},
            rerun=lambda: None,
            success=lambda *_args, **_kwargs: None,
            error=lambda message: (_ for _ in ()).throw(AssertionError(message)),
        ),
    )

    output_preview._render_layout_preview_workbench_section(
        {
            "layered_template_spec": spec_payload,
            "workspace_id": "workspace_demo",
            "project_id": "project_demo",
            "artifact_object_store": _FakeObjectStore(),
            "template_presets_root": str(repo_root),
        }
    )

    from pixelle_video.repositories.template_presets import TemplatePresetRepository

    repo = TemplatePresetRepository(root=repo_root)
    saved = repo.list_all(source="user")
    assert len(saved) == 1
    assert saved[0].name == "Portrait News"
    assert saved[0].source == "user"
    assert saved[0].thumbnail_ref is not None
    assert saved[0].thumbnail_ref.startswith("thumbnails/")
    assert saved[0].last_used_at is not None
    assert saved[0].spec.template_id == "user:portrait_news"
    assert captured["mark_used"] == [saved[0].preset_id]


def test_build_layout_preview_html_uses_layered_template_service():
    spec = {
        "version": "layered_template.v1",
        "template_id": "portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
        "layers": [],
        "metadata": {"render_backend": "html_preview"},
    }

    html = output_preview._build_layout_preview_html(
        {
            "title": "Demo Title",
            "layered_template_spec": spec,
            "text_rendering": {"title_style": {"font_size": 88}},
            "layout_preview_caption_text": "Demo Caption",
            "layout_preview_html": "<script>alert('must not be trusted')</script>",
        }
    )

    assert html is not None
    assert "width:720px;" in html.html
    assert "must not be trusted" not in html.html


def test_build_layout_preview_html_uses_default_frame_template_without_layered_spec(tmp_path, monkeypatch):
    template = tmp_path / "image_sample.html"
    template.write_text(
        """
        <html>
          <head><meta name="template:media-width" content="640"><meta name="template:media-height" content="480"></head>
          <body>{{title}} {{text}} {{pixelle_media_layer}} {{brand=Pixelle}}</body>
        </html>
        """,
        encoding="utf-8",
    )
    captured = {}

    class _FakeHTMLFrameGenerator:
        def __init__(self, template_path, *, canvas_width=None, canvas_height=None):
            captured["init"] = {
                "template_path": template_path,
                "canvas_width": canvas_width,
                "canvas_height": canvas_height,
            }
            self.template = Path(template_path).read_text(encoding="utf-8")
            self.template_width = 1920
            self.template_height = 1080
            self.width = int(canvas_width)
            self.height = int(canvas_height)

        def _build_render_html(self, **kwargs):
            captured["render_kwargs"] = kwargs
            return (
                self.template.replace("{{title}}", kwargs["title"])
                .replace("{{text}}", kwargs["text"])
                .replace("{{pixelle_media_layer}}", "<div class='pixelle-media-layer'></div>")
                .replace("{{brand=Pixelle}}", "Pixelle")
            )

        def _prepare_html_for_render(self, html):
            return f"<base>{html}"

    monkeypatch.setattr(output_preview, "resolve_template_path", lambda _path: str(template))
    monkeypatch.setattr(output_preview, "HTMLFrameGenerator", _FakeHTMLFrameGenerator)

    html = output_preview._build_layout_preview_html(
        {
            "title": "用户标题",
            "text": "用户正文第一句，用来作为即时模板预览字幕。",
            "frame_template": "1920x1080/image_landscape_minimal.html",
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 768,
            "media_height": 768,
            "media_placement": {
                "basis": "canvas",
                "fit": "contain",
                "scale_percent": 90,
                "offset_x": 12,
                "offset_y": -8,
            },
            "layout_preview_html": "<script>alert('must not be trusted')</script>",
        }
    )

    assert html is not None
    assert html.width == 1920
    assert html.height == 1080
    assert "用户标题" in html.html
    assert "用户正文第一句" in html.html
    assert "默认模板预览" not in html.html
    assert "服务端预览前使用当前模板规则生成即时预览" not in html.html
    assert "pixelle-media-layer" in html.html
    assert "must not be trusted" not in html.html
    assert captured["init"] == {
        "template_path": str(template),
        "canvas_width": 1280,
        "canvas_height": 720,
    }
    assert captured["render_kwargs"]["media_placement"]["scale_percent"] == 90
    assert captured["render_kwargs"]["media_width"] == 768
    assert captured["render_kwargs"]["media_height"] == 768
    assert (
        captured["render_kwargs"]["image"]
        == Path("resources/example.png").resolve().as_uri()
    )
    assert captured["render_kwargs"]["ext"]["media_layout_mode"] == "template"


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
    _disable_layout_preview_recent_presets(monkeypatch)
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
            "video_resolution_preset": "landscape_hd",
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
    assert captured["request"]["video_resolution_preset"] == "landscape_hd"
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
    _disable_layout_preview_recent_presets(monkeypatch)
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
    _disable_layout_preview_recent_presets(monkeypatch)
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
    _disable_layout_preview_recent_presets(monkeypatch)
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
    _disable_layout_preview_recent_presets(monkeypatch)
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
    _disable_layout_preview_recent_presets(monkeypatch)
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
    _disable_layout_preview_recent_presets(monkeypatch)
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
    _disable_layout_preview_recent_presets(monkeypatch)
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


def test_render_single_output_renders_workbench_between_generation_and_recent(monkeypatch):
    sections = []

    monkeypatch.setattr(
        output_preview,
        "_render_layout_preview_workbench_section",
        lambda *args, **kwargs: sections.append("workbench"),
        raising=False,
    )
    monkeypatch.setattr(
        output_preview,
        "render_recent_video_gallery",
        lambda *args, **kwargs: sections.append("recent"),
    )
    monkeypatch.setattr(
        output_preview,
        "_render_generation_section",
        lambda *args, **kwargs: sections.append("generation"),
        raising=False,
    )

    output_preview._render_single_output_sections(object(), {"text": "demo"})

    assert sections == ["generation", "workbench", "recent"]


def test_render_batch_output_writes_last_successful_planning_snapshot(monkeypatch):
    captured = {"snapshot_updates": []}

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

    def _set_storyboard_preview_snapshot(session_state, snapshot):
        captured["snapshot_updates"].append(snapshot)
        session_state["storyboard_preview_snapshot"] = snapshot
        return True

    monkeypatch.setattr(
        output_preview,
        "set_storyboard_preview_snapshot",
        _set_storyboard_preview_snapshot,
    )

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
    assert captured["snapshot_updates"] == [{"world_preset_id": "last"}]


def test_render_batch_output_clears_stale_snapshot_when_successes_have_no_planning_snapshot(
    monkeypatch,
):
    captured = {"snapshot_updates": []}

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

    def _set_storyboard_preview_snapshot(session_state, snapshot):
        captured["snapshot_updates"].append(snapshot)
        session_state["storyboard_preview_snapshot"] = snapshot
        return True

    monkeypatch.setattr(
        output_preview,
        "set_storyboard_preview_snapshot",
        _set_storyboard_preview_snapshot,
    )

    output_preview.render_batch_output(
        object(),
        {
            "topics": ["demo one", "demo two"],
            "tts_inference_mode": "local",
        },
    )

    assert output_preview.st.session_state["storyboard_preview_snapshot"] is None
    assert captured["snapshot_updates"] == [None]
