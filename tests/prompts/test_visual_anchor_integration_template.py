from __future__ import annotations

from pathlib import Path
from string import Formatter

from pixelle_video.prompts.visual_anchor_integration import render_visual_anchor_integration_prompt


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / "pixelle_video/prompts/templates/visual_anchor_integration.md"


def test_visual_anchor_template_has_no_empty_format_placeholders():
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    empty_fields = [
        (literal, field_name)
        for literal, field_name, _format_spec, _conversion in Formatter().parse(template)
        if field_name == ""
    ]
    assert not empty_fields


def test_visual_anchor_integration_prompt_renders_with_strict_schema_guards():
    rendered = render_visual_anchor_integration_prompt(
        base_visual_briefs_json=[],
        anchor_profile_json={},
        visual_signature_policy_json={},
        cadence_plan_json=[],
    )

    assert "# Strict schema guards" in rendered.text
    assert "Use an empty object when there is no affordance" in rendered.text
    assert "affordance" in rendered.text
    assert "candidates" in rendered.text
