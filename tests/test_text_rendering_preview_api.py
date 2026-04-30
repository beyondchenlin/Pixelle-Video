from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.text_rendering_preview import router
from pixelle_video.services.text_rendering_preview import TextRenderingPreviewFrameResult


def test_text_rendering_preview_frame_api_returns_public_artifact_contract(monkeypatch):
    captured = {}

    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            captured["object_store"] = object_store
            captured["renderer"] = renderer

        async def render_preview_frame(self, request):
            captured["request"] = request
            return TextRenderingPreviewFrameResult(
                storage_key="artifacts/demo/frame.png",
                url="https://cdn.example.test/frame.png",
                fingerprint="fp-api",
            )

    monkeypatch.setattr(
        "api.routers.text_rendering_preview.TextRenderingPreviewFrameService",
        FakeService,
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/text-rendering/preview-frame",
        json={
            "workspace_id": "demo",
            "template_id": "image_default",
            "title_text": "API title",
            "caption_text": "API caption",
            "text_rendering": {
                "title_style": {"font_size": 80},
                "caption_style": {"font_size": 42},
            },
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
            "media_placement": {"anchor": "center"},
            "preview_media_storage_key": "artifacts/demo/source.png",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "storage_key": "artifacts/demo/frame.png",
        "url": "https://cdn.example.test/frame.png",
        "fingerprint": "fp-api",
    }
    assert set(response.json()) == {"storage_key", "url", "fingerprint"}
    assert captured["request"].text_rendering["title_style"] == {"font_size": 80}
    assert "template_params" not in captured["request"].text_rendering
    assert not hasattr(captured["request"], "preview_media_url")
    assert not hasattr(captured["request"], "template_params")


def test_text_rendering_preview_frame_rejects_public_preview_media_url(monkeypatch):
    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            pass

        async def render_preview_frame(self, request):
            raise AssertionError("validation should reject before service call")

    monkeypatch.setattr(
        "api.routers.text_rendering_preview.TextRenderingPreviewFrameService",
        FakeService,
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/text-rendering/preview-frame",
        json={
            "workspace_id": "demo",
            "template_id": "image_default",
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
            "preview_media_url": "file:///local-only.png",
        },
    )

    assert response.status_code == 422


def test_text_rendering_preview_frame_rejects_unbounded_dimensions_and_fps(monkeypatch):
    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            pass

        async def render_preview_frame(self, request):
            raise AssertionError("validation should reject before service call")

    monkeypatch.setattr(
        "api.routers.text_rendering_preview.TextRenderingPreviewFrameService",
        FakeService,
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/text-rendering/preview-frame",
        json={
            "workspace_id": "demo",
            "template_id": "image_default",
            "canvas_width": 8193,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
            "fps": 121,
        },
    )

    assert response.status_code == 422


def test_text_rendering_preview_frame_is_registered_under_api_prefix():
    from api.app import app

    route_paths = {route.path for route in app.routes}

    assert "/api/text-rendering/preview-frame" in route_paths
