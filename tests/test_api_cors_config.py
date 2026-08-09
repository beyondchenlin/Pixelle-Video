import pytest
from pydantic import ValidationError

from api.config import APIConfig


def test_api_config_derives_local_cors_origins_from_web_port(monkeypatch):
    monkeypatch.setenv("PIXELLE_WEB_PORT", "8512")
    monkeypatch.delenv("PIXELLE_CORS_ORIGINS", raising=False)

    config = APIConfig.from_env()

    assert config.cors_origins == [
        "http://localhost:8512",
        "http://127.0.0.1:8512",
    ]


def test_api_config_accepts_explicit_deduplicated_cors_origins(monkeypatch):
    monkeypatch.setenv(
        "PIXELLE_CORS_ORIGINS",
        "https://web.example.test/, https://web.example.test, http://localhost:8512",
    )

    config = APIConfig.from_env()

    assert config.cors_origins == [
        "https://web.example.test",
        "http://localhost:8512",
    ]


@pytest.mark.parametrize(
    "origins",
    [
        ["*"],
        [],
        ["file:///tmp/index.html"],
        ["https://user:secret@example.test"],
        ["https://example.test/path"],
    ],
)
def test_api_config_rejects_unsafe_cors_origins(origins):
    with pytest.raises(ValidationError):
        APIConfig(cors_origins=origins)
