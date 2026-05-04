import httpx

from web.utils import content_api


def test_generate_world_hint_draft_posts_expected_payload(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "world_hint_draft": "古城漫游草稿",
                "generation_world_profile": {"summary": "古城漫游"},
                "hint_source": "generated_from_script",
            },
        )

    monkeypatch.setattr(content_api.httpx, "post", fake_post)

    payload = content_api.generate_world_hint_draft(
        source_text="demo",
        title="title",
        world_preset_id="neutral_knowledge_storyboard",
        storyboard_prompt_language="zh_CN",
        ip_default_world_hint="friendly guide world",
    )

    assert captured["url"] == content_api.DEFAULT_ENDPOINT
    assert captured["timeout"] == content_api.DEFAULT_TIMEOUT
    assert captured["json"]["ip_default_world_hint"] == "friendly guide world"
    assert payload["world_hint_draft"] == "古城漫游草稿"
