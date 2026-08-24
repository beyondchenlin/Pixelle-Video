from fastapi import FastAPI

from api.routers.text_rendering_preview import router
from pixelle_video.services.text_rendering_preview import TextRenderingPreviewFrameResult
from tests.support.test_client import create_test_client


def test_text_rendering_preview_frame_api_returns_public_artifact_contract(monkeypatch):
    captured = {}
    injected_object_store = object()

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
    app.state.artifact_object_store = injected_object_store
    app.include_router(router)
    client = create_test_client(app)

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
            "media_placement": {},
            "preview_media_storage_key": "artifacts/demo/source.png",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "storage_key": "artifacts/demo/frame.png",
        "url": "https://cdn.example.test/frame.png",
    }
    assert set(response.json()) == {"storage_key", "url"}
    assert captured["object_store"] is injected_object_store
    assert captured["request"].text_rendering["title_style"] == {"font_size": 80}
    assert captured["request"].media_placement == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "anchor": "center",
    }
    assert "template_params" not in captured["request"].text_rendering
    assert not hasattr(captured["request"], "preview_media_url")
    assert not hasattr(captured["request"], "template_params")


def test_text_rendering_preview_frame_api_preserves_legacy_anchor_input(monkeypatch):
    captured = {}

    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            pass

        async def render_preview_frame(self, request):
            captured["request"] = request
            return TextRenderingPreviewFrameResult(
                storage_key="artifacts/demo/frame.png",
                url=None,
                fingerprint="fp-api",
            )

    monkeypatch.setattr(
        "api.routers.text_rendering_preview.TextRenderingPreviewFrameService",
        FakeService,
    )

    app = FastAPI()
    app.state.artifact_object_store = object()
    app.include_router(router)
    client = create_test_client(app)

    response = client.post(
        "/text-rendering/preview-frame",
        json={
            "workspace_id": "demo",
            "template_id": "image_default",
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
            "media_placement": {"anchor": "bottom_right", "scale_percent": 80},
        },
    )

    assert response.status_code == 200
    assert captured["request"].media_placement == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 80,
        "anchor": "bottom_right",
    }


def test_text_rendering_preview_frame_requires_injected_object_store(monkeypatch):
    service_called = False

    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            nonlocal service_called
            service_called = True

        async def render_preview_frame(self, request):
            raise AssertionError("missing platform dependency should reject before service call")

    monkeypatch.setattr(
        "api.routers.text_rendering_preview.TextRenderingPreviewFrameService",
        FakeService,
    )

    app = FastAPI()
    app.include_router(router)
    client = create_test_client(app, raise_server_exceptions=False)

    response = client.post(
        "/text-rendering/preview-frame",
        json={
            "workspace_id": "demo",
            "template_id": "image_default",
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Artifact object store is not configured"
    assert service_called is False


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
    client = create_test_client(app)

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
    client = create_test_client(app)

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


def test_text_rendering_preview_frame_rejects_invalid_template_id_before_service(
    monkeypatch,
):
    service_called = False

    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            nonlocal service_called
            service_called = True

        async def render_preview_frame(self, request):
            raise AssertionError("validation should reject before service call")

    monkeypatch.setattr(
        "api.routers.text_rendering_preview.TextRenderingPreviewFrameService",
        FakeService,
    )

    app = FastAPI()
    app.include_router(router)
    client = create_test_client(app, raise_server_exceptions=False)

    for template_id in ("../image_default", "missing_template", "image_default/../../x"):
        response = client.post(
            "/text-rendering/preview-frame",
            json={
                "workspace_id": "demo",
                "template_id": template_id,
                "canvas_width": 1080,
                "canvas_height": 1920,
                "media_width": 900,
                "media_height": 1200,
            },
        )

        assert response.status_code == 400

    assert service_called is False


def test_text_rendering_preview_frame_rejects_invalid_workspace_id_before_service(
    monkeypatch,
):
    service_called = False

    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            nonlocal service_called
            service_called = True

        async def render_preview_frame(self, request):
            raise AssertionError("validation should reject before service call")

    monkeypatch.setattr(
        "api.routers.text_rendering_preview.TextRenderingPreviewFrameService",
        FakeService,
    )

    app = FastAPI()
    app.include_router(router)
    client = create_test_client(app)

    for workspace_id in ("../bad", "ws/bad"):
        response = client.post(
            "/text-rendering/preview-frame",
            json={
                "workspace_id": workspace_id,
                "template_id": "image_default",
                "canvas_width": 1080,
                "canvas_height": 1920,
                "media_width": 900,
                "media_height": 1200,
            },
        )

        assert response.status_code == 422

    assert service_called is False


def test_text_rendering_preview_frame_rejects_invalid_media_placement_with_4xx(
    monkeypatch,
):
    service_called = False

    class FakeService:
        def __init__(self, *, object_store, renderer=None):
            nonlocal service_called
            service_called = True

        async def render_preview_frame(self, request):
            raise AssertionError("validation should reject before service call")

    monkeypatch.setattr(
        "api.routers.text_rendering_preview.TextRenderingPreviewFrameService",
        FakeService,
    )

    app = FastAPI()
    app.include_router(router)
    client = create_test_client(app, raise_server_exceptions=False)

    response = client.post(
        "/text-rendering/preview-frame",
        json={
            "workspace_id": "demo",
            "template_id": "image_default",
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
            "media_placement": {"scale_percent": 0},
        },
    )

    assert 400 <= response.status_code < 500
    assert response.status_code != 500
    assert service_called is False


def test_text_rendering_preview_frame_maps_cross_workspace_key_to_4xx():
    app = FastAPI()
    app.state.artifact_object_store = object()
    app.include_router(router)
    client = create_test_client(app, raise_server_exceptions=False)

    response = client.post(
        "/text-rendering/preview-frame",
        json={
            "workspace_id": "ws-a",
            "template_id": "image_default",
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
            "preview_media_storage_key": "artifacts/ws-b/source.png",
        },
    )

    assert 400 <= response.status_code < 500


def test_text_rendering_preview_frame_maps_malformed_storage_key_to_4xx():
    app = FastAPI()
    app.state.artifact_object_store = object()
    app.include_router(router)
    client = create_test_client(app, raise_server_exceptions=False)

    response = client.post(
        "/text-rendering/preview-frame",
        json={
            "workspace_id": "ws-a",
            "template_id": "image_default",
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
            "preview_media_storage_key": "artifacts/ws-a/../source.png",
        },
    )

    assert 400 <= response.status_code < 500


def test_text_rendering_preview_frame_is_registered_under_api_prefix():
    from api.app import app

    route_paths = {route.path for route in app.routes}

    assert "/api/text-rendering/preview-frame" in route_paths
