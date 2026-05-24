from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any

TEMPLATE_DIR = Path(__file__).with_name("templates")
REQUIRED_FRONTMATTER_FIELDS = frozenset(
    {"prompt_id", "version", "stage", "purpose", "output_contract"}
)


class PromptTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    stage: str
    purpose: str
    output_contract: str
    path: Path
    body: str


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_id: str
    version: str
    stage: str
    purpose: str
    output_contract: str
    path: str
    text: str

    def trace_metadata(self) -> dict[str, str]:
        return {
            "prompt_id": self.prompt_id,
            "version": self.version,
            "stage": self.stage,
            "purpose": self.purpose,
            "output_contract": self.output_contract,
            "path": self.path,
        }


def _discover_prompt_template_ids() -> frozenset[str]:
    if not TEMPLATE_DIR.is_dir():
        return frozenset()
    return frozenset(path.stem for path in TEMPLATE_DIR.glob("*.md"))


PROMPT_TEMPLATE_IDS = _discover_prompt_template_ids()


def _parse_frontmatter(raw: str, path: Path) -> tuple[dict[str, str], str]:
    if not raw.startswith("---\n"):
        raise PromptTemplateError(f"{path.name} is missing front matter")
    end_index = raw.find("\n---", 4)
    if end_index < 0:
        raise PromptTemplateError(f"{path.name} has unterminated front matter")

    metadata: dict[str, str] = {}
    for line in raw[4:end_index].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise PromptTemplateError(f"{path.name} has invalid front matter line: {line}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")

    missing = sorted(REQUIRED_FRONTMATTER_FIELDS - set(metadata))
    if missing:
        raise PromptTemplateError(
            f"{path.name} missing required front matter fields: {', '.join(missing)}"
        )
    body = raw[end_index + len("\n---") :].strip()
    if not body:
        raise PromptTemplateError(f"{path.name} has an empty prompt body")
    return metadata, body


def load_prompt_template(prompt_id: str) -> PromptTemplate:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", prompt_id):
        raise PromptTemplateError("prompt_id must contain only letters, numbers, underscores, and hyphens")
    path = TEMPLATE_DIR / f"{prompt_id}.md"
    if not path.is_file():
        raise PromptTemplateError(f"prompt template not found: {prompt_id}")

    metadata, body = _parse_frontmatter(path.read_text(encoding="utf-8"), path)
    template_prompt_id = metadata["prompt_id"]
    if template_prompt_id != prompt_id:
        raise PromptTemplateError(
            f"{path.name} front matter prompt_id {template_prompt_id!r} does not match {prompt_id!r}"
        )

    return PromptTemplate(
        prompt_id=template_prompt_id,
        version=metadata["version"],
        stage=metadata["stage"],
        purpose=metadata["purpose"],
        output_contract=metadata["output_contract"],
        path=path,
        body=body,
    )


def _json_default(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _stringify_template_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _json_default(value)


def _frame_source_count(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("frame_source_texts", "narrations"):
            values = payload.get(key)
            if isinstance(values, list):
                return len(values)
    if isinstance(payload, list):
        return len(payload)
    return 0


def _apply_template_defaults(prompt_id: str, variables: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(variables)
    if prompt_id in {"image_generation", "video_generation"} and "input_payload" in resolved:
        input_payload = resolved["input_payload"]
        resolved.setdefault("narrations_json", _json_default(input_payload))
        resolved.setdefault("style_profile_json", _json_default(None))
        resolved.setdefault("narrations_count", _frame_source_count(input_payload))
        if "detail_requirement" in resolved:
            resolved.setdefault("description_length_guidance", resolved["detail_requirement"])
    return resolved


def _template_variables(body: str) -> set[str]:
    variables: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(body):
        if field_name:
            variables.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return variables


def _strip_template_comments(body: str) -> str:
    return re.sub(r"(?ms)^<!--\s*template-loader:strip\b.*?-->\s*", "", body)


def _render_json_blocks(body: str) -> str:
    pattern = re.compile(
        r"(?ms)<!--\s*json-block\s+([A-Za-z_][A-Za-z0-9_]*)\s*-->\s*(.*?)\s*<!--\s*end-json-block\s*-->"
    )
    while True:
        match = pattern.search(body)
        if match is None:
            return body
        block = match.group(2).strip()
        replacement = json.dumps(block, ensure_ascii=False)
        body = body[: match.start()] + replacement + body[match.end() :]


def _render_condition_blocks(body: str, variables: dict[str, Any]) -> str:
    pattern = re.compile(
        r"(?ms)^<!--\s*if\s+([A-Za-z_][A-Za-z0-9_]*)\s*-->\s*(.*?)^<!--\s*endif\s*-->\s*"
    )
    while True:
        match = pattern.search(body)
        if match is None:
            return body
        variable_name, block = match.groups()
        replacement = block if variables.get(variable_name) else ""
        body = body[: match.start()] + replacement + body[match.end() :]


def render_prompt_template(prompt_id: str, variables: dict[str, Any] | None = None) -> RenderedPrompt:
    template = load_prompt_template(prompt_id)
    body = _strip_template_comments(template.body)
    provided = _apply_template_defaults(prompt_id, variables or {})
    body = _render_condition_blocks(body, provided)
    body = _render_json_blocks(body)
    required_variables = _template_variables(body)
    missing = sorted(name for name in required_variables if name not in provided)
    if missing:
        raise PromptTemplateError(
            f"{prompt_id} missing template variables: {', '.join(missing)}"
        )

    stringified = {
        name: _stringify_template_value(value)
        for name, value in provided.items()
    }
    try:
        text = body.format(**stringified).strip()
    except KeyError as exc:
        raise PromptTemplateError(
            f"{prompt_id} missing template variables: {exc.args[0]}"
        ) from exc
    except (IndexError, ValueError) as exc:
        raise PromptTemplateError(f"{prompt_id} template rendering failed: {exc}") from exc

    return RenderedPrompt(
        prompt_id=template.prompt_id,
        version=template.version,
        stage=template.stage,
        purpose=template.purpose,
        output_contract=template.output_contract,
        path=str(template.path),
        text=text,
    )


__all__ = [
    "PROMPT_TEMPLATE_IDS",
    "PromptTemplate",
    "PromptTemplateError",
    "RenderedPrompt",
    "load_prompt_template",
    "render_prompt_template",
]
