import json
from pathlib import Path

from comfykit.comfyui.workflow_parser import WorkflowParser

OMNIVOICE_UI_WORKFLOW_PATHS = (
    Path("workflows/selfhost/OmniVoice_all.json"),
    Path("workflows/selfhost/OmniVoice_bf16.json"),
)

OMNIVOICE_API_WORKFLOW_PATHS = (
    Path("workflows/selfhost/tts_omnivoice_longform_bf16.json"),
    Path("workflows/selfhost/tts_omnivoice_clone_duration_bf16.json"),
)

OMNIVOICE_DEPENDENCY_DOCS = {
    "OmniVoice_all": Path(
        "workflows/down/OmniVoice_all_\u4f9d\u8d56\u4e0e\u4e0b\u8f7d\u8bf4\u660e.md"
    ),
    "OmniVoice_bf16": Path(
        "workflows/down/OmniVoice_bf16_\u4f9d\u8d56\u4e0e\u4e0b\u8f7d\u8bf4\u660e.md"
    ),
}

OMNIVOICE_WIDGET_COUNTS = {
    "OmniVoiceWhisperLoader": 3,
    "OmniVoiceVoiceDesignTTS": 19,
    "OmniVoiceVoiceCloneTTS": 21,
    "OmniVoiceLongformTTS": 22,
    "OmniVoiceMultiSpeakerTTS": 22,
}


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


def _load_ui_workflow(path: Path):
    workflow = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(workflow.get("nodes"), list)
    assert isinstance(workflow.get("links"), list)

    return workflow


def _node_by_id(workflow: dict, node_id: int):
    return next(node for node in workflow["nodes"] if node["id"] == node_id)


