from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

_ACTIVE_TEST_CLIENTS: list[TestClient] = []


def create_test_client(*args: Any, **kwargs: Any) -> TestClient:
    client = TestClient(*args, **kwargs)
    _ACTIVE_TEST_CLIENTS.append(client)
    return client


def close_test_clients() -> None:
    first_error: Exception | None = None
    while _ACTIVE_TEST_CLIENTS:
        client = _ACTIVE_TEST_CLIENTS.pop()
        try:
            client.close()
        except Exception as exc:
            first_error = first_error or exc
    if first_error is not None:
        raise RuntimeError("failed to close an API test client") from first_error
