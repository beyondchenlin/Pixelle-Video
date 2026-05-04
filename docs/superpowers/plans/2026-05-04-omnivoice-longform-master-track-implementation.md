# OmniVoice Longform Master Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OmniVoice bf16 the default local TTS workflow, add source-level OmniVoice workflow family detection, and implement backend-only master-track longform protection blocks without exposing a new frontend switch.

**Architecture:** Introduce a unified TTS workflow family classifier that all TTS-specific branching uses, add a parseable OmniVoice API workflow based on `OmniVoiceLongformTTS`, and implement a dedicated master-track longform block planner separate from the existing IndexTTS2 external segmentation plan. The standard pipeline remains the orchestration boundary: it decides when master-track OmniVoice protection applies, executes each protected block through the new workflow, and records observability with block-level metadata.

**Tech Stack:** Python, pytest, ComfyUI workflow JSON, Streamlit i18n/UI config, existing Pixelle TTS pipeline services.

---

## File Structure

**Create**

- `pixelle_video/tts_workflow_family.py`
- `workflows/selfhost/tts_omnivoice_bf16.json`
- `pixelle_video/services/omnivoice_longform_blocks.py`
- `workflows/down/tts_omnivoice_bf16_依赖与下载说明.md`

**Modify**

- `pixelle_video/config/workflow_defaults.py`
- `config.yaml`
- `config.example.yaml`
- `pixelle_video/services/tts_voice_profiles.py`
- `pixelle_video/tts_workflow_contract.py`
- `pixelle_video/pipelines/standard.py`
- `web/components/style_config.py`
- `web/i18n/locales/zh_CN.json`
- `web/i18n/locales/en_US.json`
- `tests/test_tts_service_workflow_params.py`
- `tests/test_tts_voice_profiles.py`
- `tests/test_selfhost_workflows.py`
- `tests/test_tts_comfyui_defaults.py`
- `tests/test_index_tts2_timing_profile.py`

**Test Focus**

- `tests/test_tts_service_workflow_params.py`
- `tests/test_tts_voice_profiles.py`
- `tests/test_selfhost_workflows.py`
- `tests/test_tts_comfyui_defaults.py`
- `tests/test_tts_segmentation.py`
- `tests/test_index_tts2_timing_profile.py`

---

### Task 1: Add Unified TTS Workflow Family Detection

**Files:**
- Create: `pixelle_video/tts_workflow_family.py`
- Modify: `pixelle_video/tts_workflow_contract.py`
- Test: `tests/test_tts_service_workflow_params.py`

- [ ] **Step 1: Write the failing tests for workflow family inference**

```python
from pathlib import Path

from pixelle_video.tts_workflow_family import (
    infer_tts_workflow_family,
    is_tts_workflow_family,
)


def test_omnivoice_workflow_family_is_detected_from_node_class(tmp_path):
    workflow_path = tmp_path / "custom_tts.json"
    workflow_path.write_text(
        """
        {
          "12": {
            "inputs": {"text": ["3", 0]},
            "class_type": "OmniVoiceLongformTTS"
          }
        }
        """,
        encoding="utf-8",
    )

    assert infer_tts_workflow_family(workflow_path) == "omnivoice"
    assert is_tts_workflow_family(workflow_path, "omnivoice") is True


def test_generic_tts_workflow_family_falls_back_when_unknown(tmp_path):
    workflow_path = tmp_path / "generic_tts.json"
    workflow_path.write_text(
        """
        {
          "1": {
            "inputs": {"text": ["3", 0]},
            "class_type": "CustomTTSNode"
          }
        }
        """,
        encoding="utf-8",
    )

    assert infer_tts_workflow_family(workflow_path) == "generic"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts_service_workflow_params.py -k "workflow_family or omnivoice" -v`  
Expected: FAIL with `ModuleNotFoundError` or missing symbol errors for `pixelle_video.tts_workflow_family`.

- [ ] **Step 3: Implement the workflow family module and contract wrappers**

