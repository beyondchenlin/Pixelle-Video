from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from api.schemas.responses import install_exception_handlers, success_envelope


class DemoPayload(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if value == "bad":
            raise ValueError("bad name")
        return value


def build_test_app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404, detail="not found")

    @app.post("/payload")
    async def payload(body: DemoPayload):
        return {"name": body.name}

    @app.get("/json-detail")
    async def json_detail():
        raise HTTPException(
            status_code=418,
            detail={"at": datetime(2026, 1, 2, 3, 4, 5)},
        )

    return app


def test_http_exception_uses_error_envelope():
    client = TestClient(build_test_app())

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "message": "not found",
        "error": {"code": "http_404", "details": None},
    }


def test_missing_field_validation_uses_validation_error_envelope():
    client = TestClient(build_test_app())

    response = client.post("/payload", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "validation error"
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"] == ["body", "name"]


def test_field_validator_value_error_details_are_json_safe():
    client = TestClient(build_test_app())

    response = client.post("/payload", json={"name": "bad"})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "validation error"
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"] == ["body", "name"]
    assert "bad name" in body["error"]["details"][0]["msg"]


def test_success_envelope_omits_data_when_none():
    assert success_envelope() == {
        "success": True,
        "message": "Success",
    }


def test_unknown_path_uses_error_envelope():
    client = TestClient(build_test_app())

    response = client.get("/unknown")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "http_404"


def test_wrong_method_uses_error_envelope():
    client = TestClient(build_test_app())

    response = client.get("/payload")

    assert response.status_code == 405
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "http_405"


def test_non_string_http_exception_detail_is_json_safe():
    client = TestClient(build_test_app())

    response = client.get("/json-detail")

    assert response.status_code == 418
    assert response.json() == {
        "success": False,
        "message": "{'at': datetime.datetime(2026, 1, 2, 3, 4, 5)}",
        "error": {
            "code": "http_418",
            "details": {"at": "2026-01-02T03:04:05"},
        },
    }
