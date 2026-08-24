from fastapi import FastAPI

from api.routers.layered_template_preview import router
from pixelle_video.services.layered_template_service import LayeredTemplatePreviewFrameResult
from tests.support.test_client import create_test_client


def test_preview_frame_api_returns_storage_key(monkeypatch):
    captured = {}
    injected_object_store = object()

    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            captured["object_store"] = object_store
            captured["renderer"] = renderer

        async def render_preview_frame(self, request):
            captured["request"] = request
            return LayeredTemplatePreviewFrameResult(
                storage_key="artifacts/ws/preview.png",
                url="/api/files/artifacts/ws/preview.png",
                fingerprint="fp-api",
            )

    monkeypatch.setattr(
        "api.routers.layered_template_preview.LayeredTemplateService",
        FakeService,
    )

    app = FastAPI()
    app.state.artifact_object_store = injected_object_store
    app.include_router(router)
    client = create_test_client(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={
            "workspace_id": "ws",
            "title_text": "Title",
            "caption_text": "Caption",
            "text_rendering": {"title_style": {"font_size": 88}},
            "spec": {
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
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "storage_key": "artifacts/ws/preview.png",
        "url": "/api/files/artifacts/ws/preview.png",
    }
    assert captured["object_store"] is injected_object_store
    assert captured["request"].workspace_id == "ws"
    assert captured["request"].spec.template_id == "demo"
    assert captured["request"].text_rendering["title_style"] == {"font_size": 88}


def test_preview_frame_api_requires_injected_object_store(monkeypatch):
    service_called = False

    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            nonlocal service_called
            service_called = True

        async def render_preview_frame(self, request):
            raise AssertionError("missing platform dependency should reject before service call")

    monkeypatch.setattr(
        "api.routers.layered_template_preview.LayeredTemplateService",
        FakeService,
    )

    app = FastAPI()
    app.include_router(router)
    client = create_test_client(app, raise_server_exceptions=False)

    response = client.post(
        "/layered-templates/preview-frame",
        json={
            "workspace_id": "ws",
            "spec": {
                "version": "layered_template.v1",
                "template_id": "demo",
                "template_name": "Demo",
                "template_type": "image",
                "canvas_width": 1080,
                "canvas_height": 1920,
                "media_width": 1080,
                "media_height": 1920,
                "safe_area": {"x": 64, "y": 64, "width": 952, "height": 1792},
                "layers": [],
                "metadata": {},
            },
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Artifact object store is not configured"
    assert service_called is False


def test_layered_template_preview_route_is_registered_once_under_api_prefix():
    from api.app import app

    preview_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/layered-templates/preview-frame"
    ]

    assert len(preview_routes) == 1
