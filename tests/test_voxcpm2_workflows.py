import json
from pathlib import Path

from comfykit.comfyui.workflow_parser import WorkflowParser


def test_tts_voxcpm2_rh_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_voxcpm2_rh.json"))
    )
    workflow = json.loads(Path("workflows/selfhost/tts_voxcpm2_rh.json").read_text(encoding="utf-8"))

    assert {
        "text",
        "voice_description",
        "cfg_value",
        "inference_steps",
        "seed",
        "max_len",
        "normalize_text",
    } <= set(metadata.params)
    assert metadata.params["text"].required is True
    assert workflow["1"]["class_type"] == "RunningHub_VoxCPM_LoadModel"
    assert workflow["2"]["class_type"] == "RunningHub_VoxCPM_Generate"
    assert workflow["3"]["class_type"] == "SaveAudioMP3"


def test_tts_voxcpm2_rh_clone_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_voxcpm2_rh_clone.json"))
    )
    workflow = json.loads(
        Path("workflows/selfhost/tts_voxcpm2_rh_clone.json").read_text(encoding="utf-8")
    )

    assert metadata.params["text"].required is True
    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True
    assert workflow["4"]["class_type"] == "VHS_LoadAudioUpload"
    assert workflow["2"]["inputs"]["reference_audio"] == ["4", 0]


def test_tts_voxcpm2_saganaki_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_voxcpm2_saganaki.json"))
    )
    workflow = json.loads(
        Path("workflows/selfhost/tts_voxcpm2_saganaki.json").read_text(encoding="utf-8")
    )

    assert {
        "text",
        "voice_description",
        "cfg_value",
        "inference_timesteps",
        "seed",
        "max_tokens",
        "normalize_text",
    } <= set(metadata.params)
    assert metadata.params["text"].required is True
    assert workflow["1"]["class_type"] == "VoxCPM2_TTS"
    assert workflow["2"]["class_type"] == "SaveAudioMP3"


def test_tts_voxcpm2_saganaki_clone_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_voxcpm2_saganaki_clone.json"))
    )
    workflow = json.loads(
        Path("workflows/selfhost/tts_voxcpm2_saganaki_clone.json").read_text(encoding="utf-8")
    )

    assert metadata.params["text"].required is True
    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True
    assert workflow["1"]["class_type"] == "VHS_LoadAudioUpload"
    assert workflow["2"]["class_type"] == "VoxCPM2_Clone"
    assert workflow["2"]["inputs"]["reference_audio"] == ["1", 0]


def test_tts_voxcpm2_dependency_doc_is_modelscope_first():
    doc = Path("workflows/down/tts_voxcpm2_依赖与下载说明.md").read_text(encoding="utf-8")

    assert "HM-RunningHub/ComfyUI_RH_VoxCPM" in doc
    assert "Saganaki22/ComfyUI-VoxCPM2" in doc
    assert "ModelScope" in doc
    assert "OpenBMB/VoxCPM2" in doc
    assert "Hugging Face" in doc
    assert doc.index("ModelScope") < doc.index("Hugging Face")