```python
# pixelle_video/tts_workflow_family.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Literal

TtsWorkflowFamily = Literal["indextts2", "omnivoice", "edge", "generic"]

INDEX_TTS2_NODE_PREFIXES = ("IndexTTS2",)
OMNIVOICE_NODE_PREFIXES = ("OmniVoice",)
EDGE_NODE_TYPES = frozenset({"PixelleEdgeTTS", "EdgeTTS"})


def infer_tts_workflow_family(workflow_key: Any) -> TtsWorkflowFamily:
    workflow = _load_workflow_from_key(workflow_key)
    family = _infer_family_from_workflow(workflow)
    if family is not None:
        return family
    return _infer_family_from_stem(workflow_key)


def is_tts_workflow_family(workflow_key: Any, family: TtsWorkflowFamily) -> bool:
    return infer_tts_workflow_family(workflow_key) == family


def _infer_family_from_workflow(workflow: Mapping[str, Any] | None) -> TtsWorkflowFamily | None:
    if not isinstance(workflow, Mapping):
        return None
    for value in workflow.values():
        if not isinstance(value, Mapping):
            continue
        class_type = value.get("class_type")
        if isinstance(class_type, str):
            if class_type.startswith(INDEX_TTS2_NODE_PREFIXES):
                return "indextts2"
            if class_type.startswith(OMNIVOICE_NODE_PREFIXES):
                return "omnivoice"
            if class_type in EDGE_NODE_TYPES:
                return "edge"
        nested = _infer_family_from_workflow(value)
        if nested is not None:
            return nested
    return None


def _infer_family_from_stem(workflow_key: Any) -> TtsWorkflowFamily:
    stem = Path(str(workflow_key or "")).stem.lower().replace("-", "").replace("_", "")
    if "index2" in stem or "indextts2" in stem:
        return "indextts2"
    if "omnivoice" in stem:
        return "omnivoice"
    if "edge" in stem:
        return "edge"
    return "generic"


def _load_workflow_from_key(workflow_key: Any) -> Mapping[str, Any] | None:
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
            with candidate.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except Exception:
            continue
        if isinstance(value, Mapping):
            return value
    return None
```

```python
# pixelle_video/tts_workflow_contract.py
from pixelle_video.tts_workflow_family import infer_tts_workflow_family, is_tts_workflow_family


def is_index_tts2_workflow_key(workflow_key: Any) -> bool:
    return is_tts_workflow_family(workflow_key, "indextts2")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts_service_workflow_params.py -k "workflow_family or omnivoice or index_tts2" -v`  
Expected: PASS for the new family-detection tests and the existing IndexTTS2 detection tests.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/tts_workflow_family.py pixelle_video/tts_workflow_contract.py tests/test_tts_service_workflow_params.py
git commit -m "refactor: 统一 TTS 工作流家族识别"
```

### Task 2: Add Parseable OmniVoice API Workflow and Default Workflow Switch

**Files:**
- Create: `workflows/selfhost/tts_omnivoice_bf16.json`
- Modify: `pixelle_video/config/workflow_defaults.py`
- Modify: `config.yaml`
- Modify: `config.example.yaml`
- Test: `tests/test_selfhost_workflows.py`
- Test: `tests/test_tts_comfyui_defaults.py`

- [ ] **Step 1: Write the failing tests for the new default workflow and workflow parser contract**

```python
from pathlib import Path

from comfykit.comfyui.workflow_parser import WorkflowParser


def test_tts_omnivoice_bf16_workflow_is_parseable_for_api_use():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/tts_omnivoice_bf16.json"))
    )
    assert set(metadata.params.keys()) == {"text", "ref_audio", "reference_audio_text"}
    assert metadata.params["text"].required is True
    assert metadata.params["ref_audio"].need_upload is True


def test_tts_defaults_to_comfyui_omnivoice_workflow():
    from pixelle_video.config.workflow_defaults import BUILTIN_DEFAULT_WORKFLOWS

    assert BUILTIN_DEFAULT_WORKFLOWS["tts"] == "selfhost/tts_omnivoice_bf16.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selfhost_workflows.py tests/test_tts_comfyui_defaults.py -k "omnivoice_bf16_workflow or defaults_to_comfyui_omnivoice" -v`  
Expected: FAIL because `tts_omnivoice_bf16.json` does not exist and the default workflow still points to `tts_index2_8g.json`.

- [ ] **Step 3: Create the OmniVoice API workflow and switch defaults**

