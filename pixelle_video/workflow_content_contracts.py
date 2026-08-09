from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pixelle_video.runninghub_workflow_contracts import runninghub_descriptor_path
from pixelle_video.utils.os_util import get_resource_path, get_root_path

TTS_NODE_MARKERS = (
    "edgetts",
    "indextts",
    "omnivoice",
    "tts",
)
ANALYSIS_NODE_MARKERS = (
    "qwenvl",
    "qwen_vl",
    "qwen-vl",
    "vlm",
    "visionlanguage",
    "vision_language",
    "video_understanding",
    "image_understanding",
    "interrogate",
    "interrogator",
)
PROMPT_INPUT_KEYS = frozenset(
    {
        "caption",
        "custom_prompt",
        "content",
        "description",
        "instruction",
        "instructions",
        "message",
        "negative",
        "negative_prompt",
        "positive",
        "positive_prompt",
        "preset_prompt",
        "prompt",
        "query",
        "question",
        "system_prompt",
        "text",
        "user_prompt",
    }
)
PROMPT_INPUT_SUFFIXES = (
    "_caption",
    "_instruction",
    "_instructions",
    "_negative",
    "_negative_prompt",
    "_positive",
    "_positive_prompt",
    "_prompt",
    "_prompt_text",
    "_query",
    "_question",
    "_system_prompt",
    "_text",
    "_user_prompt",
)
PROMPT_NODE_MARKERS = (
    "cliptextencode",
    "conditioning",
    "customprompt",
    "edgetts",
    "indextts",
    "interrogate",
    "interrogator",
    "omnivoice",
    "prompt",
    "qwen-vl",
    "qwen_vl",
    "qwenvl",
    "textencode",
    "tts",
    "video_understanding",
    "image_understanding",
    "vision_language",
    "visionlanguage",
    "vlm",
)
WORKFLOW_FILE_TRACE_KEYS = (
    "workflow_file_sha256",
    "workflow_prompt_literals",
    "workflow_prompt_literals_sha256",
)


def load_workflow_json(path: str | Path) -> dict[str, Any]:
    workflow_path = Path(path)
    payload = json.loads(workflow_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Workflow file must contain a JSON object: {workflow_path}")
    return payload


def workflow_file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_workflow_file_trace(*workflow_candidates: str | Path | None) -> dict[str, Any]:
    for workflow_candidate in workflow_candidates:
        workflow_path = resolve_workflow_candidate_path(workflow_candidate)
        if workflow_path is None:
            continue
        try:
            workflow = load_workflow_json(workflow_path)
            content_contract = workflow_content_contract(workflow)
        except Exception:
            return {}
        return {
            "workflow_file_sha256": workflow_file_sha256(workflow_path),
            "workflow_prompt_literals": content_contract["prompt_literals"],
            "workflow_prompt_literals_sha256": content_contract[
                "prompt_literals_sha256"
            ],
        }
    return {}


def extract_workflow_file_trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in WORKFLOW_FILE_TRACE_KEYS
        if key in payload
    }


def resolve_workflow_candidate_path(candidate: str | Path | None) -> Path | None:
    if candidate is None:
        return None
    try:
        candidate_text = str(candidate).strip()
        candidate_path = Path(candidate_text)
    except (TypeError, ValueError):
        return None
    if not candidate_text:
        return None
    if candidate_path.is_file():
        return candidate_path

    normalized = candidate_text.replace("\\", "/").strip("/")
    if normalized.startswith("workflows/"):
        rooted_path = Path(get_root_path(normalized))
        if rooted_path.is_file():
            return rooted_path
        normalized = normalized.removeprefix("workflows/")

    parts = [part for part in normalized.split("/") if part]
    if len(parts) < 2:
        return None
    source, rest = parts[0], parts[1:]
    if source == "runninghub":
        descriptor_path = runninghub_descriptor_path("/".join(rest))
        return descriptor_path if descriptor_path.is_file() else None
    if source in {"provider", "selfhost"}:
        try:
            resource_path = Path(get_resource_path("workflows", source, *rest))
        except FileNotFoundError:
            return None
        return resource_path if resource_path.is_file() else None
    return None


def workflow_content_contract(workflow: Mapping[str, Any]) -> dict[str, Any]:
    prompt_literals = workflow_prompt_literals(workflow)
    return {
        "contains_tts_nodes": workflow_contains_tts_nodes(workflow),
        "contains_analysis_nodes": workflow_contains_analysis_nodes(workflow),
        "prompt_literals": prompt_literals,
        "prompt_literals_sha256": workflow_prompt_literals_sha256(prompt_literals),
    }


def workflow_contains_tts_nodes(workflow: Mapping[str, Any]) -> bool:
    return any(
        _node_class_contains_marker(node, TTS_NODE_MARKERS)
        for node in iter_workflow_node_mappings(workflow)
    )


def workflow_contains_analysis_nodes(workflow: Mapping[str, Any]) -> bool:
    return any(
        _node_class_contains_marker(node, ANALYSIS_NODE_MARKERS)
        for node in iter_workflow_node_mappings(workflow)
    )


