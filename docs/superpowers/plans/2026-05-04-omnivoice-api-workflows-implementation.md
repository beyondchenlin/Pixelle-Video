# OmniVoice API Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create two Pixelle-executable OmniVoice bf16 API workflows: one for longform narration and one for short voice-clone generation with target duration.

**Architecture:** Keep the existing ComfyUI UI workflows (`OmniVoice_bf16.json` and `OmniVoice_all.json`) as manual visual debugging assets, and add separate `tts_*.json` API workflows under `workflows/selfhost/` for Pixelle runtime execution. The workflows expose parameters through ComfyKit title markers so `WorkflowParser` can map `text`, `ref_audio`, `reference_audio_text`, and `duration` into ComfyUI nodes.

**Tech Stack:** ComfyUI API workflow JSON, ComfyKit `WorkflowParser`, pytest, OmniVoice bf16 model assets, ModelScope-first dependency documentation.

---

## 关联计划

This plan is the prerequisite for:

- `docs/superpowers/plans/2026-05-04-omnivoice-longform-master-track-implementation.md`

Boundary:

- This plan creates and verifies the two API-format workflow files and their dependency docs.
- The system integration plan handles default TTS switching, saved voice profiles, runtime parameter propagation, and master-track longform block planning.

Do not modify `workflows/selfhost/OmniVoice_bf16.json` or `workflows/selfhost/OmniVoice_all.json` in this plan.

## File Structure

**Create**

- `workflows/selfhost/tts_omnivoice_longform_bf16.json`
- `workflows/selfhost/tts_omnivoice_clone_duration_bf16.json`
- `workflows/down/tts_omnivoice_longform_bf16_依赖与下载说明.md`
- `workflows/down/tts_omnivoice_clone_duration_bf16_依赖与下载说明.md`

**Modify**

- `tests/test_selfhost_workflows.py`

**Reference Only**

- `workflows/selfhost/OmniVoice_bf16.json`
- `workflows/selfhost/OmniVoice_all.json`
- `workflows/down/OmniVoice_bf16_依赖与下载说明.md`
- `workflows/down/OmniVoice_all_依赖与下载说明.md`

---

### Task 1: Add Tests for Parseable OmniVoice API Workflows

**Files:**
- Modify: `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Add API workflow path constants**

Near the existing OmniVoice constants in `tests/test_selfhost_workflows.py`, add:

```python
OMNIVOICE_API_WORKFLOW_PATHS = (
    Path("workflows/selfhost/tts_omnivoice_longform_bf16.json"),
    Path("workflows/selfhost/tts_omnivoice_clone_duration_bf16.json"),
)
```

- [ ] **Step 2: Add failing parser contract tests**

Append these tests to `tests/test_selfhost_workflows.py`:

```python
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
```

- [ ] **Step 3: Add failing workflow structure tests**

Append:

```python
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
    assert inputs["duration"] == ["8", 0]
```

- [ ] **Step 4: Run tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py -k "tts_omnivoice" -v
```

Expected: FAIL because the new workflow files do not exist yet.

- [ ] **Step 5: Commit the failing tests**

```powershell
git add tests/test_selfhost_workflows.py
git commit -m "test: 描述 OmniVoice API 工作流契约"
git push
```

---

### Task 2: Create the Longform OmniVoice API Workflow

