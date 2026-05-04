# OmniVoice 默认 TTS 系统集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 OmniVoice bf16 接入 Pixelle 默认 TTS、保存音色和长文本主音轨分段链路，同时保留 IndexTTS2 与 Edge TTS 的兼容路径。

**Architecture:** 本计划负责方案三的系统集成层：新增统一 TTS 工作流家族识别，默认 TTS 指向 OmniVoice 长文本 API 工作流，保存音色和主音轨长文本保护分段都通过同一识别层决策。两个 OmniVoice API 工作流本身不在本计划中创建，必须先完成关联计划 `docs/superpowers/plans/2026-05-04-omnivoice-api-workflows-implementation.md`。

**Tech Stack:** Python, pytest, ComfyUI API workflow JSON, ComfyKit `WorkflowParser`, Streamlit configuration UI, Pixelle TTS pipeline services.

---

## 关联计划

本计划依赖并引用：

- `docs/superpowers/plans/2026-05-04-omnivoice-api-workflows-implementation.md`

两个计划的边界如下：

- **API 工作流专项计划**：只负责创建和验证 `tts_omnivoice_longform_bf16.json` 与 `tts_omnivoice_clone_duration_bf16.json`，并补充对应依赖说明。
- **本系统集成计划**：在两个 API 工作流已存在且可解析的前提下，完成默认 TTS、保存音色、长文本主音轨保护分段、前端选择和兼容逻辑。

执行顺序必须是：

1. 先执行 `2026-05-04-omnivoice-api-workflows-implementation.md`。
2. 验证两个 API 工作流可被 `WorkflowParser` 解析。
3. 再执行本计划。

## File Structure

**Create**

- `pixelle_video/tts_workflow_family.py`
- `pixelle_video/services/omnivoice_longform_blocks.py`

**Modify**

- `pixelle_video/tts_workflow_contract.py`
- `pixelle_video/config/workflow_defaults.py`
- `config.yaml`
- `config.example.yaml`
- `pixelle_video/services/tts_voice_profiles.py`
- `pixelle_video/services/tts_service.py`
- `api/schemas/tts.py`
- `api/routers/tts.py`
- `pixelle_video/pipelines/standard.py`
- `web/components/style_config.py`
- `web/i18n/locales/zh_CN.json`
- `web/i18n/locales/en_US.json`
- `tests/test_tts_service_workflow_params.py`
- `tests/test_tts_voice_profiles.py`
- `tests/test_tts_comfyui_defaults.py`
- `tests/test_index_tts2_timing_profile.py`
- `tests/test_tts_segmentation.py`
- `tests/test_selfhost_workflows.py`

**Depends On**

- `workflows/selfhost/tts_omnivoice_longform_bf16.json`
- `workflows/selfhost/tts_omnivoice_clone_duration_bf16.json`
- `workflows/down/tts_omnivoice_longform_bf16_依赖与下载说明.md`
- `workflows/down/tts_omnivoice_clone_duration_bf16_依赖与下载说明.md`

---

### Task 1: Add Unified TTS Workflow Family Detection

**Files:**
- Create: `pixelle_video/tts_workflow_family.py`
- Modify: `pixelle_video/tts_workflow_contract.py`
- Test: `tests/test_tts_service_workflow_params.py`

- [ ] **Step 1: Write failing tests for TTS workflow family inference**

Append these tests to `tests/test_tts_service_workflow_params.py`:

