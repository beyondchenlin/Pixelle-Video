# Pixelle TTS Edge Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the third-party Edge TTS workflow dependency with a Pixelle-owned ComfyUI plugin, keep `text`/`voice`/`speed` workflow parameter injection intact, and make deployment to `E:\comfyui\comfyui\custom_nodes` repeatable.

**Architecture:** Keep the source of truth for the ComfyUI plugin inside the repository at `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS`, deploy it with a repository-owned sync script, and rewrite `workflows/selfhost/tts_edge.json` to use `PixelleEdgeTTS` plus a tiny Pixelle-owned float input node. Runtime audio synthesis will call Edge TTS directly, decode through FFmpeg, and raise explicit errors instead of returning silent placeholder waveforms.

**Tech Stack:** Python 3.11+, pytest, edge-tts, FFmpeg subprocess decode, ComfyUI custom nodes, ComfyKit workflow parser.

---

### Task 1: Lock The `tts_edge.json` Workflow Contract

**Files:**
- Modify: `tests/test_selfhost_workflows.py`
- Modify: `workflows/selfhost/tts_edge.json`

- [ ] **Step 1: Write the failing workflow regression test**

Append this test to `tests/test_selfhost_workflows.py`:

```python
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
```

- [ ] **Step 2: Run the workflow test to verify it fails**

Run:

```powershell
uv run pytest tests/test_selfhost_workflows.py -k "tts_edge or tts_index2" -v
```

Expected:

```text
FAILED tests/test_selfhost_workflows.py::test_tts_edge_workflow_is_parseable_and_uses_pixelle_nodes
```

- [ ] **Step 3: Rewrite `workflows/selfhost/tts_edge.json` to the Pixelle-owned workflow**

Replace the file with:

```json
{
  "1": {
    "inputs": {
      "text": [
        "3",
        0
      ],
      "voice": [
        "7",
        0
      ],
      "speed": [
        "8",
        0
      ],
      "pitch": 0
    },
    "class_type": "PixelleEdgeTTS",
    "_meta": {
      "title": "Pixelle Edge TTS"
    }
  },
  "3": {
    "inputs": {
      "value": "床前明月光，疑是地上霜。"
    },
    "class_type": "PrimitiveStringMultiline",
    "_meta": {
      "title": "$text.value!"
    }
  },
  "4": {
    "inputs": {
      "filename_prefix": "audio/ComfyUI",
      "quality": "V0",
      "audioUI": "",
      "audio": [
        "1",
        0
      ]
    },
    "class_type": "SaveAudioMP3",
    "_meta": {
      "title": "Save Audio (MP3)"
    }
  },
  "7": {
    "inputs": {
      "value": "zh-CN-YunjianNeural"
    },
    "class_type": "PrimitiveStringMultiline",
    "_meta": {
      "title": "$voice.value"
    }
  },
  "8": {
    "inputs": {
      "value": 1.0
    },
    "class_type": "PixelleFloatInput",
    "_meta": {
      "title": "$speed.value"
    }
  }
}
```

- [ ] **Step 4: Run the workflow test to verify it passes**

Run:

```powershell
uv run pytest tests/test_selfhost_workflows.py -k "tts_edge or tts_index2" -v
```

Expected:

```text
PASSED tests/test_selfhost_workflows.py::test_tts_edge_workflow_is_parseable_and_uses_pixelle_nodes
PASSED tests/test_selfhost_workflows.py::test_tts_index2_uses_builtin_multiline_string_input
```

- [ ] **Step 5: Do not commit yet**

Reason:

```text
The rewritten workflow references Pixelle-owned nodes that are introduced in Task 2.
Keep these changes local until the plugin source exists, then commit the workflow contract and plugin together.
```

### Task 2: Add The Pixelle ComfyUI TTS Plugin Source

**Files:**
- Modify: `tests/test_selfhost_workflows.py`
- Modify: `workflows/selfhost/tts_edge.json`
- Create: `tests/test_pixelle_tts_custom_node.py`
- Create: `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/__init__.py`
- Create: `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/pixelle_edge_tts.py`
- Create: `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/requirements.txt`

- [ ] **Step 1: Write the failing plugin unit tests**

Create `tests/test_pixelle_tts_custom_node.py` with:

