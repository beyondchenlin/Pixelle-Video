from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from api.schemas.responses import install_exception_handlers


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

    return app


def test_http_exception_uses_error_envelope():
    client = TestClient(build_test_app())

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "message": "not found",
        "error": {"code": "http_404", "details": "not found"},
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
