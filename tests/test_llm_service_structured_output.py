from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pixelle_video.services.llm_service import LLMService


class MovieReview(BaseModel):
    title: str
    rating: int


class _NativeParseRecorder:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response


class _CreateRecorder:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response


def _build_fake_client(*, base_url: str, parse_response=None, create_response=None):
    parse_recorder = _NativeParseRecorder(parse_response)
    create_recorder = _CreateRecorder(create_response)
    return (
        SimpleNamespace(
            base_url=base_url,
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(parse=parse_recorder.parse)
                )
            ),
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create_recorder.create)
            ),
        ),
        parse_recorder,
        create_recorder,
    )


@pytest.mark.asyncio
async def test_llm_service_uses_native_structured_output_for_supported_openai_models(monkeypatch):
    native_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    parsed=MovieReview(title="Inception", rating=9),
                    content=None,
                    refusal=None,
                )
            )
        ]
    )
    fake_client, parse_recorder, create_recorder = _build_fake_client(
        base_url="https://api.openai.com/v1/",
        parse_response=native_response,
        create_response=None,
    )

    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)

    result = await service(
        prompt="Review Inception",
        model="gpt-4o-mini",
        response_type=MovieReview,
    )

    assert result == MovieReview(title="Inception", rating=9)
    assert len(parse_recorder.calls) == 1
    assert parse_recorder.calls[0]["response_format"] is MovieReview
    assert create_recorder.calls == []


@pytest.mark.asyncio
async def test_llm_service_falls_back_to_schema_prompt_for_non_openai_provider(monkeypatch):
    create_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"title":"Fallback","rating":8}'
                )
            )
        ]
    )
    fake_client, parse_recorder, create_recorder = _build_fake_client(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        parse_response=None,
        create_response=create_response,
    )

    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)

    result = await service(
        prompt="Review Interstellar",
        model="qwen-max",
        response_type=MovieReview,
    )

    assert result == MovieReview(title="Fallback", rating=8)
    assert parse_recorder.calls == []
    assert len(create_recorder.calls) == 1
    assert "JSON Output Format Required" in create_recorder.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_llm_service_falls_back_to_schema_prompt_for_unsupported_openai_model(monkeypatch):
    create_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"title":"Legacy","rating":7}'
                )
            )
        ]
    )
    fake_client, parse_recorder, create_recorder = _build_fake_client(
        base_url="https://api.openai.com/v1/",
        parse_response=None,
        create_response=create_response,
    )

    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)

    result = await service(
        prompt="Review The Matrix",
        model="gpt-3.5-turbo",
        response_type=MovieReview,
    )

    assert result == MovieReview(title="Legacy", rating=7)
    assert parse_recorder.calls == []
    assert len(create_recorder.calls) == 1