```json
{
  "3": {
    "inputs": {
      "value": "This is an OmniVoice longform sample."
    },
    "class_type": "PrimitiveStringMultiline",
    "_meta": {
      "title": "$text.value!"
    }
  },
  "4": {
    "inputs": {
      "value": "This reference audio demonstrates a calm and natural speaking style."
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
      "steps": 64,
      "guidance_scale": 2,
      "t_shift": 0.1,
      "speed": 0.8,
      "duration": 0,
      "device": "cuda",
      "dtype": "fp16",
      "attention": "auto",
      "seed": 20,
      "words_per_chunk": 100,
      "position_temperature": 5,
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
      "filename_prefix": "audio/ComfyUI_omnivoice",
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

```python
# pixelle_video/config/workflow_defaults.py
DEFAULT_TTS_WORKFLOW = "selfhost/tts_omnivoice_bf16.json"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_selfhost_workflows.py tests/test_tts_comfyui_defaults.py -k "omnivoice_bf16_workflow or defaults_to_comfyui_omnivoice" -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/selfhost/tts_omnivoice_bf16.json pixelle_video/config/workflow_defaults.py config.yaml config.example.yaml tests/test_selfhost_workflows.py tests/test_tts_comfyui_defaults.py
git commit -m "feat: 新增 OmniVoice 默认 TTS 工作流"
```

### Task 3: Make Voice Profiles Use Unified Workflow Family Detection

**Files:**
- Modify: `pixelle_video/services/tts_voice_profiles.py`
- Test: `tests/test_tts_voice_profiles.py`

- [ ] **Step 1: Write the failing tests for OmniVoice voice-profile naming and filtering**

```python
def test_build_voice_profile_name_appends_omnivoice_suffix():
    assert (
        tts_voice_profiles.build_voice_profile_name("班哥", "selfhost/tts_omnivoice_bf16.json")
        == "班哥-omnivoice"
    )


