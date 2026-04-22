from pathlib import Path

from web.components import output_preview

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_video_preview_css_overrides_streamlit_inline_width():
    css = output_preview.build_video_preview_css("output_preview_media", width="50%")

    assert ".st-key-output_preview_media [data-testid=\"stVideo\"]" in css
    assert "width: 50% !important;" in css
    assert "max-width: 100% !important;" in css
    assert "margin-inline: auto;" in css
    assert "display: block;" in css


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


def test_build_single_generation_request_includes_render_backend():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "n_scenes": 3,
            "split_mode": "paragraph",
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
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "frame_overrides": [
                {
                    "scene_id": "scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["world_preset_id"] == "neutral_knowledge_storyboard"
    assert request["shot_preset_id"] == "balanced_explainer"
    assert request["consistency_strength"] == "strong"
    assert request["content_mode"] == "concept_explainer"
    assert request["role_strategy"] == "auto"
    assert request["role_locking_strength"] == "strong"
    assert request["shot_strategy"] == "strict"
    assert request["frame_overrides"] == [
        {
            "scene_id": "scene-1",
            "locked_fields": ["shot_type"],
            "shot_type": "medium_shot",
        }
    ]


def test_build_batch_shared_config_includes_render_backend():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "n_scenes": 5,
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


def test_build_batch_shared_config_includes_storyboard_controls_and_frame_overrides():
    shared_config = output_preview.build_batch_shared_config(
        {
            "n_scenes": 5,
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "frame_overrides": [
                {
                    "scene_id": "scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        }
    )

    assert shared_config["world_preset_id"] == "neutral_knowledge_storyboard"
    assert shared_config["shot_preset_id"] == "balanced_explainer"
    assert shared_config["consistency_strength"] == "strong"
    assert shared_config["content_mode"] == "concept_explainer"
    assert shared_config["role_strategy"] == "auto"
    assert shared_config["role_locking_strength"] == "strong"
    assert shared_config["shot_strategy"] == "strict"
    assert shared_config["frame_overrides"] == [
        {
            "scene_id": "scene-1",
            "locked_fields": ["shot_type"],
            "shot_type": "medium_shot",
        }
    ]


def test_build_single_generation_request_includes_tts_speed_for_comfyui():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "n_scenes": 3,
            "split_mode": "paragraph",
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
            "n_scenes": 5,
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
