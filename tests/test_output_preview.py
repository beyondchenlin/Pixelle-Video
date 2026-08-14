import asyncio
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from PIL import Image

from pixelle_video.models.progress import ProgressI18nMessage
from pixelle_video.models.size_contract import GenerationSizeContract
from pixelle_video.models.video_generation_contract import (
    ARTICLE_CONCRETIZATION_FLAT_OPTION_KEYS,
)
from web.components import output_preview
from web.components.prompt_generation_performance import (
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
    LLM_PROMPT_BATCH_SIZE_PARAM,
)
from web.utils import batch_manager as batch_manager_module
from web.utils import progress_i18n
from web.utils.streamlit_helpers import RefreshableSlot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_article_concretization_option_keys_match_generation_contract():
    assert (
        output_preview.ARTICLE_CONCRETIZATION_OPTION_KEYS
        == ARTICLE_CONCRETIZATION_FLAT_OPTION_KEYS
    )
    assert (
        output_preview.ARTICLE_CONCRETIZATION_OPTION_KEYS
        is ARTICLE_CONCRETIZATION_FLAT_OPTION_KEYS
    )


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


def test_layout_preview_fallback_store_anchors_relative_root_to_project(
    monkeypatch,
    tmp_path,
):
    project_root = tmp_path / "project"
    unrelated_cwd = tmp_path / "unrelated"
    project_root.mkdir()
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    monkeypatch.setattr(
        output_preview,
        "get_pixelle_video_root_path",
        lambda: str(project_root),
    )

    store = output_preview._resolve_layout_preview_object_store(
        {"artifact_base_path": "output"}
    )

    assert store._root == project_root / "output"
    assert not (unrelated_cwd / "output").exists()


def test_build_single_text_overlay_uses_caption_contract_defaults_for_partial_style():
    html = output_preview._build_single_text_overlay(
        style={"font_size": 36},
        text="Caption",
        region=output_preview.TextStyleRegion(x=0, y=0, width=1280, height=720),
        scale_factor=1.0,
        prefix="caption",
    )

    assert "Caption" in html
    assert "color: #000000" in html
    assert 'font-family: "Noto Sans CJK SC", sans-serif' in html
    assert "-webkit-text-stroke" not in html
    assert "text-shadow:" not in html


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

    assert '.st-key-output_preview_media [data-testid="stVideo"]' in css
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
    assert '.st-key-output_video_preview [data-testid="stVideo"]' in css
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
        assert "render_scaled_video_preview(" in source, (
            f"{path.name} should use shared preview renderer"
        )


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


def test_build_single_generation_request_includes_series_visual_signature_controls():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
            "series_visual_signature_expression_mode": "explanatory_diagram",
            "series_visual_signature_structure_mode": "workflow",
            "series_visual_signature_participation_mode": "guide_explainer",
        },
        progress_callback=_progress,
        session_state={},
    )

    assert request["series_visual_signature_enabled"] is True
    assert request["series_visual_signature_asset_bible_id"] == "bible_demo"
    assert request["series_visual_signature_profile_id"] == "ip_main"
    assert request["series_visual_signature_expression_mode"] == "explanatory_diagram"
    assert request["series_visual_signature_structure_mode"] == "workflow"
    assert request["series_visual_signature_participation_mode"] == "guide_explainer"


def test_build_single_generation_request_includes_generation_world_hint():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "generation_world_hint": "古城清晨漫游，IP 是陪伴式向导。",
        },
        progress_callback=_progress,
        session_state={},
    )

    assert request["generation_world_hint"] == "古城清晨漫游，IP 是陪伴式向导。"


def test_single_generation_request_copies_article_concretization_options():
    def _progress(_event):
        return None

    article_options = {
        "article_concretization_enabled": True,
        "cognitive_anchor_kind": "judgment",
        "explanation_diagram_grammar": "single_explanation_image",
        "series_visual_signature_role": "silent_witness",
        "diagram_render_style": "clean_vector",
        "diagram_aspect_ratio": "vertical_9_16",
        "diagram_visible_text_policy": "approved_labels_only",
        "diagram_approved_labels": ["cash flow", "risk"],
        "diagram_user_intent_hint": "make the tradeoff concrete",
    }

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            **article_options,
        },
        progress_callback=_progress,
        session_state={},
    )

    for key, value in article_options.items():
        assert request[key] == value