def test_list_voice_profiles_filters_for_omnivoice(tmp_path):
    manifest_path = tmp_path / "reference_audio" / "voice_profiles.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "id": "a",
                        "name": "班哥-omnivoice",
                        "model_slug": "omnivoice",
                        "workflow_key": "selfhost/tts_omnivoice_bf16.json",
                        "audio_path": "reference_audio/omnivoice/bange.wav",
                        "ref_audio_text": "大家好"
                    },
                    {
                        "id": "b",
                        "name": "班哥-indextts2",
                        "model_slug": "indextts2",
                        "workflow_key": "selfhost/tts_index2.json",
                        "audio_path": "reference_audio/indextts2/bange.wav",
                        "ref_audio_text": "大家好"
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    profiles = tts_voice_profiles.list_voice_profiles(
        "selfhost/tts_omnivoice_bf16.json",
        manifest_path=manifest_path,
    )
    assert [profile["name"] for profile in profiles] == ["班哥-omnivoice"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts_voice_profiles.py -k "omnivoice" -v`  
Expected: FAIL because the current slug fallback uses the full stem and not the unified family.

- [ ] **Step 3: Refactor voice profile slug inference to use workflow family**

```python
from pixelle_video.tts_workflow_family import infer_tts_workflow_family


def infer_tts_model_slug(workflow_key: str | None) -> str:
    family = infer_tts_workflow_family(workflow_key)
    if family == "generic":
        workflow_name = Path(str(workflow_key or "")).stem.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", workflow_name).strip("-")
        return slug or "tts"
    return family
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts_voice_profiles.py -v`  
Expected: PASS for existing IndexTTS2/Edge tests and the new OmniVoice tests.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/tts_voice_profiles.py tests/test_tts_voice_profiles.py
git commit -m "refactor: 统一 OmniVoice 音色档案识别"
```

### Task 4: Add Dedicated OmniVoice Master-Track Longform Block Planner

**Files:**
- Create: `pixelle_video/services/omnivoice_longform_blocks.py`
- Test: `tests/test_tts_segmentation.py`

- [ ] **Step 1: Write the failing tests for block planning**

```python
from pixelle_video.services.omnivoice_longform_blocks import build_omnivoice_longform_block_plan


def test_omnivoice_longform_block_plan_prefers_sentence_boundaries():
    text = (
        "第一段结束。第二段继续讲解系统设计。"
        "Third sentence explains the longform planner. Final sentence closes the section."
    )
    plan = build_omnivoice_longform_block_plan(
        text,
        max_chars_per_block=24,
        hard_max_chars_per_block=40,
    )
    assert "".join(block.text for block in plan.blocks) == text
    assert len(plan.blocks) >= 2
    assert plan.mode == "omnivoice_master_track_longform"


def test_omnivoice_longform_block_plan_does_not_split_decimal_or_domain():
    text = "Version 3.14 is stable. Visit example.com for details. Then continue the narration."
    plan = build_omnivoice_longform_block_plan(
        text,
        max_chars_per_block=35,
        hard_max_chars_per_block=60,
    )
    assert "3.14" in "".join(block.text for block in plan.blocks)
    assert "example.com" in "".join(block.text for block in plan.blocks)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts_segmentation.py -k "omnivoice_longform" -v`  
Expected: FAIL because the planner module does not exist.

- [ ] **Step 3: Implement the planner as a dedicated service**

```python
# pixelle_video/services/omnivoice_longform_blocks.py
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class OmniVoiceLongformBlock:
    id: str
    text: str
    source_start: int
    source_end: int
    char_count: int
    boundary_type: str
    split_reason: str
    source_audio_path: str | None = None
    normalized_audio_path: str | None = None
    duration_ms: int | None = None


@dataclass
class OmniVoiceLongformBlockPlan:
    plan_id: str
    mode: str
    source_text_hash: str
    source_char_count: int
    blocks: list[OmniVoiceLongformBlock] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def build_omnivoice_longform_block_plan(
    text: str,
    *,
    max_chars_per_block: int = 6000,
    hard_max_chars_per_block: int = 9000,
) -> OmniVoiceLongformBlockPlan:
    source_text = text or ""
    blocks: list[OmniVoiceLongformBlock] = []
    cursor = 0
    while cursor < len(source_text):
        target = min(cursor + max_chars_per_block, len(source_text))
        if target >= len(source_text):
            end = len(source_text)
            boundary_type = "end_of_text"
            split_reason = "end_of_text"
        else:
            end = _find_block_boundary(source_text, cursor, target, hard_max_chars_per_block)
            boundary_type = "sentence"
            split_reason = "sentence_boundary"
        if end <= cursor:
            end = min(cursor + hard_max_chars_per_block, len(source_text))
            boundary_type = "hard_limit"
            split_reason = "hard_limit"
        segment = source_text[cursor:end]
        blocks.append(
            OmniVoiceLongformBlock(
                id=f"block-{len(blocks)+1}",
                text=segment,
                source_start=cursor,
                source_end=end,
                char_count=len(segment),
                boundary_type=boundary_type,
                split_reason=split_reason,
            )
        )
        cursor = end
    return OmniVoiceLongformBlockPlan(
        plan_id=hashlib.sha1(source_text.encode("utf-8")).hexdigest()[:12],
        mode="omnivoice_master_track_longform",
        source_text_hash=hashlib.sha1(source_text.encode("utf-8")).hexdigest(),
        source_char_count=len(source_text),
        blocks=blocks,
        config={
            "max_chars_per_block": max_chars_per_block,
            "hard_max_chars_per_block": hard_max_chars_per_block,
        },
    )


def _find_block_boundary(
    text: str,
    cursor: int,
    target: int,
    hard_max_chars_per_block: int,
) -> int:
    hard_end = min(cursor + hard_max_chars_per_block, len(text))
    for index in range(min(hard_end, len(text)) - 1, target - 1, -1):
        if _is_sentence_boundary(text, index):
            return _consume_closing_punctuation(text, index + 1, hard_end)
    for index in range(target - 1, cursor - 1, -1):
        if _is_sentence_boundary(text, index):
            return _consume_closing_punctuation(text, index + 1, hard_end)
    return min(cursor + hard_max_chars_per_block, len(text))


def _is_sentence_boundary(text: str, index: int) -> bool:
    char = text[index]
    if char in "。！？!?":
        return True
    if char != ".":
        return False
    if _is_decimal_period(text, index):
        return False
    if _is_domain_period(text, index):
        return False
    if _is_common_abbreviation_period(text, index):
        return False
    return True


def _is_decimal_period(text: str, index: int) -> bool:
    return (
        index > 0
        and index + 1 < len(text)
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    )


def _is_domain_period(text: str, index: int) -> bool:
    return (
        index > 0
        and index + 1 < len(text)
        and text[index - 1].isalnum()
        and text[index + 1].isalnum()
    )


def _is_common_abbreviation_period(text: str, index: int) -> bool:
    start = index
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    token = text[start:index].lower()
    return token in {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc"}


def _consume_closing_punctuation(text: str, index: int, hard_end: int) -> int:
    closing_chars = set("”’」』）》】〕〉》\"')]} \n\r\t")
    cursor = index
    while cursor < hard_end and text[cursor] in closing_chars:
        cursor += 1
    return cursor
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts_segmentation.py -k "omnivoice_longform" -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/omnivoice_longform_blocks.py tests/test_tts_segmentation.py
git commit -m "feat: 新增 OmniVoice 主音轨保护块计划"
```

### Task 5: Integrate OmniVoice Longform Block Planning into Master-Track Synthesis

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_index_tts2_timing_profile.py`

- [ ] **Step 1: Write the failing integration tests for master-track OmniVoice block planning**

```python
@pytest.mark.asyncio
async def test_standard_pipeline_master_track_omnivoice_uses_longform_block_plan(monkeypatch, tmp_path):
    class RecordingTts:
        def __init__(self):
            self.calls = []

        async def __call__(self, **params):
            self.calls.append(params)
            return params["output_path"]

    core = _FakeCore()
    core.tts = RecordingTts()
    pipeline = StandardPipeline(core)
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-omnivoice-master",
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_omnivoice_bf16.json",
        ref_audio="voice.wav",
        ref_audio_text="大家好，这是参考音频文本。",
    )
    ctx = PipelineContext(input_text="demo", params={})
    ctx.task_id = config.task_id
    ctx.task_dir = str(tmp_path)
    ctx.config = config
    ctx.timing_plan = TimingPlan(
        blocks=[
            AudioBlock(
                id="block-1",
                text=(
                    "第一段结束。第二段继续讲解系统设计。"
                    "第三段继续补充架构决策。第四段收尾。"
                )
                * 220,
                source_frame_indices=[0],
            )
        ]
    )

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", lambda source, output: output)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda path: 1.0)
    monkeypatch.setattr(
        pipeline,
        "_concat_audio_files",
        lambda paths, output, **kwargs: None,
    )

    await pipeline._synthesize_hyperframes_audio(ctx)

    assert len(core.tts.calls) > 1
    assert all(call["workflow"] == "selfhost/tts_omnivoice_bf16.json" for call in core.tts.calls)
    assert all(call["ref_audio_text"] == "大家好，这是参考音频文本。" for call in core.tts.calls)
    plans = ctx.observability["tts_segmentation"]["plans"]
    assert plans[0]["mode"] == "omnivoice_master_track_longform"


@pytest.mark.asyncio
async def test_standard_pipeline_master_track_short_omnivoice_skips_longform_block_plan(monkeypatch, tmp_path):
    class RecordingTts:
        def __init__(self):
            self.calls = []

        async def __call__(self, **params):
            self.calls.append(params)
            return params["output_path"]

    core = _FakeCore()
    core.tts = RecordingTts()
    pipeline = StandardPipeline(core)
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-omnivoice-short",
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_omnivoice_bf16.json",
    )
    ctx = PipelineContext(input_text="demo", params={})
    ctx.task_id = config.task_id
    ctx.task_dir = str(tmp_path)
    ctx.config = config
    ctx.timing_plan = TimingPlan(
        blocks=[
            AudioBlock(
                id="block-1",
                text="短文本不需要进入主音轨保护块。",
                source_frame_indices=[0],
            )
        ]
    )

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", lambda source, output: output)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda path: 1.0)
    monkeypatch.setattr(
        pipeline,
        "_concat_audio_files",
        lambda paths, output, **kwargs: None,
    )

    await pipeline._synthesize_hyperframes_audio(ctx)

    assert len(core.tts.calls) == 1
    plans = ctx.observability.get("tts_segmentation", {}).get("plans", [])
    assert plans == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_index_tts2_timing_profile.py -k "omnivoice_master_track" -v`  
Expected: FAIL because the standard pipeline does not yet use the OmniVoice block planner.

- [ ] **Step 3: Integrate the planner only at the standard-pipeline master-track boundary**

```python
# pixelle_video/pipelines/standard.py
from pixelle_video.services.omnivoice_longform_blocks import build_omnivoice_longform_block_plan
from pixelle_video.tts_workflow_family import is_tts_workflow_family