def workflow_prompt_literals(workflow: Mapping[str, Any]) -> list[dict[str, str]]:
    literals: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for item in _iter_prompt_literal_candidates(workflow):
        if item["path"] in seen_paths:
            continue
        seen_paths.add(item["path"])
        literals.append(item)
    return literals


def workflow_prompt_literals_sha256(literals: Iterable[Mapping[str, Any]]) -> str:
    canonical = json.dumps(
        [
            {
                "path": str(item.get("path") or ""),
                "key": str(item.get("key") or ""),
                "sha256": str(item.get("sha256") or ""),
            }
            for item in literals
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def iter_workflow_node_mappings(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from iter_workflow_node_mappings(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from iter_workflow_node_mappings(child)


def iter_workflow_nodes_with_paths(
    value: Any,
    path: tuple[str, ...] = (),
):
    if isinstance(value, Mapping):
        if "inputs" in value and ("class_type" in value or "type" in value):
            yield path, value
        for key, child in value.items():
            yield from iter_workflow_nodes_with_paths(child, (*path, str(key)))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_workflow_nodes_with_paths(child, (*path, str(index)))


def _iter_prompt_literal_candidates(
    value: Any,
    path: tuple[str, ...] = (),
    node_marker_text: str = "",
):
    if isinstance(value, Mapping):
        current_node_marker_text = _node_marker_text(value) or node_marker_text
        widgets_values = value.get("widgets_values")
        if isinstance(widgets_values, list):
            for index, item in enumerate(widgets_values):
                if not isinstance(item, str):
                    continue
                if not (
                    _node_marker_is_prompt_bearing(current_node_marker_text)
                    or _looks_like_freeform_prompt_literal(item)
                ):
                    continue
                literal = _prompt_literal_item(
                    path=(*path, "widgets_values", str(index)),
                    key=f"widgets_values[{index}]",
                    text=item,
                )
                if literal is not None:
                    yield literal

        for key, child in value.items():
            child_path = (*path, str(key))
            if isinstance(child, str) and _is_prompt_input_key(str(key)):
                literal = _prompt_literal_item(
                    path=child_path,
                    key=str(key),
                    text=child,
                )
                if literal is not None:
                    yield literal
            elif isinstance(child, list) and _is_prompt_input_key(str(key)):
                for index, item in enumerate(child):
                    if not isinstance(item, str):
                        continue
                    literal = _prompt_literal_item(
                        path=(*child_path, str(index)),
                        key=f"{key}[{index}]",
                        text=item,
                    )
                    if literal is not None:
                        yield literal
            yield from _iter_prompt_literal_candidates(
                child,
                child_path,
                current_node_marker_text,
            )
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_prompt_literal_candidates(
                child,
                (*path, str(index)),
                node_marker_text,
            )


def _node_class_contains_marker(
    node: Mapping[str, Any],
    markers: tuple[str, ...],
) -> bool:
    normalized = _node_marker_text(node)
    return any(marker in normalized for marker in markers)


def _node_marker_text(node: Mapping[str, Any]) -> str:
    values = []
    for key in ("class_type", "type", "title", "name"):
        value = node.get(key)
        if isinstance(value, str):
            values.append(value)
    return " ".join(values).strip().lower().replace(" ", "")


def _node_marker_is_prompt_bearing(marker_text: str) -> bool:
    return any(marker in marker_text for marker in PROMPT_NODE_MARKERS)


def _prompt_literal_item(
    *,
    path: tuple[str, ...],
    key: str,
    text: str,
) -> dict[str, str] | None:
    normalized_text = text.strip()
    if not normalized_text or _looks_like_runtime_placeholder(normalized_text):
        return None
    return {
        "path": ".".join(path),
        "key": str(key),
        "sha256": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        "preview": normalized_text[:160],
    }


def _is_prompt_input_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in PROMPT_INPUT_KEYS or normalized.endswith(PROMPT_INPUT_SUFFIXES)


def _looks_like_runtime_placeholder(text: str) -> bool:
    normalized = text.strip()
    if re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_.-]*", normalized):
        return True
    return bool(
        re.fullmatch(
            r"\{\{?\s*[A-Za-z_][A-Za-z0-9_.-]*\s*\}?\}",
            normalized,
        )
    )


def _looks_like_freeform_prompt_literal(text: str) -> bool:
    normalized = text.strip()
    if not normalized or _looks_like_runtime_placeholder(normalized):
        return False
    if len(normalized) < 12:
        return False
    lowered = normalized.lower()
    if any(
        lowered.endswith(suffix)
        for suffix in (
            ".ckpt",
            ".gguf",
            ".json",
            ".mp3",
            ".mp4",
            ".png",
            ".safetensors",
            ".wav",
        )
    ):
        return False
    if "{" in normalized and "}" in normalized:
        return True
    if not any(char.isspace() for char in normalized):
        segments = [
            segment.strip()
            for segment in re.split(r"[,，、]+", normalized)
            if segment.strip()
        ]
        return len(segments) >= 3 and any(char.isalpha() for char in normalized)
    word_count = len([part for part in normalized.replace(",", " ").split() if part])
    if word_count >= 3:
        return True
    if len(normalized) >= 18 and any("\u4e00" <= char <= "\u9fff" for char in normalized):
        return True
    return False