```python
from pixelle_video.tts_workflow_family import (
    infer_tts_workflow_family,
    is_omnivoice_workflow_key,
    is_tts_workflow_family,
)


def test_tts_workflow_family_detects_omnivoice_from_node_class(tmp_path):
    workflow_path = tmp_path / "custom_tts.json"
    workflow_path.write_text(
        """
        {
          "1": {
            "inputs": {"text": "hello"},
            "class_type": "OmniVoiceLongformTTS",
            "_meta": {"title": "OmniVoice Longform TTS"}
          }
        }
        """,
        encoding="utf-8",
    )

    assert infer_tts_workflow_family(workflow_path) == "omnivoice"
    assert is_tts_workflow_family(workflow_path, "omnivoice") is True
    assert is_omnivoice_workflow_key(workflow_path) is True


def test_tts_workflow_family_detects_index_tts2_from_existing_workflow():
    assert infer_tts_workflow_family("selfhost/tts_index2.json") == "indextts2"


def test_tts_workflow_family_detects_edge_from_existing_workflow():
    assert infer_tts_workflow_family("selfhost/tts_edge.json") == "edge"


def test_tts_workflow_family_falls_back_to_generic_for_unknown_workflow(tmp_path):
    workflow_path = tmp_path / "custom_tts.json"
    workflow_path.write_text(
        """
        {
          "1": {
            "inputs": {"text": "hello"},
            "class_type": "CustomTTSNode",
            "_meta": {"title": "Custom TTS"}
          }
        }
        """,
        encoding="utf-8",
    )

    assert infer_tts_workflow_family(workflow_path) == "generic"
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_tts_service_workflow_params.py -k "tts_workflow_family" -v
```

Expected: FAIL with `ModuleNotFoundError` for `pixelle_video.tts_workflow_family`.

- [ ] **Step 3: Implement the unified family module**

Create `pixelle_video/tts_workflow_family.py`:

```python
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

        nested = _infer_family_from_workflow(node)
        if nested is not None:
            return nested

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
```

- [ ] **Step 4: Rewire the old IndexTTS2 wrapper through the unified module**

In `pixelle_video/tts_workflow_contract.py`, replace the body of `is_index_tts2_workflow_key` with:

```python
from pixelle_video.tts_workflow_family import infer_tts_workflow_family


def is_index_tts2_workflow_key(workflow_key: Any) -> bool:
    return infer_tts_workflow_family(workflow_key) == "indextts2"
```

Keep the existing public function name for compatibility.

- [ ] **Step 5: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_tts_service_workflow_params.py -k "tts_workflow_family or index_tts2" -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add pixelle_video/tts_workflow_family.py pixelle_video/tts_workflow_contract.py tests/test_tts_service_workflow_params.py
git commit -m "refactor: 统一 TTS 工作流家族识别"
git push
```

---

### Task 2: Switch Default Local TTS to OmniVoice Longform

**Files:**
- Modify: `pixelle_video/config/workflow_defaults.py`
- Modify: `config.yaml`
- Modify: `config.example.yaml`
- Test: `tests/test_tts_comfyui_defaults.py`
- Test: `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Write failing tests for default workflow selection and prerequisite workflow presence**

Append to `tests/test_selfhost_workflows.py`:

```python
def test_omnivoice_api_workflows_exist_before_default_switch():
    assert Path("workflows/selfhost/tts_omnivoice_longform_bf16.json").exists()
    assert Path("workflows/selfhost/tts_omnivoice_clone_duration_bf16.json").exists()
```

Append to `tests/test_tts_comfyui_defaults.py`:

```python
def test_builtin_default_tts_workflow_is_omnivoice_longform():
    from pixelle_video.config.workflow_defaults import DEFAULT_TTS_WORKFLOW

    assert DEFAULT_TTS_WORKFLOW == "selfhost/tts_omnivoice_longform_bf16.json"
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py tests/test_tts_comfyui_defaults.py -k "omnivoice_api_workflows_exist or default_tts_workflow_is_omnivoice" -v
```

Expected: FAIL until the API workflow plan has completed and default config still references IndexTTS2.

- [ ] **Step 3: Update defaults**

In `pixelle_video/config/workflow_defaults.py`, set:

```python
DEFAULT_TTS_WORKFLOW = "selfhost/tts_omnivoice_longform_bf16.json"
```

In `config.yaml` and `config.example.yaml`, set the local TTS default workflow to:

```yaml
default_workflow: selfhost/tts_omnivoice_longform_bf16.json
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_selfhost_workflows.py tests/test_tts_comfyui_defaults.py -k "omnivoice_api_workflows_exist or default_tts_workflow_is_omnivoice" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/config/workflow_defaults.py config.yaml config.example.yaml tests/test_selfhost_workflows.py tests/test_tts_comfyui_defaults.py
git commit -m "feat: 默认 TTS 切换到 OmniVoice 长文本工作流"
git push
```

