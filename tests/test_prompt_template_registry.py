import pytest

from pixelle_video.prompts.template_loader import (
    PROMPT_TEMPLATE_IDS,
    PromptTemplateError,
    load_prompt_template,
    render_prompt_template,
)

REQUIRED_TEMPLATE_IDS = {
    "image_generation",
    "video_generation",
    "ip_role_selection",
    "topic_narration",
    "content_narration",
    "title_generation",
    "style_conversion",
    "style_resolution",
    "content_world",
    "storyboard_planning",
    "storyboard_generation",
    "prompt_prefix_generation",
    "script_generation",
    "asset_script_generation",
    "structured_json_object",
    "structured_schema_output",
    "storyboard_repair",
}

JSON_PROMPT_TEMPLATE_IDS = {
    "content_world",
    "style_resolution",
    "storyboard_planning",
    "storyboard_generation",
    "asset_script_generation",
    "structured_json_object",
    "structured_schema_output",
    "storyboard_repair",
}

JSON_PROMPT_MODULES = {
    "content_world": "pixelle_video/prompts/content_world.py",
    "style_resolution": "pixelle_video/prompts/style_resolution.py",
    "storyboard_planning": "pixelle_video/prompts/storyboard_planning.py",
    "storyboard_generation": "pixelle_video/prompts/storyboard_generation.py",
    "asset_script_generation": "pixelle_video/prompts/asset_script_generation.py",
    "structured_json_object": "pixelle_video/prompts/structured_output.py",
    "structured_schema_output": "pixelle_video/prompts/structured_output.py",
    "storyboard_repair": "pixelle_video/prompts/storyboard_generation.py",
}


def test_prompt_registry_contains_every_generation_template():
    assert REQUIRED_TEMPLATE_IDS <= set(PROMPT_TEMPLATE_IDS)


@pytest.mark.parametrize("prompt_id", sorted(REQUIRED_TEMPLATE_IDS))
def test_prompt_template_has_required_frontmatter(prompt_id):
    template = load_prompt_template(prompt_id)

    assert template.prompt_id == prompt_id
    assert template.version
    assert template.stage
    assert template.purpose
    assert template.output_contract
    assert template.path.name == f"{prompt_id}.md"
    assert "# " in template.body


def test_render_prompt_template_returns_text_and_source_metadata():
    rendered = render_prompt_template(
        "image_generation",
        {
            "input_payload": {"frame_source_texts": ["A guide enters the market."]},
            "min_words": 50,
            "max_words": 100,
            "style_profile_json": "null",
            "narrations_json": '{"frame_source_texts": ["A guide enters the market."]}',
            "narrations_count": 1,
            "output_language_chinese": False,
            "output_language_english": True,
        },
    )

    assert rendered.prompt_id == "image_generation"
    assert rendered.version
    assert rendered.path.endswith("image_generation.md")
    assert "A guide enters the market." in rendered.text
    assert "{input_payload}" not in rendered.text
    assert "{{input_payload}}" not in rendered.text


def test_render_prompt_template_rejects_unresolved_variables():
    with pytest.raises(PromptTemplateError, match="missing template variables"):
        render_prompt_template("title_generation", {"content": "Only one variable"})


@pytest.mark.parametrize("prompt_id", sorted(JSON_PROMPT_TEMPLATE_IDS))
def test_json_prompt_templates_own_instruction_bodies(prompt_id):
    template = load_prompt_template(prompt_id)

    assert "{payload_json}" not in template.body
    assert "instructions" in template.body or "requirements" in template.body
    assert "Return JSON only." in template.body


@pytest.mark.parametrize("prompt_id", sorted(JSON_PROMPT_TEMPLATE_IDS))
def test_json_prompt_modules_do_not_own_instruction_payloads(prompt_id):
    from pathlib import Path

    source = Path(JSON_PROMPT_MODULES[prompt_id]).read_text(encoding="utf-8")

    assert '"task":' not in source
    assert '"instructions": [' not in source
    assert '"requirements": [' not in source
    assert '"output_contract":' not in source


def test_script_generation_uses_registered_template_as_prompt_source():
    from pathlib import Path

    source = Path("pixelle_video/prompts/script_generation.py").read_text(encoding="utf-8")

    assert "script_templates" not in source
    assert "SCRIPT_TEMPLATE_DIR" not in source
    assert "load_script_generation_template" not in source


def test_prompt_modules_do_not_inject_instruction_body_fragments():
    from pathlib import Path

    offenders = []
    forbidden_fragments = {
        "language_requirement",
        "description_length_guidance",
        "example_prompt",
        "count_instruction",
        "visual_goal_description",
        "length_instruction",
    }
    for path in (
        Path("pixelle_video/prompts/image_generation.py"),
        Path("pixelle_video/prompts/video_generation.py"),
        Path("pixelle_video/prompts/storyboard_generation.py"),
        Path("pixelle_video/prompts/script_generation.py"),
        Path("pixelle_video/services/script_generation.py"),
    ):
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in text:
                offenders.append(f"{path}:{fragment}")

    assert offenders == []


def test_content_generators_do_not_fallback_to_raw_style_prefix_after_resolution_failure():
    from pathlib import Path

    source = Path("pixelle_video/utils/content_generators.py").read_text(encoding="utf-8")

    assert "style_resolution_failed" not in source
    assert "legacy prefix concatenation" not in source