```python
import importlib.util
from pathlib import Path

import pytest


PLUGIN_PATH = Path("tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/pixelle_edge_tts.py")


def _load_plugin_module():
    spec = importlib.util.spec_from_file_location("pixelle_edge_tts_plugin", PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_speed_multiplier_to_rate_formats_positive_and_negative_values():
    module = _load_plugin_module()

    assert module.speed_multiplier_to_rate(1.0) == "+0%"
    assert module.speed_multiplier_to_rate(1.2) == "+20%"
    assert module.speed_multiplier_to_rate(0.85) == "-15%"


def test_normalize_voice_id_accepts_real_edge_voice_ids():
    module = _load_plugin_module()

    assert module.normalize_voice_id("zh-CN-YunjianNeural") == "zh-CN-YunjianNeural"


def test_normalize_voice_id_rejects_display_labels():
    module = _load_plugin_module()

    with pytest.raises(ValueError, match="real Edge voice ID"):
        module.normalize_voice_id("[Chinese] zh-CN Yunjian")


def test_pixelle_float_input_returns_float_value():
    module = _load_plugin_module()
    node = module.PixelleFloatInput()

    assert node.get_value(1.25) == (1.25,)
```

- [ ] **Step 2: Run the plugin tests to verify they fail**

Run:

```powershell
uv run pytest tests/test_pixelle_tts_custom_node.py -v
```

Expected:

```text
FAILED tests/test_pixelle_tts_custom_node.py::test_speed_multiplier_to_rate_formats_positive_and_negative_values
```

- [ ] **Step 3: Create the plugin implementation**

Create `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/pixelle_edge_tts.py` with:

```python
import asyncio
import concurrent.futures
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts


VOICE_ID_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]+)+Neural$")
RETRYABLE_EXCEPTIONS = (
    RuntimeError,
    ConnectionError,
)


def speed_multiplier_to_rate(speed: float) -> str:
    speed_percent = int(round((float(speed) - 1.0) * 100))
    return "+0%" if speed_percent == 0 else f"{speed_percent:+d}%"


def normalize_voice_id(voice: str) -> str:
    cleaned = (voice or "").strip()
    if not cleaned:
        raise ValueError("voice must not be empty")
    if cleaned.startswith("["):
        raise ValueError("Use a real Edge voice ID instead of a display label")
    if not VOICE_ID_PATTERN.match(cleaned):
        raise ValueError(f"Invalid Edge voice ID: {cleaned}")
    return cleaned


class PixelleFloatInput:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("FLOAT",)
    FUNCTION = "get_value"
    CATEGORY = "Pixelle/TTS"

    def get_value(self, value):
        return (float(value),)


class PixelleEdgeTTS:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "placeholder": "Enter text to convert to speech"}),
                "voice": ("STRING", {"default": "zh-CN-YunjianNeural"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.1}),
                "pitch": ("INT", {"default": 0, "min": -20, "max": 20, "step": 1}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "tts"
    CATEGORY = "Pixelle/TTS"

    async def _synthesize_bytes(self, text: str, voice: str, rate: str, pitch: int) -> bytes:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=f"{pitch:+d}Hz",
        )
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        audio_bytes = b"".join(audio_chunks)
        if not audio_bytes:
            raise RuntimeError("Edge TTS returned no audio bytes")
        return audio_bytes

    def _decode_audio_bytes(self, audio_bytes: bytes):
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("ffmpeg was not found in PATH")

        sample_rate = 24000
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(audio_bytes)

        try:
            result = subprocess.run(
                [
                    ffmpeg_path,
                    "-v",
                    "error",
                    "-i",
                    str(temp_path),
                    "-f",
                    "f32le",
                    "-acodec",
                    "pcm_f32le",
                    "-ac",
                    "1",
                    "-ar",
                    str(sample_rate),
                    "pipe:1",
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="ignore").strip()
                raise RuntimeError(f"ffmpeg decode failed: {stderr or 'unknown ffmpeg error'}")
            if not result.stdout:
                raise RuntimeError("ffmpeg decode produced no PCM output")

            import torch

            waveform = torch.frombuffer(bytearray(result.stdout), dtype=torch.float32).clone()
            if waveform.numel() == 0:
                raise RuntimeError("decoded waveform is empty")
            peak = float(waveform.abs().max())
            if peak <= 0.0:
                raise RuntimeError("decoded waveform is silent")
            waveform = (waveform / peak).unsqueeze(0).unsqueeze(0)
            return {"waveform": waveform, "sample_rate": sample_rate}
        finally:
            temp_path.unlink(missing_ok=True)

    async def _generate_audio(self, text: str, voice: str, speed: float, pitch: int):
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("text must not be empty")

        voice_id = normalize_voice_id(voice)
        rate = speed_multiplier_to_rate(speed)
        audio_bytes = await self._synthesize_bytes(cleaned_text, voice_id, rate, pitch)
        return self._decode_audio_bytes(audio_bytes)

    def tts(self, text, voice, speed, pitch):
        def run_async():
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self._generate_audio(text, voice, speed, pitch))
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            audio = executor.submit(run_async).result()
        return (audio,)
```

