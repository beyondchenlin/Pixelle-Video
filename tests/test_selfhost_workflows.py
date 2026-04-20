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


def test_tts_index2_uses_builtin_multiline_string_input():
    workflow = json.loads(Path("workflows/selfhost/tts_index2.json").read_text(encoding="utf-8"))

    assert workflow["3"]["class_type"] == "PrimitiveStringMultiline"
    assert workflow["3"]["inputs"]["value"] == "床前明月光，疑是地上霜。"
    assert workflow["3"]["_meta"]["title"] == "$text.value!"


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
    assert workflow["3"]["inputs"]["value"] == "床前明月光，疑是地上霜。"
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
