from __future__ import annotations

import hashlib
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from web.components import output_preview, style_config


class _FakeUpload:
    def __init__(self, *, name: str, content: bytes) -> None:
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = {}
        self.calls: list[str] = []

    def toggle(self, *_args, **_kwargs):
        self.calls.append("toggle")
        return False

    def file_uploader(self, *_args, **_kwargs):
        self.calls.append("file_uploader")
        return None

    def selectbox(self, _label, options, *, index=0, **_kwargs):
        self.calls.append("selectbox")
        return tuple(options)[index]

    def error(self, *_args, **_kwargs):
        self.calls.append("error")

    def info(self, *_args, **_kwargs):
        self.calls.append("info")

    def image(self, *_args, **_kwargs):
        self.calls.append("image")


class _FakeStreamlitWithUpload(_FakeStreamlit):
    def __init__(self, upload) -> None:
        super().__init__()
        self._upload = upload

    def file_uploader(self, *_args, **_kwargs):
        self.calls.append("file_uploader")
        self.upload_key = _kwargs.get("key")
        return self._upload


def _image_bytes(image_format: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buffer, format=image_format)
    return buffer.getvalue()


def test_render_reference_image_controls_hides_when_web_flag_is_off(monkeypatch):
    def _fail_render_section(*_args, **_kwargs):
        raise AssertionError("reference-image UI should stay hidden")

    monkeypatch.setattr(
        style_config.config_manager,
        "get",
        lambda key, default=None: {"enabled": True, "web_ui_enabled": False} if key == "reference_image" else default,
    )
    monkeypatch.setattr(
        style_config,
        "render_middle_column_collapsible_section",
        _fail_render_section,
    )

    assert style_config.render_reference_image_controls() == {}


def test_render_reference_image_controls_renders_when_backend_default_is_off(monkeypatch):
    fake_st = _FakeStreamlit()

    @contextmanager
    def _section(*_args, **_kwargs):
        yield

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config.config_manager,
        "get",
        lambda key, default=None: {"enabled": False, "web_ui_enabled": True} if key == "reference_image" else default,
    )
    monkeypatch.setattr(style_config, "render_middle_column_collapsible_section", _section)

    assert style_config.render_reference_image_controls() == {}
    assert "toggle" in fake_st.calls
    assert "file_uploader" in fake_st.calls


def test_visual_anchor_requires_and_forces_reference_image_binding(tmp_path, monkeypatch):
    upload = _FakeUpload(name="dog.png", content=_image_bytes("PNG"))
    fake_st = _FakeStreamlitWithUpload(upload)
    section_args = {}

    @contextmanager
    def _section(*_args, **kwargs):
        section_args.update(kwargs)
        yield

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config.config_manager,
        "get",
        lambda key, default=None: {"web_ui_enabled": True} if key == "reference_image" else default,
    )
    monkeypatch.setattr(style_config, "render_middle_column_collapsible_section", _section)
    monkeypatch.setattr(
        style_config,
        "get_runtime_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )

    result = style_config.render_reference_image_controls(
        required_for_visual_anchor=True,
        visual_anchor_identity_key="dog:dog_1",
    )

    assert section_args["expanded"] is True
    assert result["reference_image_enabled"] is True
    assert result["reference_image_analysis_mode"] == "off"
    assert result["reference_image_workflow_injection_mode"] == "required"
    assert result["reference_image_profile_merge_mode"] == "supplement"
    assert Path(result["ref_image"]).is_file()
    assert fake_st.upload_key.startswith("reference_image_web_upload_")
    assert fake_st.upload_key != "reference_image_web_upload"
    assert "info" in fake_st.calls
    assert "image" in fake_st.calls


def test_reference_image_allowed_extensions_filters_backend_unsupported_types():
    assert style_config._reference_image_allowed_extensions(
        {"allowed_extensions": [".png", "bmp", ".jpg", ".tiff", ".png"]}
    ) == [".png", ".jpg"]


def test_reference_image_allowed_extensions_does_not_widen_unsupported_config():
    assert style_config._reference_image_allowed_extensions(
        {"allowed_extensions": [".bmp", ".tiff"]}
    ) == []


def test_persist_web_reference_image_upload_uses_hash_name(tmp_path, monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config,
        "get_runtime_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    content = _image_bytes("PNG")

    path = Path(
        style_config._persist_web_reference_image_upload(
            _FakeUpload(name="../reference.png", content=content),
            allowed_extensions=[".png"],
            max_upload_size_mb=1,
        )
    )

    assert path.name == f"{hashlib.sha256(content).hexdigest()[:16]}.png"
    assert path.read_bytes() == content
    assert path.is_relative_to(tmp_path)
    assert fake_st.session_state["reference_image_web_upload_session_id"]


def test_persist_web_reference_image_upload_rejects_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(style_config, "st", _FakeStreamlit())
    monkeypatch.setattr(
        style_config,
        "get_runtime_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )

    with pytest.raises(ValueError, match="Unsupported|不支持"):
        style_config._persist_web_reference_image_upload(
            _FakeUpload(name="reference.bmp", content=b"fake"),
            allowed_extensions=[".png"],
            max_upload_size_mb=1,
        )


def test_persist_web_reference_image_upload_rejects_disguised_image(tmp_path, monkeypatch):
    monkeypatch.setattr(style_config, "st", _FakeStreamlit())
    monkeypatch.setattr(
        style_config,
        "get_runtime_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )

    with pytest.raises(ValueError, match="valid image|有效图片"):
        style_config._persist_web_reference_image_upload(
            _FakeUpload(name="reference.png", content=_image_bytes("BMP")),
            allowed_extensions=[".png"],
            max_upload_size_mb=1,
        )


def test_persist_web_reference_image_upload_rejects_oversize(tmp_path, monkeypatch):
    monkeypatch.setattr(style_config, "st", _FakeStreamlit())
    monkeypatch.setattr(
        style_config,
        "get_runtime_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )

    with pytest.raises(ValueError, match="exceeds|超过"):
        style_config._persist_web_reference_image_upload(
            _FakeUpload(name="reference.png", content=b"x" * (1024 * 1024 + 1)),
            allowed_extensions=[".png"],
            max_upload_size_mb=1,
        )


def test_build_single_generation_request_includes_reference_image_options(tmp_path):
    ref_image = tmp_path / "reference.png"
    ref_image.write_bytes(b"fake")

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "ref_image": str(ref_image),
            "reference_image_analysis_mode": "auto",
            "reference_image_workflow_injection_mode": "off",
            "reference_image_profile_merge_mode": "supplement",
        },
        progress_callback=lambda _event: None,
        session_state={},
    )

    assert request["ref_image"] == str(ref_image)
    assert request["reference_image_enabled"] is True
    assert request["reference_image_analysis_mode"] == "auto"
    assert request["reference_image_workflow_injection_mode"] == "off"
    assert request["reference_image_profile_merge_mode"] == "supplement"


def test_build_batch_shared_config_includes_reference_image_options(tmp_path):
    ref_image = tmp_path / "reference.png"
    ref_image.write_bytes(b"fake")

    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "ref_image": str(ref_image),
            "reference_image_analysis_mode": "auto",
            "reference_image_workflow_injection_mode": "off",
            "reference_image_profile_merge_mode": "supplement",
        }
    )

    assert shared_config["ref_image"] == str(ref_image)
    assert shared_config["reference_image_enabled"] is True
    assert shared_config["reference_image_analysis_mode"] == "auto"
    assert shared_config["reference_image_workflow_injection_mode"] == "off"
    assert shared_config["reference_image_profile_merge_mode"] == "supplement"