**Files:**
- Create: `workflows/selfhost/tts_omnivoice_longform_bf16.json`
- Test: `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Create the longform API workflow**

Create `workflows/selfhost/tts_omnivoice_longform_bf16.json`:

```json
{
  "3": {
    "inputs": {
      "value": "This is an OmniVoice longform narration sample for Pixelle."
    },
    "class_type": "PrimitiveStringMultiline",
    "_meta": {
      "title": "$text.value!"
    }
  },
  "4": {
    "inputs": {
      "value": "This reference audio demonstrates the speaker's natural tone."
    },
    "class_type": "PrimitiveStringMultiline",
    "_meta": {
      "title": "$reference_audio_text.value"
    }
  },
  "5": {
    "inputs": {
      "audio": "ref_audio.wav",
      "start_time": 0,
      "duration": 0
    },
    "class_type": "VHS_LoadAudioUpload",
    "_meta": {
      "title": "$ref_audio.~audio!"
    }
  },
  "6": {
    "inputs": {
      "model": "OmniVoice-bf16",
      "text": [
        "3",
        0
      ],
      "ref_text": [
        "4",
        0
      ],
      "steps": 48,
      "guidance_scale": 2,
      "t_shift": 0.1,
      "speed": 1,
      "duration": 0,
      "device": "auto",
      "dtype": "auto",
      "attention": "auto",
      "seed": 0,
      "words_per_chunk": 100,
      "position_temperature": 3,
      "class_temperature": 0,
      "layer_penalty_factor": 5,
      "denoise": true,
      "preprocess_prompt": true,
      "postprocess_output": true,
      "keep_model_loaded": true,
      "instruct": "",
      "ref_audio": [
        "5",
        0
      ]
    },
    "class_type": "OmniVoiceLongformTTS",
    "_meta": {
      "title": "OmniVoice Longform TTS"
    }
  },
  "7": {
    "inputs": {
      "filename_prefix": "audio/ComfyUI_omnivoice_longform",
      "audio": [
        "6",
        0
      ]
    },
    "class_type": "SaveAudio",
    "_meta": {
      "title": "Save Audio (FLAC)"
    }
  }
}
```

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py -k "tts_omnivoice_longform" -v
```

Expected: PASS for longform tests; clone-duration tests still fail until Task 3.

- [ ] **Step 3: Commit**

```powershell
git add workflows/selfhost/tts_omnivoice_longform_bf16.json
git commit -m "feat: 新增 OmniVoice 长文本 API 工作流"
git push
```

---

### Task 3: Create the Short Clone Duration OmniVoice API Workflow

**Files:**
- Create: `workflows/selfhost/tts_omnivoice_clone_duration_bf16.json`
- Test: `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Create the duration input node workflow**

Create `workflows/selfhost/tts_omnivoice_clone_duration_bf16.json`:

```json
{
  "3": {
    "inputs": {
      "value": "This is a short OmniVoice duration-controlled sample."
    },
    "class_type": "PrimitiveStringMultiline",
    "_meta": {
      "title": "$text.value!"
    }
  },
  "4": {
    "inputs": {
      "value": "This reference audio demonstrates the speaker's natural tone."
    },
    "class_type": "PrimitiveStringMultiline",
    "_meta": {
      "title": "$reference_audio_text.value"
    }
  },
  "5": {
    "inputs": {
      "audio": "ref_audio.wav",
      "start_time": 0,
      "duration": 0
    },
    "class_type": "VHS_LoadAudioUpload",
    "_meta": {
      "title": "$ref_audio.~audio!"
    }
  },
  "8": {
    "inputs": {
      "value": 8.0
    },
    "class_type": "PixelleFloatInput",
    "_meta": {
      "title": "$duration.value"
    }
  },
  "6": {
    "inputs": {
      "model": "OmniVoice-bf16",
      "text": [
        "3",
        0
      ],
      "ref_text": [
        "4",
        0
      ],
      "steps": 48,
      "guidance_scale": 2,
      "t_shift": 0.1,
      "speed": 1,
      "duration": [
        "8",
        0
      ],
      "device": "auto",
      "dtype": "auto",
      "attention": "auto",
      "seed": 0,
      "position_temperature": 3,
      "class_temperature": 0,
      "layer_penalty_factor": 5,
      "denoise": true,
      "preprocess_prompt": true,
      "postprocess_output": true,
      "keep_model_loaded": true,
      "instruct": "",
      "ref_audio": [
        "5",
        0
      ]
    },
    "class_type": "OmniVoiceVoiceCloneTTS",
    "_meta": {
      "title": "OmniVoice Voice Clone TTS"
    }
  },
  "7": {
    "inputs": {
      "filename_prefix": "audio/ComfyUI_omnivoice_clone_duration",
      "audio": [
        "6",
        0
      ]
    },
    "class_type": "SaveAudio",
    "_meta": {
      "title": "Save Audio (FLAC)"
    }
  }
}
```

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py -k "tts_omnivoice_clone_duration" -v
```