---

### Task 3: Propagate OmniVoice Runtime Parameters Through TTS API and Service

**Files:**
- Modify: `api/schemas/tts.py`
- Modify: `api/routers/tts.py`
- Modify: `pixelle_video/services/tts_service.py`
- Test: `tests/test_tts_service_workflow_params.py`

- [ ] **Step 1: Write failing tests for `duration` and `reference_audio_text` propagation**

Append to `tests/test_tts_service_workflow_params.py`:

```python
@pytest.mark.asyncio
async def test_tts_service_passes_omnivoice_duration_to_workflow(monkeypatch):
    captured = {}

    async def fake_execute(workflow_input, workflow_params, workflow_info):
        captured["workflow_input"] = workflow_input
        captured["workflow_params"] = dict(workflow_params)
        return SimpleNamespace(status="completed", audios=["output.flac"], files=[], outputs={})

    service = TTSService(api_key="dummy")
    monkeypatch.setattr(service, "_execute_workflow", fake_execute)
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None: {
            "key": "selfhost/tts_omnivoice_clone_duration_bf16.json",
            "path": "workflows/selfhost/tts_omnivoice_clone_duration_bf16.json",
            "source": "selfhost",
        },
    )

    await service.generate(
        text="short line",
        workflow="selfhost/tts_omnivoice_clone_duration_bf16.json",
        ref_audio="ref.wav",
        reference_audio_text="reference transcript",
        duration=8.0,
    )

    assert captured["workflow_params"]["duration"] == 8.0
    assert captured["workflow_params"]["reference_audio_text"] == "reference transcript"
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_tts_service_workflow_params.py -k "omnivoice_duration" -v
```

Expected: FAIL if the schema/router or service strips the new parameters.

- [ ] **Step 3: Add schema fields for direct TTS API use**

In `api/schemas/tts.py`, add optional fields to `TTSSynthesizeRequest`:

```python
duration: Optional[float] = Field(
    None,
    description="Target duration in seconds for workflows that expose a duration parameter.",
)
reference_audio_text: Optional[str] = Field(
    None,
    description="Transcript of the reference audio for voice-clone workflows.",
)
```

- [ ] **Step 4: Forward the new request fields in the router**

In `api/routers/tts.py`, after `ref_audio` handling, add:

```python
if request.duration is not None:
    tts_params["duration"] = request.duration
if request.reference_audio_text:
    tts_params["reference_audio_text"] = request.reference_audio_text
```

- [ ] **Step 5: Keep service compatibility with existing aliases**

In `pixelle_video/services/tts_service.py`, keep the current `ref_audio_text` and `prompt_text` compatibility path, then add canonical handling:

```python
ref_audio_text = params.pop("reference_audio_text", None)
if ref_audio_text is None:
    ref_audio_text = params.pop("ref_audio_text", None)
if ref_audio_text is None:
    ref_audio_text = params.pop("prompt_text", None)
else:
    params.pop("ref_audio_text", None)
    params.pop("prompt_text", None)
```

Then call `build_ref_audio_text_params(...)` exactly as today so workflows exposing `reference_audio_text` receive that value.

- [ ] **Step 6: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_tts_service_workflow_params.py -k "omnivoice_duration or reference_audio_text or missing_required" -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add api/schemas/tts.py api/routers/tts.py pixelle_video/services/tts_service.py tests/test_tts_service_workflow_params.py
git commit -m "feat: 支持 OmniVoice 时长与参考文本参数"
git push
```

---

### Task 4: Integrate OmniVoice Voice Profiles

**Files:**
- Modify: `pixelle_video/services/tts_voice_profiles.py`
- Test: `tests/test_tts_voice_profiles.py`

- [ ] **Step 1: Write failing tests for OmniVoice profile slugging and filtering**

Append to `tests/test_tts_voice_profiles.py`:

```python
def test_build_voice_profile_name_appends_omnivoice_suffix():
    assert (
        tts_voice_profiles.build_voice_profile_name(
            "班哥",
            "selfhost/tts_omnivoice_longform_bf16.json",
        )
        == "班哥-omnivoice"
    )


