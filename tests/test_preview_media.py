import httpx

from web.utils.preview_media import load_preview_image_bytes


PNG_BYTES = b"fake-png-bytes"


def test_load_preview_image_bytes_reads_local_file(tmp_path):
    preview_path = tmp_path / "preview.png"
    preview_path.write_bytes(PNG_BYTES)

    assert load_preview_image_bytes(str(preview_path)) == PNG_BYTES


def test_load_preview_image_bytes_downloads_http_url(monkeypatch):
    preview_url = "http://127.0.0.1:8000/view?filename=test.png&type=output"

    def fake_get(url, *, follow_redirects, timeout):
        assert url == preview_url
        assert follow_redirects is True
        assert timeout == 10.0
        request = httpx.Request("GET", url)
        return httpx.Response(200, request=request, content=PNG_BYTES)

    monkeypatch.setattr(httpx, "get", fake_get)

    assert load_preview_image_bytes(preview_url) == PNG_BYTES