def _iter_strings(value, path="root"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_strings(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_strings(item, f"{path}.{key}")


def _nodes_by_type(workflow: dict, node_type: str):
    return [node for node in workflow["nodes"] if node["type"] == node_type]


def _links_by_id(workflow: dict):
    return {link[0]: link for link in workflow["links"]}


def test_omnivoice_ui_workflows_are_valid_json_graphs():
    for workflow_path in OMNIVOICE_UI_WORKFLOW_PATHS:
        workflow = _load_ui_workflow(workflow_path)

        assert workflow["version"] == 0.4
        assert workflow["nodes"]
        assert workflow["links"]


def test_omnivoice_nodes_use_current_widget_layout():
    for workflow_path in OMNIVOICE_UI_WORKFLOW_PATHS:
        workflow = _load_ui_workflow(workflow_path)

        for node in workflow["nodes"]:
            expected_widget_count = OMNIVOICE_WIDGET_COUNTS.get(node["type"])
            if expected_widget_count is None:
                continue

            assert len(node.get("widgets_values", [])) == expected_widget_count, (
                workflow_path,
                node["id"],
                node["type"],
            )


def test_omnivoice_ui_workflows_keep_only_linked_node_inputs():
    checked_node_count = 0

    for workflow_path in OMNIVOICE_UI_WORKFLOW_PATHS:
        workflow = _load_ui_workflow(workflow_path)

        for node in workflow["nodes"]:
            if node["type"] not in OMNIVOICE_WIDGET_COUNTS:
                continue

            checked_node_count += 1
            stale_inputs = [
                input_spec["name"]
                for input_spec in node.get("inputs", [])
                if input_spec.get("link") is None
            ]

            assert stale_inputs == [], (workflow_path, node["id"], node["type"])

    assert checked_node_count > 0


def test_omnivoice_ui_workflows_do_not_contain_mojibake_or_private_use_text():
    forbidden_fragments = ("锟", "鐠", "鈥", "�")

    for workflow_path in OMNIVOICE_UI_WORKFLOW_PATHS:
        workflow = _load_ui_workflow(workflow_path)

        for string_path, value in _iter_strings(workflow):
            assert not any(fragment in value for fragment in forbidden_fragments), (
                workflow_path,
                string_path,
                value,
            )
            assert not any("\ue000" <= char <= "\uf8ff" for char in value), (
                workflow_path,
                string_path,
                value,
            )


def test_omnivoice_all_workflow_uses_intentional_readable_defaults():
    workflow = _load_ui_workflow(Path("workflows/selfhost/OmniVoice_all.json"))

    assert [group["title"] for group in workflow["groups"]] == [
        "Voice Clone",
        "Longform TTS",
        "Voice Design",
        "Multi-Speaker TTS",
    ]

    expected_titles = {
        14: "OmniVoice Whisper Loader",
        4: "OmniVoice Voice Design",
        28: "OmniVoice Voice Clone",
        24: "OmniVoice Multi-Speaker TTS",
        12: "OmniVoice Longform TTS",
        11: "OmniVoice Whisper Loader",
    }
    for node_id, expected_title in expected_titles.items():
        assert _node_by_id(workflow, node_id)["title"] == expected_title

    assert _node_by_id(workflow, 4)["widgets_values"][1:3] == [
        "Hello! This is a clean OmniVoice voice design test for local ComfyUI.",
        "female, young, medium pitch, british accent",
    ]
    assert _node_by_id(workflow, 28)["widgets_values"][1:3] == [
        "This is a clean OmniVoice voice clone test for local ComfyUI.",
        "This reference audio demonstrates the speaker's natural tone.",
    ]
    assert _node_by_id(workflow, 12)["widgets_values"][1:3] == [
        (
            "This is a longer OmniVoice local test paragraph. "
            "It checks voice continuity across multiple sentences in ComfyUI."
        ),
        "This reference audio demonstrates a calm and natural speaking style.",
    ]
    assert _node_by_id(workflow, 24)["widgets_values"][1] == (
        "[Speaker_1]: Hello, this is speaker one.\n"
        "[Speaker_2]: Hello, this is speaker two.\n"
        "[Speaker_1]: The OmniVoice local workflow is ready."
    )
    assert _node_by_id(workflow, 24)["widgets_values"][20:22] == [
        "Speaker one has a clear and warm voice.",
        "Speaker two has a calm and steady voice.",
    ]

    note = _node_by_id(workflow, 22)["widgets_values"][0]
    assert "ModelScope first" in note
    assert "E:\\ComfyUIData\\models\\omnivoice" in note
    assert "Auto-Download" not in note


def test_omnivoice_bf16_workflow_uses_intentional_readable_defaults():
    workflow = _load_ui_workflow(Path("workflows/selfhost/OmniVoice_bf16.json"))

    assert [group["title"] for group in workflow["groups"]] == [
        "OmniVoice BF16 Voice Clone"
    ]

    clean_prompt = (
        "Generate a short, natural voice clone sample for the local OmniVoice workflow."
    )
    assert _node_by_id(workflow, 6)["widgets_values"][1:3] == [clean_prompt, ""]
    prompt_nodes = _nodes_by_type(workflow, "PrimitiveStringMultiline")
    assert len(prompt_nodes) == 1
    assert prompt_nodes[0]["widgets_values"] == [clean_prompt]

    transcribe_nodes = _nodes_by_type(workflow, "PixelleOmniVoiceTranscribe")
    assert len(transcribe_nodes) == 1
    assert transcribe_nodes[0]["title"] == "Reference audio to text"

    preview_nodes = _nodes_by_type(workflow, "PreviewAny")
    assert len(preview_nodes) == 1
    assert preview_nodes[0]["title"] == "Reference transcript preview"


def test_omnivoice_bf16_voice_clone_uses_whisper_like_all_workflow():
    workflow = _load_ui_workflow(Path("workflows/selfhost/OmniVoice_bf16.json"))
    links = _links_by_id(workflow)

    assert _nodes_by_type(workflow, "Qwen3ASRLoader") == []
    assert _nodes_by_type(workflow, "Qwen3ASRTranscribe") == []
    assert _nodes_by_type(workflow, "WhisperSTT") == []
    assert "Qwen/Qwen3-ASR" not in json.dumps(workflow, ensure_ascii=False)

    whisper_nodes = _nodes_by_type(workflow, "OmniVoiceWhisperLoader")
    assert len(whisper_nodes) == 1
    assert whisper_nodes[0]["widgets_values"] == ["whisper-large-v3", "auto", "fp32"]

    transcribe_nodes = _nodes_by_type(workflow, "PixelleOmniVoiceTranscribe")
    assert len(transcribe_nodes) == 1
    transcribe_inputs = {
        input_spec["name"]: input_spec for input_spec in transcribe_nodes[0]["inputs"]
    }
    assert transcribe_inputs["audio"]["type"] == "AUDIO"
    assert transcribe_inputs["whisper_model"]["type"] == "WHISPER_ASR"

    preview_nodes = _nodes_by_type(workflow, "PreviewAny")
    assert len(preview_nodes) == 1
    preview_inputs = {input_spec["name"]: input_spec for input_spec in preview_nodes[0]["inputs"]}

    clone_nodes = _nodes_by_type(workflow, "OmniVoiceVoiceCloneTTS")
    assert len(clone_nodes) == 1
    clone_inputs = {input_spec["name"]: input_spec for input_spec in clone_nodes[0]["inputs"]}

    assert clone_inputs["text"]["type"] == "STRING"
    assert clone_inputs["ref_text"]["type"] == "STRING"
    assert clone_inputs["ref_audio"]["type"] == "AUDIO"
    assert "whisper_model" not in clone_inputs

    prompt_nodes = _nodes_by_type(workflow, "PrimitiveStringMultiline")
    assert len(prompt_nodes) == 1
    text_link = links[clone_inputs["text"]["link"]]
    assert text_link == [
        clone_inputs["text"]["link"],
        prompt_nodes[0]["id"],
        0,
        clone_nodes[0]["id"],
        1,
        "STRING",
    ]

    audio_link = links[transcribe_inputs["audio"]["link"]]
    assert audio_link == [
        transcribe_inputs["audio"]["link"],
        4,
        0,
        transcribe_nodes[0]["id"],
        0,
        "AUDIO",
    ]

    transcribe_whisper_link = links[transcribe_inputs["whisper_model"]["link"]]
    assert transcribe_whisper_link == [
        transcribe_inputs["whisper_model"]["link"],
        whisper_nodes[0]["id"],
        0,
        transcribe_nodes[0]["id"],
        1,
        "WHISPER_ASR",
    ]

    ref_text_link = links[clone_inputs["ref_text"]["link"]]
    assert ref_text_link == [
        clone_inputs["ref_text"]["link"],
        transcribe_nodes[0]["id"],
        0,
        clone_nodes[0]["id"],
        2,
        "STRING",
    ]

    preview_link = links[preview_inputs["source"]["link"]]
    assert preview_link == [
        preview_inputs["source"]["link"],
        transcribe_nodes[0]["id"],
        0,
        preview_nodes[0]["id"],
        0,
        "*",
    ]


def test_omnivoice_load_audio_nodes_default_to_none_for_portability():
    for workflow_path in OMNIVOICE_UI_WORKFLOW_PATHS:
        workflow = _load_ui_workflow(workflow_path)

        for node in workflow["nodes"]:
            if node["type"] != "LoadAudio":
                continue

            assert node["widgets_values"] == ["None", None, None], (
                workflow_path,
                node["id"],
                node["widgets_values"],
            )


def test_omnivoice_dependency_docs_record_modelscope_priority():
    for workflow_name, doc_path in OMNIVOICE_DEPENDENCY_DOCS.items():
        text = doc_path.read_text(encoding="utf-8")

        assert f"workflows/selfhost/{workflow_name}.json" in text
        assert "ModelScope" in text
        assert "E:\\ComfyUIData\\models\\omnivoice" in text
        assert "E:\\ComfyUIData\\custom_nodes" in text
        assert "python -m pytest tests/test_selfhost_workflows.py -k omnivoice -q" in text


def test_omnivoice_dependency_docs_record_current_model_install_state():
    all_doc = OMNIVOICE_DEPENDENCY_DOCS["OmniVoice_all"].read_text(encoding="utf-8")
    assert "当前默认工作流所需模型已存在" in all_doc
    assert "OmniVoice-bf16" in all_doc
    assert "whisper-large-v3" in all_doc
    assert "可选模型尚未下载" in all_doc
    assert "OmniVoice（完整精度）" in all_doc

    bf16_doc = OMNIVOICE_DEPENDENCY_DOCS["OmniVoice_bf16"].read_text(encoding="utf-8")
    assert "当前默认工作流所需模型已存在" in bf16_doc
    assert "OmniVoice-bf16" in bf16_doc
    assert "whisper-large-v3" in bf16_doc
    assert "可选模型尚未下载" in bf16_doc
    assert "whisper-large-v3-turbo" in bf16_doc


def test_omnivoice_docs_remove_qwen_asr_compat_flow():
    bf16_doc = OMNIVOICE_DEPENDENCY_DOCS["OmniVoice_bf16"].read_text(encoding="utf-8")
    all_doc = OMNIVOICE_DEPENDENCY_DOCS["OmniVoice_all"].read_text(encoding="utf-8")

    assert "OmniVoiceWhisperLoader" in bf16_doc
    assert "PixelleOmniVoiceTranscribe" in bf16_doc
    assert "PreviewAny" in bf16_doc
    assert "ComfyUI-Pixelle-TTS" in bf16_doc
    assert "whisper-large-v3" in bf16_doc
    assert "Qwen3-ASR" not in bf16_doc
    assert "qwen-asr" not in bf16_doc
    assert "thinker_config" not in bf16_doc
    assert "sync_omnivoice_qwen_asr_compat.ps1" not in bf16_doc
    assert "sync_omnivoice_qwen_asr_compat.ps1" not in all_doc


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


def test_image_z_image_turbo_gguf_defaults_to_5_sampling_steps():
    workflow = json.loads(
        Path("workflows/selfhost/image_z_image_turbo_gguf.json").read_text(
            encoding="utf-8"
        )
    )

    assert workflow["3"]["class_type"] == "KSampler"
    assert workflow["3"]["inputs"]["steps"] == 5


def test_image_z_image_turbo_gguf_doc_declares_easy_use_dependency():
    doc = Path(
        "workflows/down/image_z_image_turbo_gguf_\u4f9d\u8d56\u4e0e\u4e0b\u8f7d\u8bf4\u660e.md"
    ).read_text(encoding="utf-8")

    assert "ComfyUI-Easy-Use" in doc
    assert "easy int" in doc
    assert "默认采样步数" in doc
    assert "`5`" in doc


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


def test_tts_index2_saves_lossless_flac_audio():
    workflow = json.loads(Path("workflows/selfhost/tts_index2.json").read_text(encoding="utf-8"))

    save_audio_nodes = {
        node_id: node
        for node_id, node in workflow.items()
        if node["class_type"] in {"SaveAudio", "SaveAudioMP3"}
    }

    assert save_audio_nodes == {
        "8": {
            "inputs": {
                "filename_prefix": "audio/ComfyUI",
                "audio": ["5", 0],
            },
            "class_type": "SaveAudio",
            "_meta": {
                "title": "Save Audio (FLAC)",
            },
        }
    }


def test_tts_index2_8g_workflow_is_parseable_and_uses_low_vram_defaults():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_index2_8g.json"))
    )
    workflow = json.loads(Path("workflows/selfhost/tts_index2_8g.json").read_text(encoding="utf-8"))

    assert set(metadata.params.keys()) == {"text", "ref_audio"}
    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True
    assert workflow["5"]["inputs"]["num_beams"] == 1
    assert workflow["5"]["inputs"]["top_k"] == 20
    assert workflow["5"]["inputs"]["max_mel_tokens"] == 800
    assert workflow["5"]["inputs"]["max_tokens_per_sentence"] == 60
    assert workflow["13"]["inputs"]["keep_models_cached"] is True


def test_tts_omnivoice_longform_bf16_workflow_is_parseable_for_pixelle_api():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_omnivoice_longform_bf16.json"))
    )

    assert set(metadata.params.keys()) == {
        "text",
        "ref_audio",
        "reference_audio_text",
    }
    assert metadata.params["text"].required is True
    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True
    assert metadata.params["reference_audio_text"].required is False
    assert metadata.params["reference_audio_text"].default