Create `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/__init__.py` with:

```python
from .pixelle_edge_tts import PixelleEdgeTTS, PixelleFloatInput


NODE_CLASS_MAPPINGS = {
    "PixelleEdgeTTS": PixelleEdgeTTS,
    "PixelleFloatInput": PixelleFloatInput,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "PixelleEdgeTTS": "Pixelle Edge TTS",
    "PixelleFloatInput": "Pixelle Float Input",
}
```

Create `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/requirements.txt` with:

```text
edge-tts==7.2.7
certifi>=2025.10.5
```

- [ ] **Step 4: Run the workflow and plugin tests together**

Run:

```powershell
uv run pytest tests/test_selfhost_workflows.py tests/test_pixelle_tts_custom_node.py -v
```

Expected:

```text
PASSED tests/test_selfhost_workflows.py::test_tts_edge_workflow_is_parseable_and_uses_pixelle_nodes
PASSED tests/test_pixelle_tts_custom_node.py::test_speed_multiplier_to_rate_formats_positive_and_negative_values
PASSED tests/test_pixelle_tts_custom_node.py::test_normalize_voice_id_accepts_real_edge_voice_ids
PASSED tests/test_pixelle_tts_custom_node.py::test_normalize_voice_id_rejects_display_labels
PASSED tests/test_pixelle_tts_custom_node.py::test_pixelle_float_input_returns_float_value
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_selfhost_workflows.py workflows/selfhost/tts_edge.json tests/test_pixelle_tts_custom_node.py tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS
git commit -m "feat: add pixelle comfyui tts plugin source"
```

### Task 3: Add A Repeatable Plugin Sync Script

**Files:**
- Create: `tests/test_sync_pixelle_tts_custom_node.py`
- Create: `tools/sync_pixelle_tts_custom_node.py`

- [ ] **Step 1: Write the failing sync-script test**

Create `tests/test_sync_pixelle_tts_custom_node.py` with:

```python
from pathlib import Path

from tools.sync_pixelle_tts_custom_node import sync_tree


def test_sync_tree_replaces_existing_files(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "nested").mkdir(parents=True)
    target.mkdir()

    (source / "nested" / "plugin.py").write_text("new", encoding="utf-8")
    (target / "old.py").write_text("old", encoding="utf-8")

    sync_tree(source, target)

    assert (target / "nested" / "plugin.py").read_text(encoding="utf-8") == "new"
    assert not (target / "old.py").exists()
```

- [ ] **Step 2: Run the sync test to verify it fails**

Run:

```powershell
uv run pytest tests/test_sync_pixelle_tts_custom_node.py -v
```

Expected:

```text
FAILED tests/test_sync_pixelle_tts_custom_node.py::test_sync_tree_replaces_existing_files
```

- [ ] **Step 3: Implement the sync script**

Create `tools/sync_pixelle_tts_custom_node.py` with:

```python
import argparse
import shutil
import subprocess
from pathlib import Path


DEFAULT_SOURCE = Path("tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS")
DEFAULT_TARGET = Path(r"E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS")
DEFAULT_PYTHON = Path(r"C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe")


def sync_tree(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"source path does not exist: {source}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def install_requirements(python_executable: Path, requirements_file: Path) -> None:
    subprocess.run(
        [str(python_executable), "-m", "pip", "install", "-r", str(requirements_file)],
        check=True,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Sync the Pixelle TTS custom node into ComfyUI.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--target", default=str(DEFAULT_TARGET))
    parser.add_argument("--python", dest="python_executable", default=str(DEFAULT_PYTHON))
    parser.add_argument("--skip-install", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    source = Path(args.source)
    target = Path(args.target)
    python_executable = Path(args.python_executable)

    sync_tree(source, target)

    if not args.skip_install:
        install_requirements(python_executable, target / "requirements.txt")

    print(f"Synced Pixelle TTS custom node to: {target}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the sync test to verify it passes**

Run:

```powershell
uv run pytest tests/test_sync_pixelle_tts_custom_node.py -v
```

Expected:

```text
PASSED tests/test_sync_pixelle_tts_custom_node.py::test_sync_tree_replaces_existing_files
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_sync_pixelle_tts_custom_node.py tools/sync_pixelle_tts_custom_node.py
git commit -m "feat: add pixelle tts custom node sync script"
```

### Task 4: Update The TTS Edge Dependency Guide

**Files:**
- Modify: `workflows/down/tts_edge_依赖与下载说明.md`

- [ ] **Step 1: Replace the dependency and installation sections**

Make these content changes:

```markdown
- 将 `EdgeTTS` 依赖改为 `PixelleEdgeTTS`
- 删除 `easy showAnything`、`easy float` 作为本工作流依赖
- 新增仓库源码路径：`tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS`
- 新增部署目标路径：`E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS`
- 新增同步命令：`uv run python tools/sync_pixelle_tts_custom_node.py`
- 新增 ComfyUI Python 依赖安装说明，说明由同步脚本触发 `requirements.txt` 安装
- 将验证节点列表改为 `PixelleEdgeTTS`、`PixelleFloatInput`、`SaveAudioMP3`、`PrimitiveStringMultiline`
- 将“静音 MP3”根因说明改为第三方节点问题已被 Pixelle 自有节点替代，并说明当前节点在 FFmpeg 或网络失败时会显式报错
```

- [ ] **Step 2: Verify the document mentions the new source and deployment model**

Run:

```powershell
Get-Content -Encoding UTF8 'workflows/down/tts_edge_依赖与下载说明.md' | Select-String -Pattern 'ComfyUI-Pixelle-TTS|PixelleEdgeTTS|sync_pixelle_tts_custom_node.py|E:\\comfyui\\comfyui\\custom_nodes'
```

Expected:

```text
ComfyUI-Pixelle-TTS
PixelleEdgeTTS
sync_pixelle_tts_custom_node.py
E:\comfyui\comfyui\custom_nodes
```

- [ ] **Step 3: Commit**

Run:

```powershell
git add 'workflows/down/tts_edge_依赖与下载说明.md'
git commit -m "docs: update tts edge workflow dependency guide"
```

### Task 5: Deploy And Verify The New TTS Workflow End To End

**Files:**
- Verify: `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/*`
- Verify: `workflows/selfhost/tts_edge.json`

- [ ] **Step 1: Run the repository test suite for all touched test files**

Run:

```powershell
uv run pytest tests/test_selfhost_workflows.py tests/test_pixelle_tts_custom_node.py tests/test_sync_pixelle_tts_custom_node.py tests/test_tts_util.py -v
```

Expected:

```text
... all selected tests PASSED ...
```

- [ ] **Step 2: Sync the plugin source into the active ComfyUI instance**

Run:

```powershell
uv run python tools/sync_pixelle_tts_custom_node.py --target 'E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS' --python 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe'
```

Expected:

```text
Synced Pixelle TTS custom node to: E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS
```

- [ ] **Step 3: Restart ComfyUI and verify the new nodes are registered**

Run:

```powershell
$resp = Invoke-RestMethod 'http://127.0.0.1:8000/object_info'
@('PixelleEdgeTTS', 'PixelleFloatInput', 'SaveAudioMP3', 'PrimitiveStringMultiline') | ForEach-Object {
    if ($resp.PSObject.Properties.Name -contains $_) {
        "FOUND`t$_"
    } else {
        "MISSING`t$_"
    }
}
```

Expected:

```text
FOUND    PixelleEdgeTTS
FOUND    PixelleFloatInput
FOUND    SaveAudioMP3
FOUND    PrimitiveStringMultiline
```

- [ ] **Step 4: Run the workflow and confirm the output is audible**

Run:

```powershell
@'
import sys
sys.path.insert(0, r'E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS')
from pixelle_edge_tts import PixelleEdgeTTS

node = PixelleEdgeTTS()
audio = node.tts('床前明月光，疑是地上霜。', 'zh-CN-YunjianNeural', 1.0, 0)[0]
print(audio['sample_rate'])
print(float(audio['waveform'].abs().max()))
'@ | & 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -
```

Expected:

```text
24000
0.5 or greater non-zero amplitude
```

- [ ] **Step 5: Confirm FFmpeg failures are explicit**

Run:

```powershell
@'
import sys
sys.path.insert(0, r'E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS')
import shutil
from pixelle_edge_tts import PixelleEdgeTTS

original_which = shutil.which
shutil.which = lambda _name: None
try:
    node = PixelleEdgeTTS()
    node._decode_audio_bytes(b'not-real-audio')
except Exception as exc:
    print(type(exc).__name__)
    print(str(exc))
finally:
    shutil.which = original_which
'@ | & 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -
```

Expected:

```text
RuntimeError
ffmpeg was not found in PATH
```

- [ ] **Step 6: Confirm the working tree is clean after verification**

Run:

```powershell
git status --short
```

Expected:

```text
[no output]
```
