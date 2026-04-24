# VoxCPM2 ComfyUI Dual Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Pixelle selfhost TTS workflows for both `ComfyUI_RH_VoxCPM` and `ComfyUI-VoxCPM2`, with ModelScope-first dependency documentation.

**Architecture:** Pixelle already discovers `tts_*.json` workflows from `workflows/selfhost`. The implementation adds four API-format ComfyUI workflows and tests their ComfyKit parameter mappings, without changing `TTSService`.

**Tech Stack:** Python, pytest, ComfyKit `WorkflowParser`, ComfyUI API workflow JSON, ModelScope.

---

### Task 1: Add Workflow Parser Tests

**Files:**
- Modify: `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Write failing tests**

Add tests that expect these workflow files and contracts:

```python
def test_tts_voxcpm2_rh_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_voxcpm2_rh.json"))
    )
    workflow = json.loads(Path("workflows/selfhost/tts_voxcpm2_rh.json").read_text(encoding="utf-8"))

    assert {"text", "voice_description", "cfg_value", "inference_steps", "seed", "max_len", "normalize_text"} <= set(metadata.params)
    assert metadata.params["text"].required is True
    assert workflow["1"]["class_type"] == "RunningHub_VoxCPM_LoadModel"
    assert workflow["2"]["class_type"] == "RunningHub_VoxCPM_Generate"
    assert workflow["3"]["class_type"] == "SaveAudio"


def test_tts_voxcpm2_rh_clone_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_voxcpm2_rh_clone.json"))
    )

    assert metadata.params["text"].required is True
    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True


def test_tts_voxcpm2_saganaki_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_voxcpm2_saganaki.json"))
    )
    workflow = json.loads(Path("workflows/selfhost/tts_voxcpm2_saganaki.json").read_text(encoding="utf-8"))

    assert {"text", "voice_description", "cfg_value", "inference_timesteps", "seed", "max_tokens", "normalize_text"} <= set(metadata.params)
    assert metadata.params["text"].required is True
    assert workflow["1"]["class_type"] == "VoxCPM2_TTS"
    assert workflow["2"]["class_type"] == "SaveAudio"


def test_tts_voxcpm2_saganaki_clone_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_voxcpm2_saganaki_clone.json"))
    )
    workflow = json.loads(Path("workflows/selfhost/tts_voxcpm2_saganaki_clone.json").read_text(encoding="utf-8"))

    assert metadata.params["text"].required is True
    assert metadata.params["ref_audio"].required is True
    assert metadata.params["ref_audio"].need_upload is True
    assert workflow["2"]["class_type"] == "VoxCPM2_Clone"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_selfhost_workflows.py -k voxcpm2 -v`

Expected: fail because the four workflow files do not exist.

### Task 2: Add VoxCPM2 Workflow Files

**Files:**
- Create: `workflows/selfhost/tts_voxcpm2_rh.json`
- Create: `workflows/selfhost/tts_voxcpm2_rh_clone.json`
- Create: `workflows/selfhost/tts_voxcpm2_saganaki.json`
- Create: `workflows/selfhost/tts_voxcpm2_saganaki_clone.json`

- [ ] **Step 1: Create RunningHub TTS workflow**

Use `RunningHub_VoxCPM_LoadModel`, `RunningHub_VoxCPM_Generate`, and `SaveAudio`. Mark `text` as required with `$text.text!` and optional controls via node titles.

- [ ] **Step 2: Create RunningHub clone workflow**

Add `VHS_LoadAudioUpload` titled `$ref_audio.audio!`, connect it to `RunningHub_VoxCPM_Generate.reference_audio`, and keep the same optional generation controls.

- [ ] **Step 3: Create Saganaki TTS workflow**

Use `VoxCPM2_TTS` and `SaveAudio`. Mark `text` as required with `$text.text!` and expose `voice_description`, `cfg_value`, `inference_timesteps`, `max_tokens`, `normalize_text`, and `seed`.

- [ ] **Step 4: Create Saganaki clone workflow**

Use `VHS_LoadAudioUpload`, `VoxCPM2_Clone`, and `SaveAudio`. Mark `ref_audio` as upload-required and expose clone-specific optional controls.

- [ ] **Step 5: Run parser tests**

Run: `uv run pytest tests/test_selfhost_workflows.py -k voxcpm2 -v`

Expected: all VoxCPM2 workflow parser tests pass.

### Task 3: Add Dependency Documentation

**Files:**
- Create: `workflows/down/tts_voxcpm2_依赖与下载说明.md`

- [ ] **Step 1: Document plugin sources**

Record GitHub URLs and install commands for both node packages:

```powershell
cd E:\comfyui\comfyui\custom_nodes
git clone https://github.com/HM-RunningHub/ComfyUI_RH_VoxCPM.git
git clone https://github.com/Saganaki22/ComfyUI-VoxCPM2.git
E:\comfyui\resources\uv\win\uv.exe pip install --python E:\comfyui-venv\.venv\Scripts\python.exe -r E:\comfyui\comfyui\custom_nodes\ComfyUI_RH_VoxCPM\requirements.txt
E:\comfyui\resources\uv\win\uv.exe pip install --python E:\comfyui-venv\.venv\Scripts\python.exe -e E:\comfyui\comfyui\custom_nodes\ComfyUI-VoxCPM2
```

- [ ] **Step 2: Document ModelScope downloads**

Use the ComfyUI runtime Python:

```powershell
E:\comfyui\resources\uv\win\uv.exe pip install --python E:\comfyui-venv\.venv\Scripts\python.exe modelscope

@'
from modelscope import snapshot_download
snapshot_download("OpenBMB/VoxCPM2", local_dir=r"E:\comfyui\comfyui\models\voxcpm\VoxCPM2")
snapshot_download("iic/SenseVoiceSmall", local_dir=r"E:\comfyui\comfyui\models\SenseVoice\SenseVoiceSmall")
snapshot_download("iic/speech_zipenhancer_ans_multiloss_16k_base", local_dir=r"E:\comfyui\comfyui\models\voxcpm\speech_zipenhancer_ans_multiloss_16k_base")
'@ | & E:\comfyui-venv\.venv\Scripts\python.exe -
```

- [ ] **Step 3: Document junction for shared model storage**

Document:

```powershell
New-Item -ItemType Directory -Force -Path 'E:\comfyui\comfyui\models\tts\VoxCPM'
cmd /c mklink /J "E:\comfyui\comfyui\models\tts\VoxCPM\VoxCPM2" "E:\comfyui\comfyui\models\voxcpm\VoxCPM2"
```

- [ ] **Step 4: Run documentation and workflow tests**

Run: `uv run pytest tests/test_selfhost_workflows.py -v`

Expected: existing workflow tests and new VoxCPM2 tests pass.

### Task 4: Verify Scope

**Files:**
- Verify: `git diff -- tests/test_selfhost_workflows.py workflows/selfhost workflows/down docs/superpowers`

- [ ] **Step 1: Inspect diff**

Run: `git diff -- tests/test_selfhost_workflows.py workflows/selfhost workflows/down docs/superpowers`

Expected: diff only contains VoxCPM2 workflow, tests, and documentation changes.

- [ ] **Step 2: Final verification**

Run: `uv run pytest tests/test_selfhost_workflows.py -v`

Expected: all tests in the file pass.
