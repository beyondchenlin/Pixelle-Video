from __future__ import annotations

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_structured_json_object_prompt(prompt: str) -> RenderedPrompt:
    return render_prompt_template(
        "structured_json_object",
        {"prompt": prompt},
    )


def render_structured_schema_output_prompt(
    *,
    prompt: str,
    response_type_name: str,
    schema_json: str,
) -> RenderedPrompt:
    return render_prompt_template(
        "structured_schema_output",
        {
            "prompt": prompt,
            "response_type_name": response_type_name,
            "schema_json": schema_json,
        },
    )


__all__ = [
    "render_structured_json_object_prompt",
    "render_structured_schema_output_prompt",
]