def _uses_omnivoice_workflow(self, config: StoryboardConfig) -> bool:
    if config.tts_inference_mode != "comfyui":
        return False
    workflow_key = config.tts_workflow or ""
    tts_service = getattr(self.core, "tts", None)
    if tts_service is not None and hasattr(tts_service, "_resolve_workflow"):
        try:
            workflow_key = tts_service._resolve_workflow(workflow=config.tts_workflow)["key"]
        except Exception:
            workflow_key = config.tts_workflow or workflow_key
    return is_tts_workflow_family(workflow_key, "omnivoice")


async def _synthesize_audio_block(
    self,
    ctx: PipelineContext,
    *,
    block_id: str,
    block_text: str,
    task_audio_dir: Path,
    block_output_path: Path,
) -> str:
    omnivoice_min_chars = 6000
    segments = [block_text]
    if self._uses_index_tts2_workflow(ctx.config) and ctx.config.tts_split_mode != INTERNAL_ONLY_TTS_SPLIT_MODE:
        plan = build_external_tts_segmentation_plan(
            block_text,
            max_chars_per_segment=ctx.config.max_chars_per_tts_segment,
            boundary_search_radius=ctx.config.tts_boundary_search_radius,
            soft_overflow_chars=ctx.config.tts_soft_overflow_chars,
            source_unit_type="audio_block",
            source_unit_id=block_id,
            overflow_policy=ctx.config.tts_split_overflow_policy,
        )
        self._record_tts_segmentation_plan(ctx, plan)
        segments = [segment.text for segment in plan.segments] or [block_text]
    elif self._uses_omnivoice_workflow(ctx.config) and len(block_text) > omnivoice_min_chars:
        plan = build_omnivoice_longform_block_plan(
            block_text,
            max_chars_per_block=omnivoice_min_chars,
            hard_max_chars_per_block=9000,
        )
        self._record_tts_segmentation_plan(ctx, plan)
        segments = [block.text for block in plan.blocks] or [block_text]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_index_tts2_timing_profile.py -v`  
Expected: PASS for existing IndexTTS2 tests and the new OmniVoice master-track tests.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/pipelines/standard.py tests/test_index_tts2_timing_profile.py
git commit -m "feat: 接入 OmniVoice 主音轨保护块合成"
```

