from web.components import style_config
from web.utils import preview_media as preview_media_module
from web.utils.preview_media import PreviewMediaData, load_preview_media

PNG_BYTES = b"\x89PNG\r\n\x1a\npreview"
VIDEO_BYTES = b"\x00\x00\x00\x18ftypisompreview"


def test_load_preview_media_reads_local_image_file(tmp_path):
    preview_path = tmp_path / "preview.png"
    preview_path.write_bytes(PNG_BYTES)

    preview_media = load_preview_media(str(preview_path), "image")

    assert preview_media.data == PNG_BYTES
    assert preview_media.format is None


def test_load_preview_media_downloads_http_video_and_detects_format(monkeypatch):
    preview_url = "http://127.0.0.1:8000/view?filename=test.mp4&type=output"

    async def fake_materialize(source, target, **kwargs):
        assert source == preview_url
        assert kwargs["media_type"] == "video"
        assert kwargs["request_timeout_seconds"] == 10.0
        target.write_bytes(VIDEO_BYTES)
        return target

    monkeypatch.setattr(preview_media_module, "materialize_media_source", fake_materialize)

    preview_media = load_preview_media(preview_url, "video")

    assert preview_media.data == VIDEO_BYTES
    assert preview_media.format == "video/mp4"


def test_render_generated_style_preview_uses_image_bytes(monkeypatch):
    captured = {}

    def fake_load_preview_media(path, media_type):
        captured["load"] = (path, media_type)
        return PreviewMediaData(data=PNG_BYTES)

    class FakeStreamlit:
        def image(self, data, *, caption, width):
            captured["image"] = (data, caption, width)

        def video(self, *_args, **_kwargs):
            raise AssertionError("video should not be called for image preview")

    monkeypatch.setattr(style_config, "load_preview_media", fake_load_preview_media)
    monkeypatch.setattr(style_config, "st", FakeStreamlit())
    monkeypatch.setattr(style_config, "tr", lambda key: {"style.preview_caption": "Style Preview"}[key])

    style_config.render_generated_style_preview("http://127.0.0.1:8000/view?filename=test.png", "image")

    assert captured["load"] == ("http://127.0.0.1:8000/view?filename=test.png", "image")
    assert captured["image"] == (PNG_BYTES, "Style Preview", "stretch")


def test_render_generated_style_preview_uses_video_bytes_and_format(monkeypatch):
    captured = {}

    def fake_load_preview_media(path, media_type):
        captured["load"] = (path, media_type)
        return PreviewMediaData(data=VIDEO_BYTES, format="video/mp4")

    class FakeStreamlit:
        def image(self, *_args, **_kwargs):
            raise AssertionError("image should not be called for video preview")

        def video(self, data, *, format):
            captured["video"] = (data, format)

    monkeypatch.setattr(style_config, "load_preview_media", fake_load_preview_media)
    monkeypatch.setattr(style_config, "st", FakeStreamlit())

    style_config.render_generated_style_preview("http://127.0.0.1:8000/view?filename=test.mp4", "video")

    assert captured["load"] == ("http://127.0.0.1:8000/view?filename=test.mp4", "video")
    assert captured["video"] == (VIDEO_BYTES, "video/mp4")


def test_render_template_gallery_preview_falls_back_when_image_raises_memory_error(monkeypatch):
    captured = {}

    class FakeStreamlit:
        def image(self, *_args, **_kwargs):
            raise MemoryError("preview too large")

        def markdown(self, html, *, unsafe_allow_html):
            captured["markdown"] = (html, unsafe_allow_html)

    monkeypatch.setattr(style_config, "st", FakeStreamlit())

    style_config._render_template_gallery_preview(
        "docs/images/1080x1920/image_default.jpg",
        "image_default",
    )

    assert "image_default" in captured["markdown"][0]
    assert captured["markdown"][1] is True
