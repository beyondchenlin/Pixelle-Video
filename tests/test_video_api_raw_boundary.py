from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.routers.video import build_video_generation_params, validate_video_tts_contract
from api.schemas.video import VideoGenerateRequest
from api.schemas.video_internal import VideoGenerateInternalRequest
from pixelle_video.config.prompt_prefix_library import image_prompt_prefix_revision
from pixelle_video.config.workflow_defaults import DEFAULT_TTS_WORKFLOW
from pixelle_video.services.resource_resolver import ResolvedResource, StaticResourceResolver
from pixelle_video.utils.template_util import DEFAULT_IMAGE_TEMPLATE


def test_public_video_request_accepts_resource_ids():
    request = VideoGenerateRequest(
        text="demo",
        style_id="comic_noir",
        template_id="portrait_default",
        voice_id="voice_cn",
        bgm_id="soft_bgm",
        workflow_preset_id="z_image_fast",
    )

    assert request.style_id == "comic_noir"
    assert request.template_id == "portrait_default"
    assert request.voice_id == "voice_cn"
    assert request.bgm_id == "soft_bgm"
    assert request.workflow_preset_id == "z_image_fast"


@pytest.mark.parametrize(
    "raw_field, raw_value",
    [
        ("prompt_prefix", "arbitrary cinematic noir prefix"),
        ("media_workflow", "selfhost/image_z_image_turbo_gguf.json"),
        ("tts_workflow", "selfhost/tts_edge.json"),
        ("frame_template", DEFAULT_IMAGE_TEMPLATE),
        ("bgm_path", r"D:\music\bgm.mp3"),
        ("ref_audio", r"D:\voice\sample.wav"),
        ("image_style_id", "builtin-flat-style"),
        ("image_style_revision", "a" * 64),
    ],
)
def test_public_video_request_rejects_raw_generation_controls(raw_field: str, raw_value: str):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", **{raw_field: raw_value})


@pytest.mark.parametrize(
    "resource_field, unsafe_value",
    [
        ("style_id", "https://provider.example/style"),
        ("style_id", " cinematic"),
        ("style_id", ""),
        ("template_id", "../image_default"),
        ("voice_id", "voices/cn.wav"),
        ("bgm_id", r"C:\music\bgm.mp3"),
        ("workflow_preset_id", "selfhost/image_z_image_turbo_gguf.json"),
        ("tts_workflow_preset_id", "selfhost/tts_omnivoice_clone_duration_bf16.json"),
    ],
)
def test_public_video_request_rejects_path_like_resource_ids(
    resource_field: str,
    unsafe_value: str,
):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", **{resource_field: unsafe_value})


def test_internal_video_request_keeps_raw_debug_controls():
    request = VideoGenerateInternalRequest(
        text="demo",
        prompt_prefix="arbitrary cinematic noir prefix",
        media_workflow="selfhost/image_z_image_turbo_gguf.json",
        tts_workflow="selfhost/tts_edge.json",
        frame_template=DEFAULT_IMAGE_TEMPLATE,
        bgm_path=r"D:\music\bgm.mp3",
        ref_audio=r"D:\voice\sample.wav",
        ref_audio_text="reference transcript",
    )

    assert request.prompt_prefix == "arbitrary cinematic noir prefix"
    assert request.media_workflow == "selfhost/image_z_image_turbo_gguf.json"
    assert request.tts_workflow == "selfhost/tts_edge.json"
    assert request.frame_template == DEFAULT_IMAGE_TEMPLATE
    assert request.bgm_path == r"D:\music\bgm.mp3"
    assert request.ref_audio == r"D:\voice\sample.wav"
    assert request.ref_audio_text == "reference transcript"


def test_internal_video_request_keeps_versioned_image_style_selection():
    revision = image_prompt_prefix_revision("flat illustration style")

    request = VideoGenerateInternalRequest(
        text="demo",
        image_style_id="builtin-flat-style",
        image_style_revision=revision,
    )

    assert request.image_style_id == "builtin-flat-style"
    assert request.image_style_revision == revision


@pytest.mark.parametrize(
    "style_fields",
    [
        {"image_style_id": "builtin-flat-style"},
        {"image_style_revision": "a" * 64},
        {
            "image_style_id": "../unsafe-style",
            "image_style_revision": "a" * 64,
        },
        {
            "image_style_id": "builtin-flat-style",
            "image_style_revision": "not-a-revision",
        },
        {
            "prompt_prefix": "raw style",
            "image_style_id": "builtin-flat-style",
            "image_style_revision": "a" * 64,
        },
    ],
)
def test_internal_video_request_rejects_invalid_image_style_contract(style_fields):
    with pytest.raises(ValidationError):
        VideoGenerateInternalRequest(text="demo", **style_fields)