def test_build_single_generation_request_does_not_forward_ip_profile_world_hint():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "ip_profile_world_hint": "frontend helper only",
        },
        progress_callback=_progress,
        session_state={},
    )

    assert "ip_profile_world_hint" not in request


def test_build_single_generation_request_drops_content_ip_non_formal_fields():
    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
            "generation_world_hint": "market morning, IP blends in as a guide",
            "generation_notes": "old UI field",
            "slot_preference_override": "prefer_main",
            "presence_strength": "strong",
            "ip_profile_world_hint": "helper only",
            "generation_world_hint_source": "ip_default",
        },
        progress_callback=lambda _event: None,
        session_state={},
    )

    assert request["generation_world_hint"] == "market morning, IP blends in as a guide"
    assert "generation_notes" not in request
    assert "slot_preference_override" not in request
    assert "presence_strength" not in request
    assert "ip_profile_world_hint" not in request
    assert "generation_world_hint_source" not in request


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


def test_build_single_generation_request_includes_template_display_policy():
    def _progress(_event):
        return None

    template_display = {"show_title": True, "show_signature": False}

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "template_display": template_display,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["template_display"] == template_display


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


def test_build_batch_shared_config_includes_series_visual_signature_controls():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
        }
    )

    assert shared_config["series_visual_signature_enabled"] is True
    assert shared_config["series_visual_signature_asset_bible_id"] == "bible_demo"
    assert shared_config["series_visual_signature_profile_id"] == "ip_main"


def test_build_batch_shared_config_includes_generation_world_hint():
    shared_config = output_preview.build_batch_shared_config(
        {
            "generation_world_hint": "古城清晨漫游，IP 是陪伴式向导。",
        }
    )

    assert shared_config["generation_world_hint"] == "古城清晨漫游，IP 是陪伴式向导。"


def test_batch_shared_config_copies_article_concretization_options():
    article_options = {
        "article_concretization_enabled": True,
        "cognitive_anchor_kind": "relationship",
        "explanation_diagram_grammar": "relationship_map",
        "series_visual_signature_role": "operator",
        "diagram_render_style": "editorial_diagram",
        "diagram_aspect_ratio": "landscape_16_9",
        "diagram_visible_text_policy": "source_text_only",
        "diagram_approved_labels": ["market", "margin"],
        "diagram_user_intent_hint": "show why the relationship matters",
    }

    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            **article_options,
        }
    )

    for key, value in article_options.items():
        assert shared_config[key] == value


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


def test_build_batch_shared_config_includes_template_display_policy():
    template_display = {"show_title": False, "show_signature": True}

    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "template_display": template_display,
        }
    )

    assert shared_config["template_display"] == template_display


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


def test_build_single_generation_request_includes_tts_duration_for_comfyui():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "tts_inference_mode": "comfyui",
            "tts_workflow": "selfhost/tts_omnivoice_clone_duration_bf16.json",
            "tts_duration": 8.0,
            "ref_audio": "temp/ref.wav",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["tts_duration"] == 8.0


def test_build_single_generation_request_rejects_ref_audio_required_workflow_without_voice():
    def _progress(_event):
        return None

    with pytest.raises(ValueError, match="requires a reference audio"):
        output_preview.build_single_generation_request(
            {
                "text": "demo",
                "mode": "generate",
                "tts_inference_mode": "comfyui",
                "tts_workflow": "selfhost/tts_omnivoice_longform_bf16.json",
            },
            progress_callback=_progress,
            session_state={"template_media_width": 1080, "template_media_height": 1920},
        )


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


def test_build_batch_shared_config_includes_tts_duration_for_comfyui():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "tts_inference_mode": "comfyui",
            "tts_workflow": "selfhost/tts_omnivoice_clone_duration_bf16.json",
            "tts_duration": 8.0,
            "ref_audio": "temp/ref.wav",
        }
    )

    assert shared_config["tts_duration"] == 8.0