def test_tts_omnivoice_clone_duration_bf16_workflow_is_parseable_for_pixelle_api():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_omnivoice_clone_duration_bf16.json"))
    )

    assert set(metadata.params.keys()) == {
        "text",
        "ref_audio",
        "reference_audio_text",
        "duration",
    }
    assert metadata.params["text"].required is True
    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True
    assert metadata.params["duration"].required is False
    assert metadata.params["duration"].default == 8.0


def test_tts_omnivoice_longform_bf16_uses_longform_node_and_safe_defaults():
    workflow = json.loads(
        Path("workflows/selfhost/tts_omnivoice_longform_bf16.json").read_text(
            encoding="utf-8"
        )
    )

    longform_nodes = [
        node for node in workflow.values() if node["class_type"] == "OmniVoiceLongformTTS"
    ]
    assert len(longform_nodes) == 1
    inputs = longform_nodes[0]["inputs"]
    assert inputs["model"] == "OmniVoice-bf16"
    assert inputs["device"] == "auto"
    assert inputs["dtype"] == "auto"
    assert inputs["steps"] == 48
    assert inputs["duration"] == 0
    assert inputs["words_per_chunk"] == 100


def test_tts_omnivoice_clone_duration_bf16_uses_voice_clone_node_and_duration_param():
    workflow = json.loads(
        Path("workflows/selfhost/tts_omnivoice_clone_duration_bf16.json").read_text(
            encoding="utf-8"
        )
    )

    clone_nodes = [
        node for node in workflow.values() if node["class_type"] == "OmniVoiceVoiceCloneTTS"
    ]
    assert len(clone_nodes) == 1
    inputs = clone_nodes[0]["inputs"]
    assert inputs["model"] == "OmniVoice-bf16"
    assert inputs["device"] == "auto"
    assert inputs["dtype"] == "auto"
    assert inputs["steps"] == 48
    duration_nodes = [
        node for node in workflow.values() if node["class_type"] == "PixelleDurationInput"
    ]
    assert len(duration_nodes) == 1
    assert duration_nodes[0]["inputs"]["value"] == 8.0
    assert inputs["duration"] == ["8", 0]


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
