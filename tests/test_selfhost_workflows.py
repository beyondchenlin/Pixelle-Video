import json
from pathlib import Path

from comfykit.comfyui.workflow_parser import WorkflowParser


def _assert_prompt_mapping_is_declared_once(metadata):
    prompt_mappings = [
        (mapping.node_id, mapping.input_field)
        for mapping in metadata.mapping_info.param_mappings
        if mapping.param_name == "prompt"
    ]

    assert metadata.params["prompt"].required is True
    assert prompt_mappings == [("46", "value")]


def _assert_default_image_size_is_768(workflow_path: str):
    workflow = json.loads(Path(workflow_path).read_text(encoding="utf-8"))

    width_nodes = [
        node for node in workflow.values() if node["_meta"]["title"] == "$width.value"
    ]
    height_nodes = [
        node for node in workflow.values() if node["_meta"]["title"] == "$height.value"
    ]

    assert len(width_nodes) == 1
    assert len(height_nodes) == 1
    assert width_nodes[0]["inputs"]["value"] == 768
    assert height_nodes[0]["inputs"]["value"] == 768


def test_image_z_image_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/image_z_image.json"))
    )

    assert set(metadata.params.keys()) == {"prompt", "width", "height"}
    _assert_prompt_mapping_is_declared_once(metadata)


def test_image_z_image_turbo_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/image_z_image_turbo.json"))
    )

    assert set(metadata.params.keys()) == {"prompt", "width", "height"}
    _assert_prompt_mapping_is_declared_once(metadata)


def test_image_z_image_turbo_gguf_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/image_z_image_turbo_gguf.json"))
    )

    assert set(metadata.params.keys()) == {"prompt", "width", "height"}
    _assert_prompt_mapping_is_declared_once(metadata)


def test_image_z_image_turbo_gguf_defaults_to_q4_k_m_models():
    workflow = json.loads(
        Path("workflows/selfhost/image_z_image_turbo_gguf.json").read_text(
            encoding="utf-8"
        )
    )

    assert workflow["37"]["inputs"]["unet_name"] == "z-image-turbo-Q4_K_M.gguf"
    assert workflow["38"]["inputs"]["clip_name"] == "Qwen3-4B-Q4_K_M.gguf"


def test_image_z_image_turbo_gguf_doc_declares_easy_use_dependency():
    doc = Path(
        "workflows/down/image_z_image_turbo_gguf_\u4f9d\u8d56\u4e0e\u4e0b\u8f7d\u8bf4\u660e.md"
    ).read_text(encoding="utf-8")

    assert "ComfyUI-Easy-Use" in doc
    assert "easy int" in doc


def test_standard_image_workflows_default_to_768_square():
    workflow_paths = [
        "workflows/selfhost/image_z_image.json",
        "workflows/selfhost/image_z_image_turbo.json",
        "workflows/selfhost/image_z_image_turbo_gguf.json",
        "workflows/selfhost/image_qwen.json",
        "workflows/selfhost/image_flux.json",
    ]

    for workflow_path in workflow_paths:
        _assert_default_image_size_is_768(workflow_path)


def test_image_qwen_edit_2511_gguf_q4_k_m_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/image_qwen_edit_2511_gguf_q4_k_m.json"))
    )

    assert set(metadata.params.keys()) == {"prompt", "image", "image2", "seed", "steps", "cfg"}
    assert metadata.params["prompt"].required is True
    assert metadata.params["image"].required is True
    assert metadata.params["image"].need_upload is True
    assert metadata.params["image2"].required is True
    assert metadata.params["image2"].need_upload is True
    assert metadata.params["seed"].required is False
    assert metadata.params["steps"].required is False
    assert metadata.params["cfg"].required is False

    mappings = {
        mapping.param_name: (mapping.node_id, mapping.input_field, mapping.need_upload)
        for mapping in metadata.mapping_info.param_mappings
    }
    assert mappings == {
        "image": ("7", "image", True),
        "image2": ("9", "image", True),
        "prompt": ("10", "prompt", False),
        "seed": ("15", "seed", False),
        "steps": ("15", "steps", False),
        "cfg": ("15", "cfg", False),
    }


def test_tts_index2_uses_builtin_multiline_string_input():
    workflow = json.loads(Path("workflows/selfhost/tts_index2.json").read_text(encoding="utf-8"))

    assert workflow["3"]["class_type"] == "PrimitiveStringMultiline"
    assert workflow["3"]["inputs"]["value"] == "IndexTTS2 sample input."
    assert workflow["3"]["_meta"]["title"] == "$text.value!"