def test_public_video_generation_params_resolve_resource_ids():
    resolver = StaticResourceResolver(
        styles={"comic_noir": "cinematic noir comic style"},
        templates={"portrait_default": DEFAULT_IMAGE_TEMPLATE},
        voices={"voice_cn": "zh-CN-XiaoxiaoNeural"},
        bgms={"soft_bgm": "bgm/soft.mp3"},
        workflow_presets={"z_image_fast": "selfhost/image_z_image_turbo_gguf.json"},
        tts_workflow_presets={
            "omnivoice_duration": "selfhost/tts_omnivoice_clone_duration_bf16.json"
        },
    )
    request = VideoGenerateRequest(
        text="demo",
        style_id="comic_noir",
        template_id="portrait_default",
        voice_id="voice_cn",
        bgm_id="soft_bgm",
        workflow_preset_id="z_image_fast",
        tts_workflow_preset_id="omnivoice_duration",
    )

    params = build_video_generation_params(
        request,
        request_id="req-1",
        resource_resolver=resolver,
    )

    assert params["prompt_prefix"] == "cinematic noir comic style"
    assert params["frame_template"] == DEFAULT_IMAGE_TEMPLATE
    assert params["voice_id"] == "zh-CN-XiaoxiaoNeural"
    assert params["bgm_path"] == "bgm/soft.mp3"
    assert params["media_workflow"] == "selfhost/image_z_image_turbo_gguf.json"
    assert params["tts_workflow"] == "selfhost/tts_omnivoice_clone_duration_bf16.json"
    assert "style_id" not in params
    assert "template_id" not in params
    assert "workflow_preset_id" not in params
    assert "tts_workflow_preset_id" not in params


def test_public_video_generation_contract_accepts_edge_voice_id_resource():
    resolver = StaticResourceResolver(
        voices={"voice_cn": "zh-CN-XiaoxiaoNeural"},
    )
    params = build_video_generation_params(
        VideoGenerateRequest(text="demo", voice_id="voice_cn"),
        request_id="req-edge-voice",
        resource_resolver=resolver,
    )

    assert params["voice_id"] == "zh-CN-XiaoxiaoNeural"
    validate_video_tts_contract(params)


def test_public_video_generation_params_resolve_omnivoice_voice_metadata():
    resolver = StaticResourceResolver(
        voices={
            "bange": ResolvedResource(
                resource_id="bange",
                resolved_value="reference_audio/omnivoice/bange.wav",
                metadata={
                    "tts_workflow": "selfhost/tts_omnivoice_longform_bf16.json",
                    "ref_audio": "reference_audio/omnivoice/bange.wav",
                    "ref_audio_text": "大家好，这是参考音频文本。",
                },
            )
        },
    )
    request = VideoGenerateRequest(text="demo", voice_id="bange")

    params = build_video_generation_params(
        request,
        request_id="req-omnivoice",
        resource_resolver=resolver,
    )

    assert params["tts_workflow"] == "selfhost/tts_omnivoice_longform_bf16.json"
    assert params["ref_audio"] == "reference_audio/omnivoice/bange.wav"
    assert params["ref_audio_text"] == "大家好，这是参考音频文本。"
    assert "voice_id" not in params


def test_public_video_generation_params_copy_tts_duration():
    request = VideoGenerateRequest(text="demo", tts_duration=8.0)

    params = build_video_generation_params(request, request_id="req-duration")

    assert params["tts_duration"] == 8.0


def test_public_video_generation_contract_rejects_default_omnivoice_without_voice():
    params = build_video_generation_params(
        VideoGenerateRequest(text="demo"),
        request_id="req-missing-voice",
    )

    with pytest.raises(ValueError, match="requires a reference audio"):
        validate_video_tts_contract(params)


def test_public_video_generation_contract_accepts_omnivoice_voice_metadata():
    resolver = StaticResourceResolver(
        voices={
            "bange": ResolvedResource(
                resource_id="bange",
                resolved_value="reference_audio/omnivoice/bange.wav",
                metadata={
                    "tts_workflow": DEFAULT_TTS_WORKFLOW,
                    "ref_audio": "reference_audio/omnivoice/bange.wav",
                    "ref_audio_text": "大家好，这是参考音频文本。",
                },
            )
        },
    )
    params = build_video_generation_params(
        VideoGenerateRequest(text="demo", voice_id="bange"),
        request_id="req-voice",
        resource_resolver=resolver,
    )

    validate_video_tts_contract(params)