Expected: PASS.

- [ ] **Step 3: Run all OmniVoice API workflow tests**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py -k "tts_omnivoice" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add workflows/selfhost/tts_omnivoice_clone_duration_bf16.json
git commit -m "feat: 新增 OmniVoice 定长克隆 API 工作流"
git push
```

---

### Task 4: Add Dependency Docs for the Two API Workflows

**Files:**
- Create: `workflows/down/tts_omnivoice_longform_bf16_依赖与下载说明.md`
- Create: `workflows/down/tts_omnivoice_clone_duration_bf16_依赖与下载说明.md`
- Modify: `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Add failing dependency doc tests**

Append to `tests/test_selfhost_workflows.py`:

```python
def test_tts_omnivoice_api_dependency_docs_record_modelscope_priority():
    docs = {
        "tts_omnivoice_longform_bf16": Path(
            "workflows/down/tts_omnivoice_longform_bf16_依赖与下载说明.md"
        ),
        "tts_omnivoice_clone_duration_bf16": Path(
            "workflows/down/tts_omnivoice_clone_duration_bf16_依赖与下载说明.md"
        ),
    }

    for workflow_name, doc_path in docs.items():
        text = doc_path.read_text(encoding="utf-8")
        assert f"workflows/selfhost/{workflow_name}.json" in text
        assert "ModelScope" in text
        assert "OmniVoice-bf16" in text
        assert "whisper-large-v3" in text
        assert "python -m pytest tests/test_selfhost_workflows.py -k tts_omnivoice -q" in text
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py -k "tts_omnivoice_api_dependency_docs" -v
```

Expected: FAIL because the docs do not exist yet.

- [ ] **Step 3: Write the longform dependency doc**

Create `workflows/down/tts_omnivoice_longform_bf16_依赖与下载说明.md` with these sections:

````markdown
# tts_omnivoice_longform_bf16 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/tts_omnivoice_longform_bf16.json`
- 用途：Pixelle 可传参执行的 OmniVoice bf16 长文本旁白工作流。

## 2. 节点与依赖清单

- `PrimitiveStringMultiline`：输入待合成文本。
- `PrimitiveStringMultiline`：输入参考音频转写文本。
- `VHS_LoadAudioUpload`：上传参考音频。
- `OmniVoiceLongformTTS`：长文本 TTS 主节点。
- `SaveAudio`：保存 FLAC 音频。

## 3. 依赖分类

- 模型文件：`OmniVoice-bf16`、`whisper-large-v3`。
- 自定义节点：`ComfyUI-OmniVoice-TTS`、`ComfyUI-Pixelle-TTS`、VideoHelperSuite。
- Python 包：`modelscope`、`transformers`、`accelerate`、`safetensors`、`soundfile`、`librosa`、`soxr`。

## 4. 目标目录

- OmniVoice 模型目录：`E:\ComfyUIData\models\omnivoice\OmniVoice-bf16`
- Whisper 模型目录：`E:\ComfyUIData\models\audio_encoders\whisper-large-v3`
- 自定义节点目录：`E:\ComfyUIData\custom_nodes`

## 5. 下载优先级

根据仓库规则，模型文件默认优先使用 `ModelScope`。仅当 `ModelScope` 缺少所需文件或当前不可用时，才回退到 Hugging Face。

## 6. ModelScope 检索或主地址

- `drbaph/OmniVoice-bf16`
- `openai/whisper-large-v3`

## 7. 备用地址