### Task 6: Keep TTS Service and Workflow Param Mapping Compatible with OmniVoice

**Files:**
- Modify: `pixelle_video/services/tts_service.py`
- Modify: `tests/test_tts_service_workflow_params.py`

- [ ] **Step 1: Write the failing tests for reference-audio-text propagation**

```python
@pytest.mark.asyncio
async def test_tts_service_maps_ref_audio_text_to_reference_audio_text_for_omnivoice():
    core = _FakeCore()
    service = TTSService({"comfyui": {"tts": {}}}, core=core)

    await service._call_comfyui_workflow(
        {
            "key": "selfhost/tts_omnivoice_bf16.json",
            "source": "selfhost",
            "path": "workflows/selfhost/tts_omnivoice_bf16.json",
        },
        text="generated text",
        ref_audio="voice.wav",
        ref_audio_text="大家好",
    )

    workflow_input, params = core.kit.calls[-1]
    assert workflow_input == "workflows/selfhost/tts_omnivoice_bf16.json"
    assert params["reference_audio_text"] == "大家好"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts_service_workflow_params.py -k "reference_audio_text_for_omnivoice" -v`  
Expected: FAIL until the new workflow exists and mapping is verified against it.

- [ ] **Step 3: Make the TTS service assert the new param mapping**

```python
def _get_workflow_param_names(self, workflow_info: dict) -> set[str]:
    metadata = self._get_workflow_metadata(workflow_info)
    if metadata is None:
        return set()
    return set(metadata.params.keys())
```

Keep the existing `build_ref_audio_text_params(...)` flow, but make the new OmniVoice workflow expose `reference_audio_text` so this path is validated by tests instead of assumed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts_service_workflow_params.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/tts_service.py tests/test_tts_service_workflow_params.py
git commit -m "test: 锁定 OmniVoice 参考文本参数映射"
```

### Task 7: Align Frontend Copy and Preserve Advanced IndexTTS2 Controls

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Test: `tests/test_render_backend_ui.py`
- Test: `tests/test_tts_split_mode_ui_layout.py`

- [ ] **Step 1: Write the failing tests for updated copy behavior**

```python
def test_tts_split_mode_help_no_longer_mentions_indextts2_only():
    import json
    from pathlib import Path

    zh = json.loads(Path("web/i18n/locales/zh_CN.json").read_text(encoding="utf-8"))
    en = json.loads(Path("web/i18n/locales/en_US.json").read_text(encoding="utf-8"))

    assert "OmniVoice 默认由后端自动处理长主音轨" in zh["tts_split_mode.help"]
    assert "IndexTTS2" in zh["tts_split_mode.help"]
    assert "OmniVoice defaults to backend longform handling" in en["tts_split_mode.help"]


