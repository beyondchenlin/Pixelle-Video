from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Mapping

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


def infer_tts_workflow_family(workflow_key: Any) -> TtsWorkflowFamily:
    workflow = _load_workflow_from_key(workflow_key)
    family = _infer_family_from_workflow(workflow)
    if family is not None:
        return family
    return _infer_family_from_stem(workflow_key)


def is_tts_workflow_family(workflow_key: Any, family: TtsWorkflowFamily) -> bool:
    return infer_tts_workflow_family(workflow_key) == family


def is_omnivoice_workflow_key(workflow_key: Any) -> bool:
    return is_tts_workflow_family(workflow_key, "omnivoice")


def _infer_family_from_workflow(workflow: Mapping[str, Any] | None) -> TtsWorkflowFamily | None:
    if not isinstance(workflow, Mapping):
        return None

    nodes = workflow
    for wrapper_key in ("workflow", "prompt"):
        wrapped = workflow.get(wrapper_key)
        if isinstance(wrapped, Mapping):
            nodes = wrapped
            break

    for node in nodes.values():
        if not isinstance(node, Mapping):
            continue

        class_type = node.get("class_type")
        if isinstance(class_type, str):
            if class_type in OMNIVOICE_NODE_TYPES or class_type.startswith("OmniVoice"):
                return "omnivoice"
            if class_type in INDEX_TTS2_NODE_TYPES or class_type.startswith("IndexTTS2"):
                return "indextts2"
            if class_type in EDGE_NODE_TYPES:
                return "edge"

        nested_family = _infer_family_from_workflow(node)
        if nested_family is not None:
            return nested_family

    return None


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
    if isinstance(workflow_key, Mapping):
        return workflow_key
    if not workflow_key:
        return None

    key_path = Path(str(workflow_key))
    candidates = [key_path, Path("workflows") / key_path]
    if len(key_path.parts) == 1:
        candidates.append(Path("workflows") / "selfhost" / key_path)

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(value, Mapping):
            return value

    return None
