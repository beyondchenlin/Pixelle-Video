from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from loguru import logger

from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy

DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "visual_signature_policy.md"
)
POLICY_PATH_ENV = "PIXELLE_VISUAL_SIGNATURE_POLICY_PATH"


def load_visual_signature_policy(path: str | Path | None = None) -> VisualSignaturePolicy:
    """Load the visual-signature runtime policy from Markdown.

    The Markdown file is data only. It may tune thresholds, tighten lists, or add
    project-specific forbidden terms, but Python still keeps the immutable hard
    gates defined by VisualSignaturePolicy.
    """

    policy_path = _resolve_policy_path(path)
    if not policy_path.exists():
        return VisualSignaturePolicy()
    try:
        payload = _read_markdown_policy_payload(policy_path)
    except Exception as exc:
        logger.warning(
            "Failed to load visual signature policy from {}; using hard-coded defaults: {}",
            policy_path,
            exc,
        )
        return VisualSignaturePolicy()
    return VisualSignaturePolicy.from_dict(payload)


def _resolve_policy_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.getenv(POLICY_PATH_ENV, "").strip()
    if env_path:
        return Path(env_path)
    return DEFAULT_POLICY_PATH


def _read_markdown_policy_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    yaml_text = _extract_yaml_block(text) or text
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(yaml_text) or {}
    except Exception:
        payload = _parse_simple_yaml_subset(yaml_text)
    if not isinstance(payload, dict):
        raise ValueError("visual signature policy payload must be a mapping")
    return dict(payload)


def _extract_yaml_block(text: str) -> str:
    match = re.search(r"```(?:yaml|yml)\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _parse_simple_yaml_subset(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    current_key: str | None = None
    current_items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith(" ") and current_key and line.strip().startswith("- "):
            current_items.append(_coerce_scalar(line.strip()[2:].strip()))
            payload[current_key] = current_items
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if not value:
            current_items = []
            payload[current_key] = current_items
            continue
        payload[current_key] = _coerce_scalar(value)
        current_items = []
    return payload


def _coerce_scalar(value: str) -> Any:
    text = value.strip().strip('"').strip("'")
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


__all__ = ["DEFAULT_POLICY_PATH", "POLICY_PATH_ENV", "load_visual_signature_policy"]
