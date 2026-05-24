from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

HEX_COLOR_RE = re.compile(
    r"(?<![0-9a-fA-F])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])"
)


def build_color_palette_prompt_entries(
    existing_palette: Mapping[str, Any] | None,
    color_rules: str,
) -> dict[str, Any]:
    if not isinstance(existing_palette, Mapping):
        existing_palette = {}
    existing_rule_hex_by_prompt = _existing_rule_hex_by_prompt(existing_palette)
    palette = {
        str(key): deepcopy(value)
        for key, value in existing_palette.items()
        if not str(key).startswith("rule_")
    }
    for index, raw_rule in enumerate(_split_color_rules(color_rules), start=1):
        entry = _color_rule_entry(raw_rule)
        if entry:
            if "hex" not in entry and entry["prompt"] in existing_rule_hex_by_prompt:
                entry["hex"] = existing_rule_hex_by_prompt[entry["prompt"]]
            palette[f"rule_{index}"] = entry
    return palette


def _existing_rule_hex_by_prompt(existing_palette: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in existing_palette.items():
        if not str(key).startswith("rule_") or not isinstance(value, Mapping):
            continue
        prompt = value.get("prompt")
        hex_value = value.get("hex")
        if isinstance(prompt, str) and prompt.strip() and isinstance(hex_value, str) and hex_value.strip():
            result.setdefault(prompt.strip(), hex_value.strip().upper())
    return result


def _split_color_rules(value: str) -> list[str]:
    normalized = str(value or "").replace(";", ",").replace("\uff1b", ",")
    return [item.strip() for item in re.split(r"[\n,]+", normalized) if item.strip()]


def _color_rule_entry(raw_rule: str) -> dict[str, str]:
    text = raw_rule.strip()
    match = HEX_COLOR_RE.search(text)
    hex_value = match.group(0).upper() if match else ""
    prompt = HEX_COLOR_RE.sub("", text).strip(" -:;\uff1b")
    if not prompt:
        return {}
    entry = {"prompt": prompt}
    if hex_value:
        entry["hex"] = hex_value
    return entry
