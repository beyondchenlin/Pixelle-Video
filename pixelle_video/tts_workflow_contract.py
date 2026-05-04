import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from pixelle_video.tts_workflow_family import infer_tts_workflow_family

INDEX_TTS2_WORKFLOW_STEMS = frozenset({"tts_index2", "indextts2", "index_tts2"})
INDEX_TTS2_NODE_CLASS_TYPES = frozenset(
    {
        "IndexTTS2BaseNode",
        "IndexTTS2CacheControlNode",
    }
)
REF_AUDIO_TEXT_WORKFLOW_PARAMS = ("prompt_text", "reference_audio_text")
SAVE_AUDIO_OUTPUT_EXTENSIONS = {
    "SaveAudio": ".flac",
    "SaveAudioMP3": ".mp3",
    "SaveAudioOpus": ".opus",
}


def is_index_tts2_workflow_key(workflow_key: Any) -> bool:
    return infer_tts_workflow_family(workflow_key) == "indextts2"


def is_index_tts2_workflow(workflow: Mapping[str, Any] | None) -> bool:
    if not isinstance(workflow, Mapping):
        return False

    for value in workflow.values():
        if not isinstance(value, Mapping):
            continue

        class_type = value.get("class_type")
        if _is_index_tts2_node_class_type(class_type):
            return True

        if is_index_tts2_workflow(value):
            return True

    return False


def is_index_tts2_workflow_file(workflow_path: str | Path | None) -> bool:
    workflow = _load_workflow_from_file(workflow_path)
    if workflow is not None:
        return is_index_tts2_workflow(workflow)

    return _is_index_tts2_workflow_stem(workflow_path)


def is_index_tts2_workflow_info(workflow_info: Mapping[str, Any] | None) -> bool:
    if not isinstance(workflow_info, Mapping):
        return False

    if str(workflow_info.get("source") or "selfhost").lower() == "selfhost":
        workflow = _load_workflow_from_file(workflow_info.get("path"))
        if workflow is not None:
            return is_index_tts2_workflow(workflow)

    return _is_index_tts2_workflow_stem(workflow_info.get("key"))


def _is_index_tts2_node_class_type(class_type: Any) -> bool:
    if not isinstance(class_type, str):
        return False

    return class_type.startswith("IndexTTS2") or class_type in INDEX_TTS2_NODE_CLASS_TYPES


def _is_index_tts2_workflow_stem(workflow_key: Any) -> bool:
    workflow_stem = Path(str(workflow_key or "")).stem.lower()
    return workflow_stem in INDEX_TTS2_WORKFLOW_STEMS


def _load_workflow_from_file(workflow_path: str | Path | None) -> Mapping[str, Any] | None:
    if not workflow_path:
        return None

    path = Path(workflow_path)
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as handle:
            workflow = json.load(handle)
    except Exception:
        return None

    return workflow if isinstance(workflow, Mapping) else None


def _load_workflow_from_key(workflow_key: Any) -> Mapping[str, Any] | None:
    if not workflow_key:
        return None

    key_path = Path(str(workflow_key))
    candidates = [key_path, Path("workflows") / key_path]
    if len(key_path.parts) == 1:
        candidates.append(Path("workflows") / "selfhost" / key_path)

    for candidate in candidates:
        workflow = _load_workflow_from_file(candidate)
        if workflow is not None:
            return workflow

    return None


def build_ref_audio_text_params(
    ref_audio_text: Any,
    workflow_param_names: Iterable[str] | None,
) -> dict[str, str]:
    text = str(ref_audio_text or "").strip()
    if not text:
        return {}

    param_names = set(workflow_param_names or ())
    if not param_names:
        return {"prompt_text": text}

    return {
        param_name: text
        for param_name in REF_AUDIO_TEXT_WORKFLOW_PARAMS
        if param_name in param_names
    }


def resolve_workflow_output_audio_extension(
    workflow: Mapping[str, Any] | None,
    *,
    default: str | None = ".mp3",
) -> str | None:
    """Return the output audio extension declared by ComfyUI SaveAudio nodes."""
    if not isinstance(workflow, Mapping):
        return default

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
        if not isinstance(class_type, str):
            continue

        extension = SAVE_AUDIO_OUTPUT_EXTENSIONS.get(class_type)
        if extension:
            return extension

    return default


def resolve_workflow_output_audio_extension_from_file(
    workflow_path: str | Path | None,
    *,
    default: str | None = ".mp3",
) -> str | None:
    if not workflow_path:
        return default

    path = Path(workflow_path)
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as handle:
            workflow = json.load(handle)
    except Exception:
        return default

    return resolve_workflow_output_audio_extension(workflow, default=default)


def resolve_workflow_output_audio_extension_from_info(
    workflow_info: Mapping[str, Any] | None,
    *,
    default: str | None = ".mp3",
) -> str | None:
    if not isinstance(workflow_info, Mapping):
        return default

    if str(workflow_info.get("source") or "selfhost").lower() != "selfhost":
        return default

    return resolve_workflow_output_audio_extension_from_file(
        workflow_info.get("path"),
        default=default,
    )


def resolve_workflow_output_audio_extension_from_key(
    workflow_key: Any,
    *,
    default: str | None = ".mp3",
) -> str | None:
    if not workflow_key:
        return default

    key_path = Path(str(workflow_key))
    candidates = [key_path, Path("workflows") / key_path]
    if len(key_path.parts) == 1:
        candidates.append(Path("workflows") / "selfhost" / key_path)

    for candidate in candidates:
        extension = resolve_workflow_output_audio_extension_from_file(
            candidate,
            default=None,
        )
        if extension:
            return extension

    return default