- `https://huggingface.co/drbaph/OmniVoice-bf16`
- `https://huggingface.co/openai/whisper-large-v3`

## 8. 安装命令

```powershell
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -U modelscope
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -r E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS\requirements.txt
python tools\sync_pixelle_tts_custom_node.py --target E:\ComfyUIData\custom_nodes\ComfyUI-Pixelle-TTS --python E:\ComfyUIData\.venv\Scripts\python.exe
```

## 9. 验证命令

```powershell
python -m pytest tests/test_selfhost_workflows.py -k tts_omnivoice -q
```

## 10. 常见问题

- 如果 `WorkflowParser` 解析不到参数，检查 `_meta.title` 是否包含 `$text.value!`、`$ref_audio.~audio!` 和 `$reference_audio_text.value`。
- 如果参考音频上传失败，检查 `VHS_LoadAudioUpload` 是否安装。
- 如果参考文本为空，OmniVoice 节点可能回退到 Whisper 自动转写。
````

- [ ] **Step 4: Write the clone-duration dependency doc**

Create `workflows/down/tts_omnivoice_clone_duration_bf16_依赖与下载说明.md` with the same structure, but adjust:

- 工作流文件：`workflows/selfhost/tts_omnivoice_clone_duration_bf16.json`
- 用途：Pixelle 可传参执行的 OmniVoice bf16 短文本定长克隆工作流。
- 节点清单包含 `PixelleFloatInput` 和 `OmniVoiceVoiceCloneTTS`。
- 常见问题增加：`duration` 只适合短文本定长，不建议用于长文本整体控时长。

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py -k "tts_omnivoice" -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add workflows/down/tts_omnivoice_longform_bf16_依赖与下载说明.md workflows/down/tts_omnivoice_clone_duration_bf16_依赖与下载说明.md tests/test_selfhost_workflows.py
git commit -m "docs: 补充 OmniVoice API 工作流依赖说明"
git push
```

---

### Task 5: Final Workflow Verification

**Files:**
- `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Run parser checks directly**

Run:

```powershell
@'
from pathlib import Path
from comfykit.comfyui.workflow_parser import WorkflowParser

for path in [
    "workflows/selfhost/tts_omnivoice_longform_bf16.json",
    "workflows/selfhost/tts_omnivoice_clone_duration_bf16.json",
]:
    metadata = WorkflowParser().parse_workflow_file(path)
    print(path, sorted(metadata.params.keys()))
'@ | python -
```

Expected:

```text
workflows/selfhost/tts_omnivoice_longform_bf16.json ['ref_audio', 'reference_audio_text', 'text']
workflows/selfhost/tts_omnivoice_clone_duration_bf16.json ['duration', 'ref_audio', 'reference_audio_text', 'text']
```

- [ ] **Step 2: Run focused test suite**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py -k "tts_omnivoice or omnivoice_ui" -v
```

Expected: PASS. Existing UI workflow tests must still pass.

- [ ] **Step 3: Check git status**

Run:

```powershell
git status --short
```

Expected: clean after committed changes.

## Self-Review

- Spec coverage:
  - Two API workflow files are covered by Tasks 2 and 3.
  - `WorkflowParser` parameter mapping is covered by Task 1 and Task 5.
  - Dependency docs with ModelScope-first policy are covered by Task 4.
  - Existing UI workflows are explicitly out of scope and preserved.
- Placeholder scan:
  - No placeholder markers remain.
  - JSON workflow bodies are fully specified.
- Type consistency:
  - Longform workflow exposes `text`, `ref_audio`, and `reference_audio_text`.
  - Clone-duration workflow exposes `text`, `ref_audio`, `reference_audio_text`, and `duration`.
  - Both workflows use `OmniVoice-bf16`, `device=auto`, and `dtype=auto`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-04-omnivoice-api-workflows-implementation.md`. Complete this plan before executing `docs/superpowers/plans/2026-05-04-omnivoice-longform-master-track-implementation.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.