def test_build_batch_shared_config_rejects_ref_audio_required_workflow_without_voice():
    with pytest.raises(ValueError, match="requires a reference audio"):
        output_preview.build_batch_shared_config(
            {
                "title_prefix": "Series",
                "tts_inference_mode": "comfyui",
                "tts_workflow": "selfhost/tts_omnivoice_longform_bf16.json",
            }
        )


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

    output_preview._render_layout_preview_workbench_section({"layered_template_spec": spec_payload})

    assert captured["list_recent"] == [5]
    assert captured["recent_presets"][0]["preset_id"] == "user:portrait_news"
    assert captured["mark_used"] == ["user:portrait_news"]
    assert output_preview.st.session_state["loaded_spec"] == spec_payload
    assert output_preview.st.session_state["selected_template_preset_id"] == "user:portrait_news"
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
    expected_size = GenerationSizeContract.from_params({"video_orientation": "portrait"})
    assert default_summary.canvas_width == expected_size.canvas_width
    assert default_summary.canvas_height == expected_size.canvas_height
    assert default_summary.media_width == expected_size.media_width
    assert default_summary.media_height == expected_size.media_height
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


def test_render_layout_preview_workbench_section_refresh_uses_local_object_store_by_default(
    monkeypatch,
    tmp_path,
):
    spec_payload = _layered_template_spec_payload(
        template_id="user:portrait_news",
        metadata={"source_kind": "user"},
    )
    captured = {"store": None, "request": None}

    class _FakeLocalObjectStore:
        def __init__(self, *, root, base_url):
            self.root = Path(root)
            self.base_url = base_url

    class _FakeLayeredTemplateService:
        def __init__(self, *, object_store=None):
            captured["store"] = object_store

        async def render_preview_frame(self, request):
            captured["request"] = request
            return SimpleNamespace(
                storage_key="artifacts/workspace_demo/preview.png",
                url="/api/files/artifacts/workspace_demo/preview.png",
                fingerprint="preview-fingerprint",
            )

    monkeypatch.setattr(output_preview, "FilesystemDevArtifactObjectStore", _FakeLocalObjectStore)
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
            "workspace_id": "workspace_demo",
            "artifact_base_path": str(tmp_path / "output"),
            "artifact_base_url": "/api/files",
        }
    )

    assert isinstance(captured["store"], _FakeLocalObjectStore)
    assert captured["store"].root == tmp_path / "output"
    assert captured["store"].base_url == "/api/files"
    assert captured["request"].workspace_id == "workspace_demo"
    assert output_preview.st.session_state["layout_preview_real_preview_frame"] == {
        "storage_key": "artifacts/workspace_demo/preview.png",
        "url": "/api/files/artifacts/workspace_demo/preview.png",
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


def test_render_layout_preview_workbench_section_deletes_recent_preset(monkeypatch):
    spec_payload = _layered_template_spec_payload()
    captured = {"deleted": [], "rerun": 0, "success": []}

    class _FakeRegistry:
        def list_recent(self, *, limit=5):
            return []

        def delete_recent(self, preset_id):
            captured["deleted"].append(preset_id)
            return True

    monkeypatch.setattr(output_preview, "TemplateRegistry", _FakeRegistry, raising=False)
    monkeypatch.setattr(
        output_preview,
        "render_layout_preview_workbench",
        lambda **_kwargs: {
            "action": "delete_recent_preset",
            "preset_id": "user:template_one",
        },
    )
    monkeypatch.setattr(output_preview, "_build_layout_preview_html", lambda _params: None)
    monkeypatch.setattr(
        output_preview,
        "st",
        SimpleNamespace(
            session_state={},
            rerun=lambda: captured.__setitem__("rerun", captured["rerun"] + 1),
            success=lambda message, **_kwargs: captured["success"].append(message),
            error=lambda message: (_ for _ in ()).throw(AssertionError(message)),
        ),
    )

    output_preview._render_layout_preview_workbench_section(
        {
            "layered_template_spec": spec_payload,
            "workspace_id": "workspace_demo",
        }
    )

    assert captured["deleted"] == ["user:template_one"]
    assert captured["success"] == ["已删除最近模板"]
    assert captured["rerun"] == 1


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


def test_save_layout_preview_template_clones_system_spec_as_user_preset(
    monkeypatch,
    tmp_path,
):
    spec_payload = _layered_template_spec_payload(
        template_id="system:1080x1920/image_default.html",
        template_name="Image Default",
        metadata={"source_kind": "legacy_html", "orientation": "portrait"},
    )
    preview_png = tmp_path / "preview.png"
    preview_png.write_bytes(b"png")
    repo_root = tmp_path / "template-presets"

    monkeypatch.setattr(
        output_preview,
        "_refresh_layout_preview_frame",
        lambda *_args, **_kwargs: {
            "storage_key": "artifacts/workspace_demo/layout-preview.png",
            "url": "/api/files/artifacts/workspace_demo/layout-preview.png",
            "fingerprint": "preview-fingerprint",
        },
    )
    monkeypatch.setattr(
        output_preview,
        "_resolve_layout_preview_thumbnail_source_path",
        lambda *_args, **_kwargs: preview_png,
    )
    monkeypatch.setattr(
        output_preview,
        "TemplateRegistry",
        lambda: SimpleNamespace(mark_used=lambda *_args, **_kwargs: None),
    )
    monkeypatch.setattr(output_preview, "st", SimpleNamespace(session_state={}))

    preset = output_preview.save_layered_template_design(
        {"template_presets_root": str(repo_root)},
        spec=output_preview._coerce_layered_template_spec(spec_payload),
    )

    assert preset.preset_id.startswith("user:image_default_")
    assert preset.spec.template_id == preset.preset_id
    assert preset.spec.metadata["source_kind"] == "user"
    assert preset.spec.metadata["source_template_id"] == "system:1080x1920/image_default.html"


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


def test_build_layout_preview_html_uses_default_frame_template_without_layered_spec(
    tmp_path, monkeypatch
):
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
            "media_width": 1280,
            "media_height": 720,
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
    assert captured["render_kwargs"]["media_width"] == 1280
    assert captured["render_kwargs"]["media_height"] == 720
    placeholder_uri = captured["render_kwargs"]["image"]
    assert placeholder_uri.startswith("data:image/svg+xml")
    placeholder_svg = unquote(placeholder_uri.split(",", 1)[1])
    assert 'viewBox="0 0 1280 720"' in placeholder_svg
    assert Path("resources/example.png").resolve().as_uri() not in placeholder_uri
    assert captured["render_kwargs"]["ext"]["media_layout_mode"] == "template"


def test_layout_preview_placeholder_uses_selected_landscape_media_geometry():
    html = output_preview._build_layout_preview_html(
        {
            "title": "横屏预览",
            "text": "等待真实素材",
            "frame_template": "1920x1080/image_landscape_minimal.html",
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 1280,
            "media_height": 720,
            "media_placement": {
                "basis": "canvas",
                "fit": "contain",
                "scale_percent": 100,
                "offset_x": 0,
                "offset_y": 0,
            },
        }
    )

    assert html is not None
    assert "--pixelle-media-display-width: 1920px" in html.html
    assert "--pixelle-media-display-height: 1080px" in html.html
    assert "--pixelle-media-left: 0px" in html.html
    assert "--pixelle-media-top: 0px" in html.html
    assert Path("resources/example.png").resolve().as_uri() not in html.html


def test_layout_preview_keeps_natural_geometry_for_real_square_media(tmp_path):
    media_path = tmp_path / "real-square.png"
    Image.new("RGB", (512, 512), "white").save(media_path)

    html = output_preview._build_layout_preview_html(
        {
            "title": "真实素材",
            "frame_template": "1920x1080/image_landscape_minimal.html",
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 1280,
            "media_height": 720,
            "layout_preview_media_path": str(media_path),
            "media_placement": {
                "basis": "canvas",
                "fit": "contain",
                "scale_percent": 100,
                "offset_x": 0,
                "offset_y": 0,
            },
        }
    )

    assert html is not None
    assert media_path.resolve().as_uri() in html.html
    assert "--pixelle-media-display-width: 1080px" in html.html
    assert "--pixelle-media-display-height: 1080px" in html.html
    assert "--pixelle-media-left: 420px" in html.html
    assert "--pixelle-media-top: 0px" in html.html


def _recording_slot_streamlit(events, *, session_state=None):
    class _FakeContext:
        def __enter__(self):
            events.append("slot_enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("slot_exit")
            return False

    class _FakeSlot:
        def empty(self):
            events.append("slot_clear")

        def container(self):
            return _FakeContext()

    class _FakeStreamlit:
        def __init__(self):
            self.session_state = dict(session_state or {})

        def empty(self):
            events.append("slot_create")
            return _FakeSlot()

    return _FakeStreamlit()


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
