from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.layered_template_preview import router
from pixelle_video.models.layered_template import LayeredTemplateSpec


def _spec_payload() -> dict:
    return {
        "version": "layered_template.v1",
        "template_id": "api-preview-demo",
        "template_name": "API Preview Demo",
        "template_type": "image",
        "canvas_width": 1080,
        "canvas_height": 1920,
        "media_width": 900,
        "media_height": 1200,
        "safe_area": {"x": 80, "y": 120, "width": 920, "height": 1680, "unit": "px"},
        "layers": [
            {
                "id": "bg",
                "type": "background",
                "name": "Background",
                "rect": {"x": 0, "y": 0, "width": 1080, "height": 1920, "unit": "px"},
                "z_index": 0,
                "opacity": 1,
                "rotation": 0,
                "locked": True,
                "source": {"kind": "color", "ref": "#101820", "metadata": {}},
                "style": {},
                "role": None,
            },
            {
                "id": "title",
                "type": "text",
                "name": "Title",
                "rect": {"x": 110, "y": 90, "width": 860, "height": 180, "unit": "px"},
                "z_index": 10,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": None,
                "style": {"font_size": 72, "color": "#FFEBCD"},
                "role": "title",
            },
            {
                "id": "caption",
                "type": "text",
                "name": "Caption",
                "rect": {"x": 120, "y": 1640, "width": 840, "height": 140, "unit": "px"},
                "z_index": 20,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": None,
                "style": {"font_size": 42, "color": "#FFFFFF"},
                "role": "caption",
            },
        ],
        "metadata": {"source": "test"},
    }


def test_layered_template_preview_frame_returns_html_contract(monkeypatch):
    captured = {}

    class FakeService:
        def render_preview_html(self, *, spec, title_text, caption_text, text_rendering):
            captured["spec"] = spec
            captured["title_text"] = title_text
            captured["caption_text"] = caption_text
            captured["text_rendering"] = text_rendering
            return "<html>preview</html>"

        def fingerprint(self, spec):
            captured["fingerprint_spec"] = spec
            return "fp-api"

    monkeypatch.setattr("api.routers.layered_template_preview.LayeredTemplateService", FakeService)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={
            "workspace_id": "demo",
            "spec": _spec_payload(),
            "title_text": "API title",
            "caption_text": "API caption",
            "text_rendering": {"title_style": {"font_size": 88}},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "kind": "html_preview",
        "html": "<html>preview</html>",
        "fingerprint": "fp-api",
    }
    assert isinstance(captured["spec"], LayeredTemplateSpec)
    assert captured["spec"].template_id == "api-preview-demo"
    assert captured["fingerprint_spec"] is captured["spec"]
    assert captured["title_text"] == "API title"
    assert captured["caption_text"] == "API caption"
    assert captured["text_rendering"] == {"title_style": {"font_size": 88}}


def test_layered_template_preview_frame_is_registered_on_main_api_app():
    from api.app import app

    route_paths = {getattr(route, "path", None) for route in app.routes}

    assert "/api/layered-templates/preview-frame" in route_paths


def test_layered_template_preview_frame_rejects_incomplete_spec_payload():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={
            "workspace_id": "demo",
            "spec": {"template_id": "missing-required-fields", "layers": []},
        },
    )

    assert response.status_code == 422


def test_layered_template_preview_frame_rejects_extra_contract_fields():
    payload = _spec_payload()
    payload["template_params"] = {"legacy": "must not be accepted"}
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={"workspace_id": "demo", "spec": payload},
    )

    assert response.status_code == 422


def test_layered_template_preview_frame_rejects_unsupported_template_type():
    payload = _spec_payload()
    payload["template_type"] = "interactive"
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={"workspace_id": "demo", "spec": payload},
    )

    assert response.status_code == 422


def test_layered_template_preview_frame_rejects_too_many_layers():
    payload = _spec_payload()
    payload["layers"] = [
        {
            **payload["layers"][0],
            "id": f"bg_{index}",
        }
        for index in range(65)
    ]
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={"workspace_id": "demo", "spec": payload},
    )

    assert response.status_code == 422


def test_layered_template_preview_frame_rejects_oversized_text_fields():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={
            "workspace_id": "demo",
            "spec": _spec_payload(),
            "title_text": "x" * 2049,
        },
    )

    assert response.status_code == 422


def test_layered_template_preview_frame_rejects_deep_text_rendering_payload():
    nested = {}
    cursor = nested
    for index in range(10):
        cursor["child"] = {}
        cursor = cursor["child"]

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={
            "workspace_id": "demo",
            "spec": _spec_payload(),
            "text_rendering": nested,
        },
    )

    assert response.status_code == 422


def test_layered_template_preview_frame_maps_model_semantic_errors_to_400():
    payload = _spec_payload()
    payload["layers"][0]["source"] = {"kind": "color", "ref": "not-a-color", "metadata": {}}
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={"workspace_id": "demo", "spec": payload},
    )

    assert response.status_code == 400
    assert "color" in response.json()["detail"] or "invalid" in response.json()["detail"].lower()


def test_layered_template_preview_frame_accepts_complete_zero_layer_legacy_spec():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={
            "workspace_id": "demo",
            "spec": {
                "version": "layered_template.v1",
                "template_id": "legacy",
                "template_name": "Legacy",
                "template_type": "image",
                "canvas_width": 1920,
                "canvas_height": 1080,
                "media_width": 1920,
                "media_height": 1080,
                "safe_area": {
                    "x": 0,
                    "y": 0,
                    "width": 1920,
                    "height": 1080,
                    "unit": "px",
                },
                "layers": [],
                "metadata": {"source_kind": "legacy_html"},
            },
            "title_text": "Legacy title",
            "caption_text": "Legacy caption",
        },
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "html_preview"
    assert "width:1920px;" in response.json()["html"]
