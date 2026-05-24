from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Mapping

from pixelle_video.runninghub_workflow_contracts import (
    runninghub_descriptor_domains,
    validate_runninghub_descriptor_contract,
)

TtsWorkflowFamily = Literal["edge", "indextts2", "omnivoice", "generic"]

EDGE_NODE_TYPES = frozenset({"PixelleEdgeTTS", "EdgeTTS"})
INDEX_TTS2_NODE_TYPES = frozenset({"IndexTTS2BaseNode", "IndexTTS2CacheControlNode"})
OMNIVOICE_NODE_TYPES = frozenset(
    {
        "OmniVoiceLongformTTS",
        "OmniVoiceVoiceCloneTTS",
        "OmniVoiceVoiceDesignTTS",
        "OmniVoiceMultiSpeakerTTS",
    }
)
OMNIVOICE_LONGFORM_NODE_TYPES = frozenset({"OmniVoiceLongformTTS"})


def infer_tts_workflow_family(workflow_key: Any) -> TtsWorkflowFamily:
    workflow = _load_workflow_from_key(workflow_key)
    family = _infer_family_from_workflow(workflow)
    if family is not None:
        return family
    return _infer_family_from_stem(workflow_key)


def is_known_tts_workflow_resource(workflow_key: Any) -> bool:
    resource_path, workflow = _load_workflow_resource(workflow_key)
    if not isinstance(workflow, Mapping):
        return False
    if _infer_family_from_workflow(workflow) is not None:
        return True
    return _is_known_runninghub_tts_descriptor(
        workflow_key,
        resource_path=resource_path,
        workflow=workflow,
    )


def is_tts_workflow_family(workflow_key: Any, family: TtsWorkflowFamily) -> bool:
    return infer_tts_workflow_family(workflow_key) == family


def is_omnivoice_workflow_key(workflow_key: Any) -> bool:
    return is_tts_workflow_family(workflow_key, "omnivoice")


def is_omnivoice_longform_workflow_key(workflow_key: Any) -> bool:
    workflow = _load_workflow_from_key(workflow_key)
    if workflow is not None:
        return _contains_node_class_type(workflow, OMNIVOICE_LONGFORM_NODE_TYPES)

    stem = Path(str(workflow_key or "")).stem.lower().replace("-", "_")
    return "omnivoice" in stem and "longform" in stem


def _infer_family_from_workflow(workflow: Mapping[str, Any] | None) -> TtsWorkflowFamily | None:
    if not isinstance(workflow, Mapping):
        return None

    for node in _iter_workflow_node_mappings(workflow):
        nested_family = _infer_family_from_node_mapping(node)
        if nested_family:
            return nested_family

    return None


def _infer_family_from_node_mapping(node: Mapping[str, Any]) -> TtsWorkflowFamily | None:
    class_type = node.get("class_type")
    if not isinstance(class_type, str):
        class_type = node.get("type")
    if not isinstance(class_type, str):
        return None
    if class_type in OMNIVOICE_NODE_TYPES or class_type.startswith("OmniVoice"):
        return "omnivoice"
    if class_type in INDEX_TTS2_NODE_TYPES or class_type.startswith("IndexTTS2"):
        return "indextts2"
    if class_type in EDGE_NODE_TYPES:
        return "edge"
    return None


def _contains_node_class_type(
    workflow: Mapping[str, Any] | None,
    class_types: frozenset[str],
) -> bool:
    if not isinstance(workflow, Mapping):
        return False

    for node in _iter_workflow_node_mappings(workflow):
        class_type = node.get("class_type")
        if not isinstance(class_type, str):
            class_type = node.get("type")
        if isinstance(class_type, str) and class_type in class_types:
            return True

    return False


def _infer_family_from_stem(workflow_key: Any) -> TtsWorkflowFamily:
    stem = Path(str(workflow_key or "")).stem.lower().replace("-", "_")
    if "omnivoice" in stem:
        return "omnivoice"
    if stem in {"tts_index2", "tts_index2_8g", "indextts2", "index_tts2"}:
        return "indextts2"
    if "edge" in stem:
        return "edge"
    return "generic"


def _load_workflow_from_key(workflow_key: Any) -> Mapping[str, Any] | None:
    _resource_path, workflow = _load_workflow_resource(workflow_key)
    return workflow


def _load_workflow_resource(
    workflow_key: Any,
) -> tuple[Path | None, Mapping[str, Any] | None]:
    if isinstance(workflow_key, Mapping):
        return None, workflow_key
    if not workflow_key:
        return None, None

    for candidate in _resolve_workflow_path_candidates(workflow_key):
        if not candidate.exists():
            continue
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(value, Mapping):
            return candidate, value

    return None, None


def _resolve_workflow_path_candidates(workflow_key: Any) -> tuple[Path, ...]:
    key_path = Path(str(workflow_key))
    candidates = [key_path, Path("workflows") / key_path]
    if len(key_path.parts) == 1:
        candidates.append(Path("workflows") / "selfhost" / key_path)

    resolved_candidates = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        resolved_candidates.append(candidate)
    return tuple(resolved_candidates)


def _iter_workflow_node_mappings(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_workflow_node_mappings(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from _iter_workflow_node_mappings(child)


def _is_known_runninghub_tts_descriptor(
    workflow_key: Any,
    *,
    resource_path: Path | None,
    workflow: Mapping[str, Any],
) -> bool:
    source = str(workflow.get("source") or "").strip().lower()
    workflow_id = str(workflow.get("workflow_id") or "").strip()
    if source != "runninghub" or not workflow_id or resource_path is None:
        return False

    try:
        workflow = validate_runninghub_descriptor_contract(resource_path, workflow)
    except ValueError:
        return False
    declared_domains = {
        domain
        for domain in runninghub_descriptor_domains(workflow)
        if domain is not None
    }
    return "tts" in declared_domains
