from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pixelle_video.models.storyboard_planning import StoryboardPlanningResponse
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


class _CreateRejectsJsonModeThenSucceeds:
    def __init__(self, response, message="response_format is not supported"):
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.message = message

    async def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        if "response_format" in kwargs:
            raise TypeError(self.message)
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
async def test_llm_service_uses_dashscope_json_mode_without_max_tokens(monkeypatch):
    create_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"title":"Qwen","rating":8}'
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
        prompt="Review Qwen",
        model="qwen-max",
        response_type=MovieReview,
        max_tokens=8192,
    )

    assert result == MovieReview(title="Qwen", rating=8)
    assert parse_recorder.calls == []
    assert len(create_recorder.calls) == 1
    assert "JSON Output Format Required" in create_recorder.calls[0]["messages"][0]["content"]
    assert create_recorder.calls[0]["response_format"] == {"type": "json_object"}
    assert "max_tokens" not in create_recorder.calls[0]


@pytest.mark.asyncio
async def test_llm_service_uses_json_mode_with_max_tokens_for_generic_compatible_provider(monkeypatch):
    create_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"title":"Compatible","rating":8}'
                )
            )
        ]
    )
    fake_client, _, create_recorder = _build_fake_client(
        base_url="https://api.deepseek.com/v1",
        parse_response=None,
        create_response=create_response,
    )

    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)

    result = await service(
        prompt="Review compatible provider",
        model="deepseek-chat",
        response_type=MovieReview,
        max_tokens=8192,
    )

    assert result == MovieReview(title="Compatible", rating=8)
    assert len(create_recorder.calls) == 1
    assert create_recorder.calls[0]["response_format"] == {"type": "json_object"}
    assert create_recorder.calls[0]["max_tokens"] == 8192


@pytest.mark.asyncio
async def test_llm_service_retries_without_json_mode_when_provider_rejects_it(monkeypatch):
    create_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"title":"Fallback","rating":7}'
                )
            )
        ]
    )
    create_recorder = _CreateRejectsJsonModeThenSucceeds(create_response)
    fake_client = SimpleNamespace(
        base_url="https://custom-provider.example/v1",
        beta=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(parse=_NativeParseRecorder(None).parse)
            )
        ),
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_recorder.create)
        ),
    )

    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)

    result = await service(
        prompt="Review fallback provider",
        model="custom-model",
        response_type=MovieReview,
        max_tokens=1234,
    )

    assert result == MovieReview(title="Fallback", rating=7)
    assert len(create_recorder.calls) == 2
    assert create_recorder.calls[0]["response_format"] == {"type": "json_object"}
    assert create_recorder.calls[0]["max_tokens"] == 1234
    assert "response_format" not in create_recorder.calls[1]
    assert create_recorder.calls[1]["max_tokens"] == 1234


@pytest.mark.asyncio
async def test_llm_service_does_not_retry_unrelated_type_errors(monkeypatch):
    create_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"title":"Fallback","rating":7}'
                )
            )
        ]
    )
    create_recorder = _CreateRejectsJsonModeThenSucceeds(
        create_response,
        message="unexpected keyword argument 'temperature'",
    )
    fake_client = SimpleNamespace(
        base_url="https://custom-provider.example/v1",
        beta=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(parse=_NativeParseRecorder(None).parse)
            )
        ),
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_recorder.create)
        ),
    )

    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)

    with pytest.raises(TypeError, match="temperature"):
        await service(
            prompt="Review fallback provider",
            model="custom-model",
            response_type=MovieReview,
            max_tokens=1234,
        )

    assert len(create_recorder.calls) == 1


@pytest.mark.asyncio
async def test_llm_service_does_not_retry_invalid_parameter_errors_that_only_mention_response_format_context(monkeypatch):
    create_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"title":"Fallback","rating":7}'
                )
            )
        ]
    )
    create_recorder = _CreateRejectsJsonModeThenSucceeds(
        create_response,
        message="invalid parameter: max_tokens while response_format=json_object",
    )
    fake_client = SimpleNamespace(
        base_url="https://custom-provider.example/v1",
        beta=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(parse=_NativeParseRecorder(None).parse)
            )
        ),
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_recorder.create)
        ),
    )

    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)

    with pytest.raises(TypeError, match="max_tokens"):
        await service(
            prompt="Review fallback provider",
            model="custom-model",
            response_type=MovieReview,
            max_tokens=1234,
        )

    assert len(create_recorder.calls) == 1


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


def test_parse_response_as_model_rejects_truncated_outer_payload_instead_of_embedded_frame():
    service = LLMService({})
    truncated = """
    {
      "frames": [
        {
          "scene_id": "1",
          "narration_fragment": "intro",
          "knowledge_goal": "goal",
          "shot_type": "medium_shot",
          "shot_purpose": "context",
          "primary_subject": "subject",
          "secondary_subjects": [],
          "world_elements": ["board"],
          "continuity_anchors": [],
          "focus_detail": "detail",
          "prompt_intent": "intent",
          "locked_fields": [],
          "override_source": null,
          "frame_source": "planner_generated",
          "replan_scope": "local",
          "planner_version": "1.0"
        }
    """

    with pytest.raises(ValueError, match="Failed to parse LLM response"):
        service._parse_response_as_model(truncated, StoryboardPlanningResponse)
