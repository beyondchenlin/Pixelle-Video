from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.llm_trace import router as llm_trace_router


class FakeTraceRepository:
    def __init__(self, traces):
        self.traces = traces
        self.filters = []

    async def list_llm_interactions(self, workspace_id, filters=None):
        self.filters.append({"workspace_id": workspace_id, "filters": filters})
        results = [
            trace
            for trace in self.traces
            if trace["context"]["workspace_id"] == workspace_id
        ]
        if filters:
            for key, value in filters.items():
                if value is None:
                    continue
                if key == "task_id":
                    results = [
                        trace
                        for trace in results
                        if trace["context"].get("task_id") == value
                    ]
                elif key == "operation":
                    results = [
                        trace
                        for trace in results
                        if trace["context"].get("operation") == value
                    ]
                elif key == "trace_id":
                    results = [
                        trace
                        for trace in results
                        if trace.get("trace_id") == value
                    ]
        return results


class FakeRawPayloadStore:
    def __init__(self, payloads):
        self.payloads = payloads

    async def get_json(self, storage_key):
        return self.payloads[storage_key]


def _client(
    *,
    trace_repository=None,
    raw_payload_store=None,
    local_debug_enabled=False,
    client_host="testclient",
):
    app = FastAPI()
    if trace_repository is not None:
        app.state.trace_repository = trace_repository
    if raw_payload_store is not None:
        app.state.raw_payload_store = raw_payload_store
    app.state.local_debug_enabled = local_debug_enabled
    app.include_router(llm_trace_router)
    return TestClient(app, client=(client_host, 50000))


def _trace():
    return {
        "trace_id": "trace_001",
        "context": {
            "workspace_id": "workspace_1",
            "task_id": "task_123",
            "operation": "image_prompt_generation",
            "stage": "stage1a",
            "frame_id": "frame_0001",
            "metadata": {},
        },
        "provider": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "status": "success",
        "request_payload_key": "raw-payloads/workspace_1/request.json",
        "request_sha256": "a" * 64,
        "request_preview": '{"messages":[{"content":"safe preview"}]}',
        "response_payload_key": "raw-payloads/workspace_1/response.json",
        "response_sha256": "b" * 64,
        "response_preview": '{"content":"safe response preview"}',
        "elapsed_ms": None,
        "token_usage": None,
        "parse_error": "",
        "validation_errors": [],
        "created_at": "2026-04-30T00:00:00Z",
    }


def test_llm_trace_summary_reads_repository_without_raw_payload_content():
    trace_repository = FakeTraceRepository([_trace()])
    client = _client(trace_repository=trace_repository)

    response = client.get("/llm-traces/workspace_1", params={"task_id": "task_123"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["traces"][0]["trace_id"] == "trace_001"
    assert body["traces"][0]["request_preview"] == '{"messages":[{"content":"safe preview"}]}'
    assert "request_payload_key" not in body["traces"][0]
    assert "response_payload_key" not in body["traces"][0]
    assert "raw request" not in str(body)
    assert trace_repository.filters == [
        {
            "workspace_id": "workspace_1",
            "filters": {"task_id": "task_123", "operation": None},
        }
    ]


def test_llm_trace_summary_fails_fast_when_repository_is_not_injected():
    response = _client().get("/llm-traces/workspace_1")

    assert response.status_code == 503
    assert "trace repository is not configured" in response.json()["detail"]


def test_llm_trace_raw_payload_rejects_spoofed_debug_header_without_local_debug_capability():
    trace_repository = FakeTraceRepository([_trace()])
    raw_payload_store = FakeRawPayloadStore(
        {"raw-payloads/workspace_1/request.json": {"raw": "request"}}
    )
    client = _client(
        trace_repository=trace_repository,
        raw_payload_store=raw_payload_store,
    )

    response = client.get(
        "/llm-traces/workspace_1/trace_001/raw/request",
        headers={"x-pixelle-local-debug": "true"},
    )

    assert response.status_code == 403


def test_llm_trace_raw_payload_requires_loopback_local_debug_request():
    trace_repository = FakeTraceRepository([_trace()])
    raw_payload_store = FakeRawPayloadStore(
        {"raw-payloads/workspace_1/request.json": {"raw": "request"}}
    )
    client = _client(
        trace_repository=trace_repository,
        raw_payload_store=raw_payload_store,
        local_debug_enabled=True,
        client_host="203.0.113.10",
    )

    response = client.get(
        "/llm-traces/workspace_1/trace_001/raw/request",
        headers={"x-pixelle-local-debug": "true"},
    )

    assert response.status_code == 403


def test_llm_trace_raw_payload_reads_by_object_key_when_local_debug_is_authorized():
    trace_repository = FakeTraceRepository([_trace()])
    raw_payload_store = FakeRawPayloadStore(
        {"raw-payloads/workspace_1/request.json": {"raw": "request"}}
    )
    client = _client(
        trace_repository=trace_repository,
        raw_payload_store=raw_payload_store,
        local_debug_enabled=True,
        client_host="127.0.0.1",
    )

    response = client.get(
        "/llm-traces/workspace_1/trace_001/raw/request",
        headers={"x-pixelle-local-debug": "true"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Success",
        "trace_id": "trace_001",
        "payload_kind": "request",
        "payload": {"raw": "request"},
    }
