import pytest

from pixelle_video.models.size_contract import (
    DEFAULT_MEDIA_SIZE,
    GenerationSizeContract,
    SizeSpec,
    resolve_canvas_size,
    resolve_media_size,
)


def test_default_generation_size_contract_keeps_video_and_media_independent():
    contract = GenerationSizeContract.default()

    assert (contract.canvas_width, contract.canvas_height) == (1280, 720)
    assert (contract.media_width, contract.media_height) == (768, 768)
    assert contract.video_orientation == "landscape"
    assert contract.video_resolution_preset == "1k"
    assert contract.media_orientation == "square"
    assert contract.media_resolution_preset == "768"
    assert contract.sync_media_size_to_canvas is False


@pytest.mark.parametrize(
    ("orientation", "preset", "expected"),
    [
        ("landscape", "1k", SizeSpec(1280, 720)),
        ("landscape", "2k", SizeSpec(1920, 1080)),
        ("landscape", "4k", SizeSpec(3840, 2160)),
        ("portrait", "1k", SizeSpec(720, 1280)),
        ("portrait", "2k", SizeSpec(1080, 1920)),
        ("portrait", "4k", SizeSpec(2160, 3840)),
        ("square", "1k", SizeSpec(1024, 1024)),
        ("square", "2k", SizeSpec(2048, 2048)),
        ("square", "4k", SizeSpec(4096, 4096)),
    ],
)
def test_resolve_canvas_size_for_orientation_presets(orientation, preset, expected):
    assert resolve_canvas_size(orientation, preset) == expected


@pytest.mark.parametrize(
    ("orientation", "preset", "expected"),
    [
        ("landscape", "1k", SizeSpec(1280, 720)),
        ("landscape", "2k", SizeSpec(1920, 1080)),
        ("landscape", "4k", SizeSpec(3840, 2160)),
        ("portrait", "1k", SizeSpec(720, 1280)),
        ("portrait", "2k", SizeSpec(1080, 1920)),
        ("portrait", "4k", SizeSpec(2160, 3840)),
        ("square", "768", SizeSpec(768, 768)),
        ("square", "1k", SizeSpec(1024, 1024)),
        ("square", "2k", SizeSpec(2048, 2048)),
        ("square", "4k", SizeSpec(4096, 4096)),
    ],
)
def test_resolve_media_size_for_independent_image_presets(orientation, preset, expected):
    assert resolve_media_size(orientation, preset) == expected


def test_media_size_defaults_to_768_square_when_sync_is_off():
    contract = GenerationSizeContract.from_params(
        {
            "video_orientation": "portrait",
            "video_resolution_preset": "2k",
            "sync_media_size_to_canvas": False,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (1080, 1920)
    assert (contract.media_width, contract.media_height) == DEFAULT_MEDIA_SIZE.as_tuple()
    assert contract.media_orientation == "square"
    assert contract.media_resolution_preset == "768"


def test_media_size_preset_is_independent_from_video_canvas_when_sync_is_off():
    contract = GenerationSizeContract.from_params(
        {
            "video_orientation": "portrait",
            "video_resolution_preset": "2k",
            "media_orientation": "landscape",
            "media_resolution_preset": "4k",
            "sync_media_size_to_canvas": False,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (1080, 1920)
    assert (contract.media_width, contract.media_height) == (3840, 2160)
    assert contract.media_orientation == "landscape"
    assert contract.media_resolution_preset == "4k"


def test_media_size_syncs_to_canvas_when_enabled():
    contract = GenerationSizeContract.from_params(
        {
            "video_orientation": "landscape",
            "video_resolution_preset": "4k",
            "sync_media_size_to_canvas": True,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (3840, 2160)
    assert (contract.media_width, contract.media_height) == (3840, 2160)
    assert contract.media_orientation == "square"
    assert contract.media_resolution_preset == "768"


def test_explicit_canvas_and_media_dimensions_take_precedence():
    contract = GenerationSizeContract.from_params(
        {
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 1024,
            "media_height": 1024,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (1280, 720)
    assert (contract.media_width, contract.media_height) == (1024, 1024)


def test_legacy_media_only_request_uses_media_as_canvas():
    contract = GenerationSizeContract.from_params(
        {
            "media_width": 1080,
            "media_height": 1920,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (1080, 1920)
    assert (contract.media_width, contract.media_height) == (1080, 1920)


def test_missing_dimensions_uses_new_defaults():
    contract = GenerationSizeContract.from_params({})

    assert (contract.canvas_width, contract.canvas_height) == (1280, 720)
    assert (contract.media_width, contract.media_height) == (768, 768)


@pytest.mark.parametrize(
    "params",
    [
        {"video_orientation": "circle"},
        {"video_resolution_preset": "8k"},
        {"media_orientation": "circle"},
        {"media_resolution_preset": "8k"},
        {"media_orientation": "landscape", "media_resolution_preset": "768"},
        {"canvas_width": 0, "canvas_height": 720},
        {"media_width": 768, "media_height": -1},
    ],
)
def test_invalid_size_contract_inputs_raise_value_error(params):
    with pytest.raises(ValueError):
        GenerationSizeContract.from_params(params)
