import json
from pathlib import Path

from comfykit.comfyui.workflow_parser import WorkflowParser


def test_tts_longcat_workflow_is_parseable_and_modelscope_first():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_longcat.json"))
    )
    workflow = json.loads(
        Path("workflows/selfhost/tts_longcat.json").read_text(encoding="utf-8")
    )

    assert {
        "text",
        "steps",
        "guidance_strength",
        "guidance_method",
        "device",
        "dtype",
        "attention",
        "seed",
        "keep_model_loaded",
    } <= set(metadata.params)
    assert metadata.params["text"].required is True
    assert "ref_audio" not in metadata.params
    assert workflow["1"]["class_type"] == "LongCatTTS"
    assert workflow["1"]["inputs"]["model_path"] == "LongCat-AudioDiT-1B"
    assert "auto download" not in workflow["1"]["inputs"]["model_path"].lower()
    assert workflow["2"]["class_type"] == "SaveAudioMP3"


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
    assert workflow["2"]["class_type"] == "LongCatVoiceCloneTTS"
    assert workflow["2"]["inputs"]["model_path"] == "LongCat-AudioDiT-1B"
    assert "auto download" not in workflow["2"]["inputs"]["model_path"].lower()


def test_tts_longcat_docs_are_modelscope_first():
    docs = [
        Path("workflows/down/tts_longcat_依赖与下载说明.md"),
        Path("workflows/down/tts_longcat_clone_依赖与下载说明.md"),
    ]

    for doc_path in docs:
        doc = doc_path.read_text(encoding="utf-8")
        assert "Saganaki22/ComfyUI-LongCat-AudioDIT-TTS" in doc
        assert "ModelScope" in doc
        assert "meituan-longcat/LongCat-AudioDiT-1B" in doc
        assert "Hugging Face" in doc
        assert doc.index("ModelScope") < doc.index("Hugging Face")
