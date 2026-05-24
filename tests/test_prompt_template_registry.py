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
            "language_requirement": "Image prompts must use English",
            "output_language_label": "English",
            "detail_requirement": "Ensure clear, complete, and creative descriptions.",
            "example_prompt": "[detailed English image prompt]",
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
