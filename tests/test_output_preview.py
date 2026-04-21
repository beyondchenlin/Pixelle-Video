from web.components import output_preview


def test_render_scaled_video_preview_uses_center_column_layout():
    captured = {}

    class _FakeColumn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeContainer:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit:
        def columns(self, spec):
            captured["columns"] = spec
            return (_FakeColumn(), _FakeColumn(), _FakeColumn())

        def video(self, path, *, width):
            captured["video"] = (path, width)

        def markdown(self, *_args, **_kwargs):
            captured["markdown_called"] = True

        def container(self, **_kwargs):
            return _FakeContainer()

    output_preview.st = FakeStreamlit()

    output_preview.render_scaled_video_preview("final.mp4")

    assert captured["columns"] == [1, 2, 1]
    assert captured["video"] == ("final.mp4", "stretch")
