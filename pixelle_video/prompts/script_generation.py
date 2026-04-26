from __future__ import annotations

import json
import re
from pathlib import Path

SCRIPT_TEMPLATE_DIR = Path(__file__).with_name("script_templates")
DEFAULT_SCRIPT_TEMPLATE_ID = "default"


def _strip_frontmatter(markdown: str) -> str:
    if not markdown.startswith("---"):
        return markdown.strip()
    end = markdown.find("\n---", 3)
    if end < 0:
        return markdown.strip()
    return markdown[end + len("\n---"):].strip()


def load_script_generation_template(template_id: str = DEFAULT_SCRIPT_TEMPLATE_ID) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", template_id):
        raise ValueError("script template id must contain only letters, numbers, underscores, and hyphens")
    template_path = SCRIPT_TEMPLATE_DIR / f"{template_id}.md"
    if not template_path.is_file():
        raise FileNotFoundError(f"script generation template not found: {template_id}")
    return _strip_frontmatter(template_path.read_text(encoding="utf-8"))


def build_script_generation_prompt(
    *,
    topic: str,
    length_instruction: str,
    template_id: str = DEFAULT_SCRIPT_TEMPLATE_ID,
) -> str:
    script_generation_strategy = load_script_generation_template(template_id)
    payload = {
        "task": "generate_complete_video_script_source_text",
        "topic": topic,
        "length_instruction": length_instruction,
        "script_generation_strategy": script_generation_strategy,
        "requirements": [
            "Generate one complete source_text for the whole video script.",
            "The source_text must be coherent as a complete script before storyboard splitting.",
            "Do not split the script into storyboard frames.",
            "Do not generate image prompts.",
            "Return JSON only.",
        ],
        "output_schema": {
            "source_text": "The complete source_text script for the video.",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = [
    "DEFAULT_SCRIPT_TEMPLATE_ID",
    "SCRIPT_TEMPLATE_DIR",
    "build_script_generation_prompt",
    "load_script_generation_template",
]
