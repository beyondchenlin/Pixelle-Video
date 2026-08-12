import pytest

import pixelle_video.services.video as video_module
from pixelle_video.services.video import VideoService


def _font_resolver_cls():
    from pixelle_video.services.font_resolver import FontResolver

    return FontResolver


def test_font_resolver_prefers_existing_font_file_parent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fallback_dir = tmp_path / "fonts"
    fallback_dir.mkdir()
    font_dir = tmp_path / "custom fonts"
    font_dir.mkdir()
    font_file = font_dir / "Title Font.ttf"
    font_file.write_bytes(b"font")

    result = _font_resolver_cls()().resolve_fontsdir(font_file)

    assert result == font_dir


def test_font_resolver_default_is_independent_from_process_working_directory(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "font").mkdir()
    (tmp_path / "resource" / "fonts").mkdir(parents=True)

    result = _font_resolver_cls()().resolve_fontsdir()

    assert result is not None
    expected = (
        _font_resolver_cls().APPLICATION_ROOT
        / "resources"
        / "hyperframes"
        / "runtime"
        / "fonts"
        / "assets"
    )
    assert result.resolve() == expected.resolve()


def test_font_resolver_returns_none_without_explicit_candidate(tmp_path):
    assert (
        _font_resolver_cls()(candidate_dirs=[tmp_path / "missing"]).resolve_fontsdir()
        is None
    )


def test_font_resolver_prefers_bundled_assets_over_unmanaged_root_fonts(
    tmp_path,
    monkeypatch,
):
    bundled = tmp_path / "resources" / "hyperframes" / "runtime" / "fonts" / "assets"
    unmanaged = tmp_path / "fonts"
    bundled.mkdir(parents=True)
    unmanaged.mkdir()
    monkeypatch.setattr(_font_resolver_cls(), "APPLICATION_ROOT", tmp_path)

    assert _font_resolver_cls()().resolve_fontsdir() == bundled.resolve()


def test_font_resolver_uses_explicit_candidate_directory(tmp_path):
    candidate = tmp_path / "fonts"
    candidate.mkdir()

    assert _font_resolver_cls()(candidate_dirs=[candidate]).resolve_fontsdir() == candidate


def test_build_ass_filter_includes_ass_file_and_fontsdir(tmp_path):
    ass_file = tmp_path / "caption clips" / "master title.ass"
    fonts_dir = tmp_path / "caption fonts"
    ass_file.parent.mkdir()
    fonts_dir.mkdir()

    expression = VideoService()._build_ass_filter(ass_file, fonts_dir=fonts_dir)

    assert expression.startswith("ass=")
    assert "fontsdir=" in expression
    assert "master title.ass" in expression
    assert "caption fonts" in expression
    assert "subtitles=" not in expression


def test_build_ass_filter_omits_fontsdir_when_not_provided(tmp_path):
    ass_file = tmp_path / "master.ass"

    expression = VideoService()._build_ass_filter(ass_file)

    assert expression.startswith("ass=")
    assert "fontsdir=" not in expression
    assert "master.ass" in expression


def test_build_ass_filter_escapes_windows_drive_and_preserves_spaces():
    expression = VideoService()._build_ass_filter(r"C:\caption clips\master.ass")

    assert r"C\:" in expression
    assert r"C\\:" not in expression
    assert "caption clips" in expression
    assert "master.ass" in expression


def test_build_ass_filter_rejects_explicit_missing_fontsdir(tmp_path):
    ass_file = tmp_path / "master.ass"

    with pytest.raises(ValueError, match="fonts_dir"):
        VideoService()._build_ass_filter(ass_file, fonts_dir=tmp_path / "missing")


class _FakeOutput:
    def __init__(self, calls):
        self._calls = calls

    def overwrite_output(self):
        self._calls["overwrite_output"] = True
        return self

    def run(self, **kwargs):
        self._calls["run_kwargs"] = kwargs


class _FakeInput:
    def __init__(self, path, calls):
        self._path = path
        self._calls = calls

    def output(self, output_path, **kwargs):
        self._calls["input_path"] = self._path
        self._calls["output_path"] = output_path
        self._calls["output_kwargs"] = kwargs
        return _FakeOutput(self._calls)