def test_render_tts_split_settings_uses_updated_translation_keys(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "config_manager", _fake_config_manager())

    settings = style_config.render_tts_split_settings()

    assert settings["tts_split_mode"] == "internal_only"
    assert fake_st.captions[-1] == "tts_split_mode.caption.internal_only"
```

Use the existing test style to assert the UI still renders the same controls while updated help/caption text no longer describes the setting as OmniVoice-facing user configuration.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_render_backend_ui.py tests/test_tts_split_mode_ui_layout.py -k "tts_split_mode" -v`  
Expected: FAIL because the copy still references IndexTTS2-specific default behavior.

- [ ] **Step 3: Update i18n copy and keep the existing control surface**

```json
"tts_split_mode.help": "选择 TTS 文本如何分段。OmniVoice 默认由后端自动处理长主音轨；外部分段主要用于 IndexTTS2 等兼容工作流。",
"tts_split_mode.caption.internal_only": "整段交给工作流内部处理。OmniVoice 默认使用这种方式。",
"tts_split_mode.caption.external_only": "由 Pixelle 在调用前预切文本，适合 IndexTTS2 等需要更强边界控制的工作流。"
```

Do not add a new OmniVoice longform switch; only update wording and, if needed, conditional display help.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_render_backend_ui.py tests/test_tts_split_mode_ui_layout.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/components/style_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_render_backend_ui.py tests/test_tts_split_mode_ui_layout.py
git commit -m "docs: 调整 TTS 分段模式文案语义"
```

### Task 8: Add OmniVoice Dependency Doc and Final Verification

**Files:**
- Create: `workflows/down/tts_omnivoice_bf16_依赖与下载说明.md`
- Modify: `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Write the failing tests for the new dependency doc coverage**

```python
def test_tts_omnivoice_dependency_doc_records_modelscope_priority():
    doc = Path("workflows/down/tts_omnivoice_bf16_依赖与下载说明.md").read_text(encoding="utf-8")
    assert "ModelScope" in doc
    assert "OmniVoice-bf16" in doc
    assert "whisper-large-v3" in doc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selfhost_workflows.py -k "tts_omnivoice_dependency_doc" -v`  
Expected: FAIL because the doc does not exist yet.

- [ ] **Step 3: Write the dependency doc with verified install and fallback notes**

Include:

- Workflow path: `workflows/selfhost/tts_omnivoice_bf16.json`
- Node list: `PrimitiveStringMultiline`, `VHS_LoadAudioUpload`, `OmniVoiceLongformTTS`, `SaveAudio`
- Model directories
- ModelScope-first lookup records
- Verified fallback links
- Validation commands
- Common issues

- [ ] **Step 4: Run the full focused verification suite**

Run:  
`pytest tests/test_tts_service_workflow_params.py tests/test_tts_voice_profiles.py tests/test_selfhost_workflows.py tests/test_tts_comfyui_defaults.py tests/test_tts_segmentation.py tests/test_index_tts2_timing_profile.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/down/tts_omnivoice_bf16_依赖与下载说明.md tests/test_selfhost_workflows.py
git commit -m "docs: 补充 OmniVoice 默认 TTS 依赖说明"
```

## Self-Review

- Spec coverage:
  - Unified workflow family detection is covered by Task 1 and consumed again in Tasks 3 and 5.
  - New OmniVoice API workflow and default-switch requirements are covered by Task 2.
  - Voice profile compatibility is covered by Task 3.
  - Dedicated longform protection block planning is covered by Task 4.
  - Standard-pipeline master-track integration is covered by Task 5.
  - Workflow param propagation is covered by Task 6.
  - Frontend copy alignment without a new switch is covered by Task 7.
  - Dependency docs and ModelScope-first verification are covered by Task 8.
- Placeholder scan:
  - No `TODO`, `TBD`, or “similar to task N” placeholders remain.
  - Code steps include concrete snippets or concrete content requirements.
- Type consistency:
  - Workflow family names are consistently `indextts2`, `omnivoice`, `edge`, `generic`.
  - The dedicated block plan mode is consistently `omnivoice_master_track_longform`.
  - The new workflow param name is consistently `reference_audio_text`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-04-omnivoice-longform-master-track-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