def test_tts_index2_exposes_only_current_workflow_inputs():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_index2.json"))
    )

    assert set(metadata.params.keys()) == {"text", "ref_audio"}


def test_tts_index2_treats_ref_audio_as_uploaded_audio():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_index2.json"))
    )

    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True

    mappings = {
        mapping.param_name: (mapping.node_id, mapping.input_field, mapping.need_upload)
        for mapping in metadata.mapping_info.param_mappings
    }
    assert mappings["ref_audio"] == ("12", "audio", True)


def test_tts_longcat_clone_workflow_is_parseable_and_modelscope_first():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_longcat_clone.json"))
    )
    workflow = json.loads(
        Path("workflows/selfhost/tts_longcat_clone.json").read_text(encoding="utf-8")
    )

    assert set(metadata.params.keys()) == {"text", "ref_audio", "prompt_text"}
    assert metadata.params["text"].required is True
    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True
    assert metadata.params["prompt_text"].required is False

    mappings = {
        mapping.param_name: (mapping.node_id, mapping.input_field, mapping.need_upload)
        for mapping in metadata.mapping_info.param_mappings
    }
    assert mappings == {
        "text": ("3", "value", False),
        "ref_audio": ("4", "audio", True),
        "prompt_text": ("5", "value", False),
    }

    assert workflow["2"]["class_type"] == "LongCatVoiceCloneTTS"
    assert workflow["2"]["inputs"]["model_path"] == "LongCat-AudioDiT-1B"
    assert "auto download" not in workflow["2"]["inputs"]["model_path"].lower()
    assert workflow["2"]["inputs"]["prompt_audio"] == ["4", 0]
    assert workflow["2"]["inputs"]["prompt_text"] == ["5", 0]


def test_tts_index2_keeps_models_cached_between_runs():
    workflow = json.loads(Path("workflows/selfhost/tts_index2.json").read_text(encoding="utf-8"))

    cache_nodes = {
        node_id: node
        for node_id, node in workflow.items()
        if node["class_type"] == "IndexTTS2CacheControlNode"
    }

    assert len(cache_nodes) == 1

    cache_node_id, cache_node = next(iter(cache_nodes.items()))
    assert cache_node["inputs"]["keep_models_cached"] is True
    assert workflow["5"]["inputs"]["cache_control"] == [cache_node_id, 0]


def test_tts_index2_uses_safer_sentence_token_cap():
    workflow = json.loads(Path("workflows/selfhost/tts_index2.json").read_text(encoding="utf-8"))

    assert workflow["5"]["inputs"]["max_tokens_per_sentence"] == 90


def test_tts_edge_workflow_is_parseable_and_uses_pixelle_nodes():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_edge.json"))
    )
    workflow = json.loads(Path("workflows/selfhost/tts_edge.json").read_text(encoding="utf-8"))

    assert set(metadata.params.keys()) == {"text", "voice", "speed"}
    assert metadata.params["text"].required is True
    assert metadata.params["voice"].required is False
    assert metadata.params["speed"].required is False

    mappings = {
        mapping.param_name: (mapping.node_id, mapping.input_field)
        for mapping in metadata.mapping_info.param_mappings
    }
    assert mappings == {
        "text": ("3", "value"),
        "voice": ("7", "value"),
        "speed": ("8", "value"),
    }

    assert workflow["1"]["class_type"] == "PixelleEdgeTTS"
    assert workflow["3"]["class_type"] == "PrimitiveStringMultiline"
    assert workflow["3"]["inputs"]["value"] == "\u5e8a\u524d\u660e\u6708\u5149\uff0c\u7591\u662f\u5730\u4e0a\u971c\u3002"
    assert workflow["3"]["_meta"]["title"] == "$text.value!"
    assert workflow["7"]["class_type"] == "PrimitiveStringMultiline"
    assert workflow["7"]["inputs"]["value"] == "zh-CN-YunjianNeural"
    assert workflow["7"]["_meta"]["title"] == "$voice.value"
    assert workflow["8"]["class_type"] == "PixelleFloatInput"
    assert workflow["8"]["inputs"]["value"] == 1.0
    assert workflow["8"]["_meta"]["title"] == "$speed.value"

    class_types = {node["class_type"] for node in workflow.values()}
    assert "EdgeTTS" not in class_types
    assert "easy showAnything" not in class_types
    assert "easy float" not in class_types