def test_burn_ass_subtitles_uses_ass_filter_and_resolved_default_fontsdir(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    input_video = tmp_path / "input.mp4"
    ass_file = tmp_path / "master.ass"
    output = tmp_path / "out" / "final.mp4"
    fonts_dir = tmp_path / "fonts"
    input_video.write_bytes(b"video")
    ass_file.write_text("", encoding="utf-8")
    fonts_dir.mkdir()
    calls = {}

    def fake_input(path):
        return _FakeInput(path, calls)

    monkeypatch.setattr(video_module.ffmpeg, "input", fake_input)

    result = VideoService().burn_ass_subtitles(
        str(input_video), str(ass_file), str(output)
    )

    assert result == str(output.resolve())
    assert calls["input_path"] == str(input_video.resolve())
    assert calls["output_path"] == str(output.resolve())
    assert calls["output_kwargs"]["acodec"] == "copy"
    assert "c_a" not in calls["output_kwargs"]
    assert calls["run_kwargs"] == {
        "capture_stdout": True,
        "capture_stderr": True,
    }
    vf = calls["output_kwargs"]["vf"]
    assert vf.startswith("ass=")
    assert "fontsdir=" in vf
    assert "master.ass" in vf
    assert "fonts" in vf
    assert "subtitles=" not in vf


def test_burn_ass_subtitles_accepts_explicit_fontsdir(tmp_path, monkeypatch):
    input_video = tmp_path / "input.mp4"
    ass_file = tmp_path / "master.ass"
    output = tmp_path / "out" / "final.mp4"
    fonts_dir = tmp_path / "explicit fonts"
    input_video.write_bytes(b"video")
    ass_file.write_text("", encoding="utf-8")
    fonts_dir.mkdir()
    calls = {}

    def fake_input(path):
        return _FakeInput(path, calls)

    monkeypatch.setattr(video_module.ffmpeg, "input", fake_input)

    VideoService().burn_ass_subtitles(
        str(input_video),
        str(ass_file),
        str(output),
        fonts_dir=fonts_dir,
    )

    vf = calls["output_kwargs"]["vf"]
    assert "fontsdir=" in vf
    assert "explicit fonts" in vf


def test_burn_ass_subtitles_returns_original_output_string(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    input_video = tmp_path / "input.mp4"
    ass_file = tmp_path / "master.ass"
    output = "relative out/final.mp4"
    input_video.write_bytes(b"video")
    ass_file.write_text("", encoding="utf-8")
    calls = {}

    def fake_input(path):
        return _FakeInput(path, calls)

    monkeypatch.setattr(video_module.ffmpeg, "input", fake_input)

    result = VideoService().burn_ass_subtitles(
        str(input_video), str(ass_file), output
    )

    assert result == output


def test_burn_ass_subtitles_rejects_explicit_missing_fontsdir(tmp_path):
    input_video = tmp_path / "input.mp4"
    ass_file = tmp_path / "master.ass"
    input_video.write_bytes(b"video")
    ass_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="fonts_dir"):
        VideoService().burn_ass_subtitles(
            str(input_video),
            str(ass_file),
            str(tmp_path / "out.mp4"),
            fonts_dir=tmp_path / "missing",
        )


def test_burn_ass_subtitles_rejects_explicit_file_as_fontsdir(tmp_path):
    input_video = tmp_path / "input.mp4"
    ass_file = tmp_path / "master.ass"
    fonts_file = tmp_path / "not-a-dir.ttf"
    input_video.write_bytes(b"video")
    ass_file.write_text("", encoding="utf-8")
    fonts_file.write_bytes(b"font")

    with pytest.raises(ValueError, match="fonts_dir"):
        VideoService().burn_ass_subtitles(
            str(input_video),
            str(ass_file),
            str(tmp_path / "out.mp4"),
            fonts_dir=fonts_file,
        )


def test_burn_ass_subtitles_rejects_explicit_missing_font_file(tmp_path):
    input_video = tmp_path / "input.mp4"
    ass_file = tmp_path / "master.ass"
    input_video.write_bytes(b"video")
    ass_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="font_file"):
        VideoService().burn_ass_subtitles(
            str(input_video),
            str(ass_file),
            str(tmp_path / "out.mp4"),
            font_file=tmp_path / "missing.ttf",
        )


def test_ffmpeg_python_args_use_valid_audio_copy_option(tmp_path):
    ass_file = tmp_path / "master.ass"
    args = (
        video_module.ffmpeg.input(str(tmp_path / "input.mp4"))
        .output(
            str(tmp_path / "out.mp4"),
            vf=VideoService()._build_ass_filter(ass_file),
            acodec="copy",
        )
        .get_args()
    )

    assert "-c_a" not in args
    assert args[args.index("-acodec") + 1] == "copy"
