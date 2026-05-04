import json

import pytest

import pixelle_video.services.content_world_planner as content_world_planner
from pixelle_video.models.content_world import ContentWorldHintSource
from pixelle_video.prompts.content_world import (
    build_content_world_prompt,
    parse_content_world_profile,
)
from pixelle_video.services.content_world_planner import ContentWorldPlanner


@pytest.mark.asyncio
async def test_content_world_planner_uses_manual_hint_as_authority():
    calls = []

    async def fake_llm(**kwargs):
        calls.append(kwargs)
        return {
            "summary": "正定古城文旅",
            "time_space": "当代正定古城清晨",
            "visual_environment": "青砖城墙和水汽",
            "atmosphere": "温柔历史感",
            "cultural_context": "中国古城漫游",
            "story_constraints": "不能替代真实古建筑",
            "ip_integration_guidance": "IP 作为陪伴式向导",
        }

    profile = await ContentWorldPlanner().plan(
        llm_service=fake_llm,
        source_text="从长乐门出发，这是正定的南大门。",
        generation_world_hint="正定古城清晨漫游，IP 作为陪伴式向导。",
        ip_world_hint="IP 默认适合亲切讲解。",
        world_preset={"display_name": "Neutral"},
    )

    assert calls
    assert calls[0]["response_type"] is dict
    assert profile.hint_source == ContentWorldHintSource.MANUAL
    assert profile.summary == "正定古城文旅"
    assert profile.ip_integration_guidance == "IP 作为陪伴式向导"


@pytest.mark.asyncio
async def test_content_world_planner_uses_ip_default_without_manual_hint():
    async def fake_llm(**kwargs):
        return {
            "summary": "亲切科普世界",
            "ip_integration_guidance": "IP 作为知识讲解者",
        }

    profile = await ContentWorldPlanner().plan(
        llm_service=fake_llm,
        source_text="讲一个知识点。",
        generation_world_hint=None,
        ip_world_hint="适合亲切科普世界。",
        world_preset={},
    )

    assert profile.hint_source == ContentWorldHintSource.IP_DEFAULT
    assert profile.summary == "亲切科普世界"


@pytest.mark.asyncio
async def test_content_world_planner_falls_back_when_llm_fails():
    async def failing_llm(**kwargs):
        raise RuntimeError("llm down")

    profile = await ContentWorldPlanner().plan(
        llm_service=failing_llm,
        source_text="从长乐门出发，这是正定的南大门。",
        generation_world_hint=None,
        ip_world_hint=None,
        world_preset={"display_name": "Neutral"},
    )

    assert profile.hint_source == ContentWorldHintSource.FALLBACK
    assert profile.generation_failed is True
    assert "从长乐门出发" in profile.summary


@pytest.mark.asyncio
async def test_content_world_planner_falls_back_when_llm_returns_empty_profile():
    async def empty_llm(**kwargs):
        return {}

    profile = await ContentWorldPlanner().plan(
        llm_service=empty_llm,
        source_text="从长乐门出发，这是正定的南大门。",
        generation_world_hint=None,
        ip_world_hint=None,
        world_preset={"display_name": "Neutral"},
    )

    assert profile.hint_source == ContentWorldHintSource.FALLBACK
    assert profile.generation_failed is True
    assert "从长乐门出发" in profile.summary


@pytest.mark.asyncio
async def test_content_world_planner_logs_warning_before_fallback(monkeypatch):
    warnings = []

    class FakeLogger:
        def warning(self, message, *args):
            warnings.append((message, args))

    monkeypatch.setattr(content_world_planner, "logger", FakeLogger())

    async def failing_llm(**kwargs):
        raise RuntimeError("llm down")

    await content_world_planner.ContentWorldPlanner().plan(
        llm_service=failing_llm,
        source_text="从长乐门出发，这是正定的南大门。",
    )

    assert warnings
    assert "Content world planning failed" in warnings[0][0]


def test_build_content_world_prompt_embeds_priority_rules():
    prompt = json.loads(
        build_content_world_prompt(
            source_text="从长乐门出发。",
            generation_world_hint="古城清晨漫游",
            ip_world_hint="亲切科普",
            world_preset={"display_name": "Neutral"},
        )
    )

    assert prompt["task"] == "extract_current_generation_world_profile"
    assert prompt["generation_world_hint"] == "古城清晨漫游"
    assert prompt["ip_default_world_hint"] == "亲切科普"
    assert any("highest priority" in instruction for instruction in prompt["instructions"])


def test_parse_content_world_profile_accepts_fenced_json():
    profile = parse_content_world_profile(
        """```json
{"summary": "古城漫游", "story_constraints": "不能替代真实建筑"}
```""",
        hint_source=ContentWorldHintSource.MANUAL,
    )

    assert profile.summary == "古城漫游"
    assert profile.hint_source == ContentWorldHintSource.MANUAL