def test_list_voice_profiles_filters_omnivoice_profiles(tmp_path):
    manifest_path = tmp_path / "reference_audio" / "voice_profiles.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "id": "omnivoice",
                        "name": "班哥-omnivoice",
                        "model_slug": "omnivoice",
                        "workflow_key": "selfhost/tts_omnivoice_longform_bf16.json",
                        "audio_path": "reference_audio/omnivoice/bange.wav",
                        "ref_audio_text": "大家好，这是参考音频文本。",
                    },
                    {
                        "id": "indextts2",
                        "name": "班哥-indextts2",
                        "model_slug": "indextts2",
                        "workflow_key": "selfhost/tts_index2.json",
                        "audio_path": "reference_audio/indextts2/bange.wav",
                        "ref_audio_text": "大家好，这是参考音频文本。",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    profiles = tts_voice_profiles.list_voice_profiles(
        "selfhost/tts_omnivoice_longform_bf16.json",
        manifest_path=manifest_path,
    )

    assert [profile["id"] for profile in profiles] == ["omnivoice"]
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_tts_voice_profiles.py -k "omnivoice" -v
```

Expected: FAIL until voice profile slug inference uses the unified family module.

- [ ] **Step 3: Use workflow family detection for model slug inference**

In `pixelle_video/services/tts_voice_profiles.py`, import:

```python
from pixelle_video.tts_workflow_family import infer_tts_workflow_family
```

Then update slug inference:

```python
def infer_tts_model_slug(workflow_key: str | None) -> str:
    family = infer_tts_workflow_family(workflow_key)
    if family != "generic":
        return family

    workflow_name = Path(str(workflow_key or "")).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", workflow_name).strip("-")
    return slug or "tts"
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_tts_voice_profiles.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/services/tts_voice_profiles.py tests/test_tts_voice_profiles.py
git commit -m "feat: 接入 OmniVoice 保存音色识别"
git push
```

---

### Task 5: Add Dedicated OmniVoice Master-Track Longform Block Planner

**Files:**
- Create: `pixelle_video/services/omnivoice_longform_blocks.py`
- Test: `tests/test_tts_segmentation.py`

- [ ] **Step 1: Write failing tests for longform block planning**

Append to `tests/test_tts_segmentation.py`:

```python
from pixelle_video.services.omnivoice_longform_blocks import (
    build_omnivoice_longform_block_plan,
)


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

    combined = "".join(block.text for block in plan.blocks)
    assert "3.14" in combined
    assert "example.com" in combined
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_tts_segmentation.py -k "omnivoice_longform" -v
```

Expected: FAIL because `pixelle_video.services.omnivoice_longform_blocks` does not exist.

- [ ] **Step 3: Implement the planner**

Create `pixelle_video/services/omnivoice_longform_blocks.py`:

```python
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
        return asdict(self)


def build_omnivoice_longform_block_plan(
    text: str,
    *,
    max_chars_per_block: int = 6000,
    hard_max_chars_per_block: int = 9000,
) -> OmniVoiceLongformBlockPlan:
    source_text = text or ""
    text_hash = hashlib.sha1(source_text.encode("utf-8")).hexdigest()
    blocks: list[OmniVoiceLongformBlock] = []

    cursor = 0
    while cursor < len(source_text):
        target = min(cursor + max_chars_per_block, len(source_text))
        if target >= len(source_text):
            end = len(source_text)
            boundary_type = "end_of_text"
            split_reason = "end_of_text"
        else:
            end = _find_block_boundary(
                source_text,
                cursor,
                target,
                hard_max_chars_per_block,
            )
            boundary_type = "sentence"
            split_reason = "sentence_boundary"

        if end <= cursor:
            end = min(cursor + hard_max_chars_per_block, len(source_text))
            boundary_type = "hard_limit"
            split_reason = "hard_limit"

        segment = source_text[cursor:end]
        blocks.append(
            OmniVoiceLongformBlock(
                id=f"block-{len(blocks) + 1}",
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
        plan_id=text_hash[:12],
        mode="omnivoice_master_track_longform",
        source_text_hash=text_hash,
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
    return hard_end


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
    closing_chars = set("\"'”’）)】]》>、 \n\r\t")
    cursor = index
    while cursor < hard_end and text[cursor] in closing_chars:
        cursor += 1
    return cursor
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_tts_segmentation.py -k "omnivoice_longform" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/services/omnivoice_longform_blocks.py tests/test_tts_segmentation.py
git commit -m "feat: 新增 OmniVoice 主音轨长文本分块规划"
git push
```

---

### Task 6: Integrate OmniVoice Blocks into Master-Track Audio Synthesis

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_index_tts2_timing_profile.py`

- [ ] **Step 1: Write failing tests for OmniVoice master-track block execution**

Append to `tests/test_index_tts2_timing_profile.py`:

```python
@pytest.mark.asyncio
async def test_standard_pipeline_master_track_omnivoice_uses_longform_blocks(monkeypatch, tmp_path):
    class RecordingTts:
        def __init__(self):
            self.calls = []

        async def __call__(self, **params):
            self.calls.append(dict(params))
            output_path = Path(params["output_path"])
            output_path.write_bytes(b"audio")
            return str(output_path)

    core = _FakeCore()
    core.tts = RecordingTts()
    pipeline = StandardPipeline(core)
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-omnivoice-master",
        tts_inference_mode="comfyui",
        tts_workflow="selfhost/tts_omnivoice_longform_bf16.json",
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
                text=("第一段结束。第二段继续讲解系统设计。第三段补充架构决策。第四段收尾。") * 220,
                source_frame_indices=[0],
            )
        ]
    )

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", lambda source, output: output)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda path: 1.0)
    monkeypatch.setattr(pipeline, "_concat_audio_files", lambda paths, output, **kwargs: Path(output).write_bytes(b"audio"))

    await pipeline._synthesize_hyperframes_audio(ctx)

    assert len(core.tts.calls) > 1
    assert all(call["workflow"] == "selfhost/tts_omnivoice_longform_bf16.json" for call in core.tts.calls)
    assert all(call["reference_audio_text"] == "大家好，这是参考音频文本。" for call in core.tts.calls)
    assert ctx.observability["tts_segmentation"]["plans"][0]["mode"] == "omnivoice_master_track_longform"
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_index_tts2_timing_profile.py -k "master_track_omnivoice" -v
```

Expected: FAIL because master-track synthesis still treats OmniVoice as a generic TTS workflow.

- [ ] **Step 3: Add a helper to decide when OmniVoice master-track protection applies**

In `pixelle_video/pipelines/standard.py`, import:

```python
from pixelle_video.services.omnivoice_longform_blocks import build_omnivoice_longform_block_plan
from pixelle_video.tts_workflow_family import infer_tts_workflow_family
```

Add helper methods near the existing TTS audio helpers:

```python
def _uses_omnivoice_longform_workflow(self, workflow_key: str | None) -> bool:
    return infer_tts_workflow_family(workflow_key) == "omnivoice"


def _should_use_omnivoice_longform_blocks(self, config: StoryboardConfig, text: str) -> bool:
    if not self._uses_omnivoice_longform_workflow(config.tts_workflow):
        return False
    if getattr(config, "tts_audio_strategy", "per_frame") != "master_track":
        return False
    return len(text or "") > 6000
```

- [ ] **Step 4: Integrate block planning into master-track synthesis**

Inside the master-track path that currently sends one audio block to TTS, branch before calling `core.tts(...)`:

```python
if self._should_use_omnivoice_longform_blocks(config, block.text):
    plan = build_omnivoice_longform_block_plan(block.text)
    ctx.observability.setdefault("tts_segmentation", {}).setdefault("plans", []).append(plan.to_dict())
    generated_paths = []
    for index, omnivoice_block in enumerate(plan.blocks, start=1):
        output_path = str(Path(ctx.task_dir) / f"master_omnivoice_{block.id}_{index:03d}.flac")
        audio_path = await self.core.tts(
            text=omnivoice_block.text,
            workflow=config.tts_workflow,
            ref_audio=config.ref_audio,
            reference_audio_text=config.ref_audio_text,
            output_path=output_path,
        )
        generated_paths.append(audio_path)
    merged_path = str(Path(ctx.task_dir) / f"master_omnivoice_{block.id}.flac")
    self._concat_audio_files(generated_paths, merged_path)
    return merged_path
```

Adapt names to the exact local variables in the target method; preserve existing IndexTTS2 and generic paths.

- [ ] **Step 5: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_index_tts2_timing_profile.py -k "master_track_omnivoice or index_tts2" -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add pixelle_video/pipelines/standard.py tests/test_index_tts2_timing_profile.py
git commit -m "feat: 接入 OmniVoice 主音轨长文本分块"
git push
```

---

### Task 7: Align Frontend Workflow Selection and Copy

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`

- [ ] **Step 1: Update user-facing copy**

Replace copy that describes TTS segmentation as IndexTTS2-specific with model-neutral wording:

Chinese:

```json
"tts.split_mode_hint": "长文本会根据所选 TTS 工作流自动使用合适的内部或外部分段策略。"
```

English:

```json
"tts.split_mode_hint": "Long text uses the appropriate internal or external segmentation strategy for the selected TTS workflow."
```

- [ ] **Step 2: Keep both OmniVoice workflows selectable**

Ensure TTS workflow select boxes list both:

- `selfhost/tts_omnivoice_longform_bf16.json`
- `selfhost/tts_omnivoice_clone_duration_bf16.json`

Do not hide IndexTTS2 or Edge TTS workflows.

- [ ] **Step 3: Run focused UI tests**

Run:

```powershell
python -m pytest tests/test_style_config_storyboard_planning_ui.py tests/test_digital_tts_config.py -k "tts_workflow" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add web/components/style_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json
git commit -m "docs: 调整 TTS 工作流选择说明"
git push
```

---

### Task 8: Final Verification

**Files:**
- Modify: `tests/test_selfhost_workflows.py`

- [ ] **Step 1: Add cross-plan dependency doc assertions**

Append to `tests/test_selfhost_workflows.py`:

```python
def test_omnivoice_api_workflow_dependency_docs_exist():
    docs = [
        Path("workflows/down/tts_omnivoice_longform_bf16_依赖与下载说明.md"),
        Path("workflows/down/tts_omnivoice_clone_duration_bf16_依赖与下载说明.md"),
    ]
    for doc_path in docs:
        text = doc_path.read_text(encoding="utf-8")
        assert "ModelScope" in text
        assert "OmniVoice-bf16" in text
        assert "whisper-large-v3" in text
```

- [ ] **Step 2: Run full focused verification**

Run:

```powershell
python -m pytest tests/test_tts_service_workflow_params.py tests/test_tts_voice_profiles.py tests/test_selfhost_workflows.py tests/test_tts_comfyui_defaults.py tests/test_tts_segmentation.py tests/test_index_tts2_timing_profile.py -v
```

Expected: PASS.

- [ ] **Step 3: Check git status**

Run:

```powershell
git status --short
```

Expected: no unstaged implementation changes for this task.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_selfhost_workflows.py
git commit -m "test: 验证 OmniVoice 系统集成依赖"
git push
```

## Self-Review

- Spec coverage:
  - Unified workflow family detection is covered by Task 1.
  - Default TTS switch to OmniVoice longform is covered by Task 2.
  - `duration` and `reference_audio_text` propagation is covered by Task 3.
  - OmniVoice saved voice profiles are covered by Task 4.
  - Dedicated longform block planning is covered by Task 5.
  - Master-track integration is covered by Task 6.
  - Frontend copy and workflow selection are covered by Task 7.
  - Cross-plan dependency documentation verification is covered by Task 8.
- Placeholder scan:
  - No placeholder markers remain.
  - Code steps include concrete snippets and exact paths.
- Type consistency:
  - Workflow family values are consistently `edge`, `indextts2`, `omnivoice`, and `generic`.
  - The longform block mode is consistently `omnivoice_master_track_longform`.
  - The canonical reference transcript parameter is `reference_audio_text`; compatibility aliases are `ref_audio_text` and `prompt_text`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-04-omnivoice-longform-master-track-implementation.md`. Execute `docs/superpowers/plans/2026-05-04-omnivoice-api-workflows-implementation.md` first, then return to this plan.

Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.
