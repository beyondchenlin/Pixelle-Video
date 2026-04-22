# Pixelle HyperFrames Rendering Implementation Plan

> **Status:** Superseded as the primary rollout plan by the compiled-project architecture in
> [2026-04-22-pixelle-hyperframes-compiled-project-design.md](/d:/demo1/Pixelle/Pixelle/docs/superpowers/specs/2026-04-22-pixelle-hyperframes-compiled-project-design.md).
> This plan documents the earlier runtime-manifest approach and remains useful as historical context, but new implementation work should follow the compiled-project direction instead.
> Use [2026-04-22-pixelle-hyperframes-compiled-project-implementation.md](/d:/demo1/Pixelle/Pixelle/docs/superpowers/plans/2026-04-22-pixelle-hyperframes-compiled-project-implementation.md) as the active execution plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Pixelle's `segment.mp4 + concat` final assembly with a HyperFrames render pipeline driven by block-level IndexTTS2 audio, `Qwen3-ForcedAligner-0.6B` sentence timing, optional `auto-editor` silence trimming, and migrated HTML template shells.

**Architecture:** Python remains the system of record for storyboard generation, media generation, sentence/block planning, audio alignment, silence-remap metadata, and render-package export. A small Node bridge wraps `@hyperframes/producer` and renders one global HTML timeline where visual clips, captions, and master audio all share the same clock.

**Caption Timing Policy:** `primary = qwen_forced_aligner` for `known text + generated audio`; `fallback = funasr_transcribe` only for `audio-only` or missing-text inputs. `FunClip` is an allowed helper when a ready-made `SRT` interoperability artifact is useful, but it does not replace the primary timing path.

**Tech Stack:** Python 3.11+, pytest, `qwen-asr`, ModelScope, `auto-editor`, Node.js 22+, `@hyperframes/producer`, FFmpeg, HyperFrames HTML/CSS compositions

**Non-Goal for V1:** Do not treat `FunASR` or `FunClip` as the normal subtitle source for Pixelle-generated tasks. They are fallback integrations that should remain behind an explicit strategy boundary.

---

### Task 1: Add render-contract models and config surface

**Files:**
- Create: `pixelle_video/models/render_package.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `config.example.yaml`
- Test: `tests/test_render_package_models.py`

- [ ] **Step 1: Write the failing model/config test**

```python
from pixelle_video.models.render_package import (
    AudioBlock,
    CaptionCue,
    RenderManifest,
    SentenceUnit,
    VisualClip,
)
from pixelle_video.models.storyboard import StoryboardConfig


def test_render_manifest_round_trip_and_timing_config_defaults():
    config = StoryboardConfig(media_width=1080, media_height=1920)
    assert config.tts_batching_mode == "paragraph"
    assert config.subtitle_alignment_engine == "qwen_forced_aligner"
    assert config.silence_trim_tool is None

    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        master_audio_path="output/task-1/master_audio.wav",
        audio_blocks=[AudioBlock(id="block-1", text="Sentence 1. Sentence 2.", audio_path="block-1.wav", start=0.0, end=4.2)],
        sentence_units=[SentenceUnit(id="s1", text="Sentence 1.", frame_indices=[0], block_id="block-1", source_start=0.0, source_end=2.0)],
        visual_clips=[VisualClip(id="v1", frame_index=0, start=0.0, end=2.0, media_path="01_image.png", media_type="image", track_index=0)],
        caption_cues=[CaptionCue(id="c1", text="Sentence 1", start=0.0, end=2.0, frame_indices=[0], style_profile="image_life_insights_light")],
    )

    data = manifest.to_dict()
    restored = RenderManifest.from_dict(data)
    assert restored.caption_cues[0].text == "Sentence 1"
    assert restored.audio_blocks[0].end == 4.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_package_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.models.render_package'`

- [ ] **Step 3: Write the model and config implementation**

```python
# pixelle_video/models/render_package.py
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class SentenceUnit:
    id: str
    text: str
    frame_indices: List[int]
    block_id: str
    source_start: float
    source_end: float
    remapped_start: Optional[float] = None
    remapped_end: Optional[float] = None


@dataclass
class AudioBlock:
    id: str
    text: str
    audio_path: str
    start: float
    end: float
    source_frame_indices: List[int] = field(default_factory=list)


@dataclass
class VisualClip:
    id: str
    frame_index: int
    start: float
    end: float
    media_path: str
    media_type: str
    track_index: int = 0


@dataclass
class CaptionCue:
    id: str
    text: str
    start: float
    end: float
    frame_indices: List[int]
    style_profile: str
    word_timings: Optional[List[Dict[str, float]]] = None


@dataclass
class RenderManifest:
    task_id: str
    title: str
    width: int
    height: int
    fps: int
    template_id: str
    master_audio_path: str
    audio_blocks: List[AudioBlock]
    sentence_units: List[SentenceUnit]
    visual_clips: List[VisualClip]
    caption_cues: List[CaptionCue]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RenderManifest":
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            width=data["width"],
            height=data["height"],
            fps=data["fps"],
            template_id=data["template_id"],
            master_audio_path=data["master_audio_path"],
            audio_blocks=[AudioBlock(**item) for item in data["audio_blocks"]],
            sentence_units=[SentenceUnit(**item) for item in data["sentence_units"]],
            visual_clips=[VisualClip(**item) for item in data["visual_clips"]],
            caption_cues=[CaptionCue(**item) for item in data["caption_cues"]],
        )
```

```python
# pixelle_video/models/storyboard.py (new config fields)
tts_batching_mode: str = "paragraph"
tts_batch_max_sentences: int = 8
tts_batch_max_chars: int = 220
subtitle_alignment_engine: str = "qwen_forced_aligner"
silence_trim_tool: Optional[str] = None
silence_trim_margin_ms: int = 120
render_backend: str = "hyperframes"
```

```yaml
# config.example.yaml
render:
  backend: hyperframes
  timing:
    tts_batching_mode: paragraph
    tts_batch_max_sentences: 8
    tts_batch_max_chars: 220
    subtitle_alignment_engine: qwen_forced_aligner
    silence_trim_tool: null
    silence_trim_margin_ms: 120
```

```python
# pixelle_video/services/persistence.py
def _config_to_dict(self, config: StoryboardConfig) -> Dict[str, Any]:
    return {
        "task_id": config.task_id,
        "n_storyboard": config.n_storyboard,
        "min_narration_words": config.min_narration_words,
        "max_narration_words": config.max_narration_words,
        "min_image_prompt_words": config.min_image_prompt_words,
        "max_image_prompt_words": config.max_image_prompt_words,
        "video_fps": config.video_fps,
        "tts_inference_mode": config.tts_inference_mode,
        "voice_id": config.voice_id,
        "tts_workflow": config.tts_workflow,
        "tts_speed": config.tts_speed,
        "ref_audio": config.ref_audio,
        "media_width": config.media_width,
        "media_height": config.media_height,
        "media_workflow": config.media_workflow,
        "media_negative_prompt": config.media_negative_prompt,
        "frame_template": config.frame_template,
        "template_params": config.template_params,
        "tts_batching_mode": config.tts_batching_mode,
        "tts_batch_max_sentences": config.tts_batch_max_sentences,
        "tts_batch_max_chars": config.tts_batch_max_chars,
        "subtitle_alignment_engine": config.subtitle_alignment_engine,
        "silence_trim_tool": config.silence_trim_tool,
        "silence_trim_margin_ms": config.silence_trim_margin_ms,
        "render_backend": config.render_backend,
    }


def _dict_to_config(self, data: Dict[str, Any]) -> StoryboardConfig:
    return StoryboardConfig(
        task_id=data.get("task_id"),
        n_storyboard=data.get("n_storyboard", 5),
        min_narration_words=data.get("min_narration_words", 5),
        max_narration_words=data.get("max_narration_words", 20),
        min_image_prompt_words=data.get("min_image_prompt_words", 30),
        max_image_prompt_words=data.get("max_image_prompt_words", 60),
        video_fps=data.get("video_fps", 30),
        tts_inference_mode=data.get("tts_inference_mode", "local"),
        voice_id=data.get("voice_id"),
        tts_workflow=data.get("tts_workflow"),
        tts_speed=data.get("tts_speed"),
        ref_audio=data.get("ref_audio"),
        media_width=data.get("media_width", data.get("image_width", 1024)),
        media_height=data.get("media_height", data.get("image_height", 1024)),
        media_workflow=data.get("media_workflow", data.get("image_workflow")),
        media_negative_prompt=data.get("media_negative_prompt"),
        frame_template=data.get("frame_template", "1080x1920/default.html"),
        template_params=data.get("template_params"),
        tts_batching_mode=data.get("tts_batching_mode", "paragraph"),
        tts_batch_max_sentences=data.get("tts_batch_max_sentences", 8),
        tts_batch_max_chars=data.get("tts_batch_max_chars", 220),
        subtitle_alignment_engine=data.get("subtitle_alignment_engine", "qwen_forced_aligner"),
        silence_trim_tool=data.get("silence_trim_tool"),
        silence_trim_margin_ms=data.get("silence_trim_margin_ms", 120),
        render_backend=data.get("render_backend", "hyperframes"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_package_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/render_package.py pixelle_video/models/storyboard.py pixelle_video/services/persistence.py config.example.yaml tests/test_render_package_models.py
git commit -m "feat: add hyperframes render package contract"
```

### Task 2: Build sentence planning and block-level TTS batching

**Files:**
- Create: `pixelle_video/services/timing_planner.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_timing_planner.py`

- [ ] **Step 1: Write the failing planning test**

```python
from pixelle_video.models.storyboard import StoryboardFrame
from pixelle_video.services.timing_planner import TimingPlanner


def test_timing_planner_keeps_sentence_boundaries_but_batches_into_paragraph_blocks():
    frames = [
        StoryboardFrame(index=0, narration="Sentence 1.", image_prompt="p1"),
        StoryboardFrame(index=1, narration="Sentence 2.", image_prompt="p2"),
        StoryboardFrame(index=2, narration="Sentence 3.", image_prompt="p3"),
    ]

    planner = TimingPlanner(mode="paragraph", max_sentences=2, max_chars=20)
    plan = planner.build(frames)

    assert [s.text for s in plan.sentences] == ["Sentence 1.", "Sentence 2.", "Sentence 3."]
    assert [b.text for b in plan.blocks] == ["Sentence 1.Sentence 2.", "Sentence 3."]
    assert plan.blocks[0].source_frame_indices == [0, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_timing_planner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.services.timing_planner'`

- [ ] **Step 3: Write the planner**

```python
# pixelle_video/services/timing_planner.py
from dataclasses import dataclass
from typing import List

from pixelle_video.models.render_package import AudioBlock, SentenceUnit


@dataclass
class TimingPlan:
    sentences: List[SentenceUnit]
    blocks: List[AudioBlock]


class TimingPlanner:
    def __init__(self, mode: str, max_sentences: int, max_chars: int):
        self.mode = mode
        self.max_sentences = max_sentences
        self.max_chars = max_chars

    def build(self, frames) -> TimingPlan:
        sentences: List[SentenceUnit] = []
        for frame in frames:
            sentences.append(
                SentenceUnit(
                    id=f"sentence-{frame.index}",
                    text=frame.narration,
                    frame_indices=[frame.index],
                    block_id="",
                    source_start=0.0,
                    source_end=0.0,
                )
            )

        blocks: List[AudioBlock] = []
        cursor: List[SentenceUnit] = []
        for sentence in sentences:
            projected = "".join(item.text for item in cursor + [sentence])
            if cursor and (len(cursor) >= self.max_sentences or len(projected) > self.max_chars):
                blocks.append(self._make_block(len(blocks), cursor))
                cursor = []
            cursor.append(sentence)
        if cursor:
            blocks.append(self._make_block(len(blocks), cursor))

        for block in blocks:
            for sentence in sentences:
                if sentence.frame_indices[0] in block.source_frame_indices:
                    sentence.block_id = block.id

        return TimingPlan(sentences=sentences, blocks=blocks)

    def _make_block(self, index: int, sentences: List[SentenceUnit]) -> AudioBlock:
        return AudioBlock(
            id=f"block-{index}",
            text="".join(item.text for item in sentences),
            audio_path="",
            start=0.0,
            end=0.0,
            source_frame_indices=[item.frame_indices[0] for item in sentences],
        )
```

- [ ] **Step 4: Integrate planning into the pipeline without changing media generation**

```python
# pixelle_video/pipelines/standard.py
from pixelle_video.services.timing_planner import TimingPlanner


planner = TimingPlanner(
    mode=config.tts_batching_mode,
    max_sentences=config.tts_batch_max_sentences,
    max_chars=config.tts_batch_max_chars,
)
ctx.timing_plan = planner.build(ctx.storyboard.frames)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_timing_planner.py tests/test_standard_pipeline_staged_mode.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pixelle_video/services/timing_planner.py pixelle_video/pipelines/standard.py tests/test_timing_planner.py
git commit -m "feat: add narration timing planner"
```

### Task 3: Integrate Qwen forced alignment and sentence cue aggregation

**Files:**
- Create: `pixelle_video/services/alignment_service.py`
- Modify: `pyproject.toml`
- Test: `tests/test_alignment_service.py`

- [ ] **Step 1: Write the failing alignment aggregation test**

```python
from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.services.alignment_service import AlignmentService


class FakeAligner:
    def align(self, audio, text, language="zh"):
        return {
            "words": [
                {"text": "Sentence 1", "start": 0.10, "end": 1.80},
                {"text": "Sentence 2", "start": 2.20, "end": 3.70},
            ]
        }


def test_alignment_service_maps_known_text_back_to_sentence_spans():
    service = AlignmentService(client=FakeAligner())
    block = AudioBlock(id="block-0", text="Sentence 1. Sentence 2.", audio_path="block.wav", start=0.0, end=4.0, source_frame_indices=[0, 1])
    sentences = [
        SentenceUnit(id="s1", text="Sentence 1.", frame_indices=[0], block_id="block-0", source_start=0.0, source_end=0.0),
        SentenceUnit(id="s2", text="Sentence 2.", frame_indices=[1], block_id="block-0", source_start=0.0, source_end=0.0),
    ]

    aligned = service.align_block(block, sentences)
    assert aligned[0].source_start == 0.10
    assert aligned[0].source_end == 1.80
    assert aligned[1].source_start == 2.20
    assert aligned[1].source_end == 3.70
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_alignment_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.services.alignment_service'`

- [ ] **Step 3: Write the alignment wrapper**

```python
# pyproject.toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.6.0",
]
render = [
    "qwen-asr>=0.3.0",
]
```

```python
# pixelle_video/services/alignment_service.py
from typing import Iterable, List, Optional

from pixelle_video.services.frame_processor import _strip_trailing_subtitle_punctuation


class AlignmentService:
    def __init__(self, client=None):
        self._client = client

    def _get_client(self):
        if self._client is None:
            from qwen_asr import Qwen3ForcedAligner

            self._client = Qwen3ForcedAligner.from_pretrained(
                "models/Qwen3-ForcedAligner-0.6B",
                device_map="cuda:0",
            )
        return self._client

    def align_block(self, block, sentences: Iterable):
        result = self._get_client().align(audio=block.audio_path, text=block.text, language="zh")
        words = result["words"]
        aligned: List = []
        for sentence in sentences:
            bare = _strip_trailing_subtitle_punctuation(sentence.text)
            sentence_words = [word for word in words if word["text"].replace(" ", "") in bare.replace(" ", "")]
            sentence.source_start = sentence_words[0]["start"]
            sentence.source_end = sentence_words[-1]["end"]
            aligned.append(sentence)
        return aligned

    def align_blocks(self, blocks, sentences):
        grouped = []
        for block in blocks:
            block_sentences = [sentence for sentence in sentences if sentence.block_id == block.id]
            grouped.extend(self.align_block(block, block_sentences))
        return grouped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_alignment_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml pixelle_video/services/alignment_service.py tests/test_alignment_service.py
git commit -m "feat: add qwen forced alignment service"
```

### Follow-up Strategy Note: Add explicit transcription fallback without changing the primary path

This plan intentionally makes `Qwen3-ForcedAligner-0.6B` the default sentence-timing engine for normal Pixelle-generated tasks. If a later implementation phase adds `funasr_transcribe`, it must obey all of the following rules:

- only activate when Pixelle narration text is absent or explicitly marked unusable
- produce text plus timing as a compatibility path, not as the main contract
- allow `FunClip` to emit `SRT` only as an interoperability artifact
- keep `ASS` generation, if needed, on the Pixelle export side
- never silently downgrade a `text + audio` task from forced alignment to transcription

### Task 4: Add optional auto-editor silence trimming and time remapping

**Files:**
- Create: `pixelle_video/services/audio_edit_service.py`
- Test: `tests/test_audio_edit_service.py`

- [ ] **Step 1: Write the failing time-remap test**

```python
from pixelle_video.models.render_package import SentenceUnit
from pixelle_video.services.audio_edit_service import AutoEditorTimeline


def test_auto_editor_v1_chunks_remap_sentence_boundaries():
    timeline = AutoEditorTimeline(chunks=[[0, 30, 1.0], [30, 40, 0.0], [40, 80, 1.0]], timebase=10.0)
    sentence = SentenceUnit(id="s1", text="Example", frame_indices=[0], block_id="block-0", source_start=2.0, source_end=6.0)

    remapped = timeline.remap_sentence(sentence)
    assert remapped.remapped_start == 2.0
    assert remapped.remapped_end == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audio_edit_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.services.audio_edit_service'`

- [ ] **Step 3: Write the auto-editor wrapper**

```python
# pixelle_video/services/audio_edit_service.py
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AutoEditorTimeline:
    chunks: list[list[float]]
    timebase: float

    def remap_time(self, value: float) -> float:
        current = 0.0
        for start, end, speed in self.chunks:
            src_start = start / self.timebase
            src_end = end / self.timebase
            if speed == 0.0:
                if value <= src_end:
                    return current
                continue
            span = src_end - src_start
            if value <= src_end:
                return current + max(0.0, value - src_start) / speed
            current += span / speed
        return current

    def remap_sentence(self, sentence):
        sentence.remapped_start = self.remap_time(sentence.source_start)
        sentence.remapped_end = self.remap_time(sentence.source_end)
        return sentence


class AudioEditService:
    def export_timeline(self, audio_path: str, output_json: str) -> AutoEditorTimeline:
        subprocess.run(
            ["auto-editor", audio_path, "--export", "timeline:api=1", "-o", output_json],
            check=True,
        )
        data = json.loads(Path(output_json).read_text(encoding="utf-8"))
        return AutoEditorTimeline(chunks=data["chunks"], timebase=30.0)

    def remap_sentences(self, audio_path: str, sentences):
        timeline_path = str(Path(audio_path).with_suffix(".timeline.json"))
        timeline = self.export_timeline(audio_path, timeline_path)
        return [timeline.remap_sentence(sentence) for sentence in sentences]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_audio_edit_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/audio_edit_service.py tests/test_audio_edit_service.py
git commit -m "feat: add auto-editor timeline remapping"
```

### Task 5: Export HyperFrames project data and remove burned-in body subtitles from shell renders

**Files:**
- Create: `pixelle_video/services/hyperframes_project_service.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Test: `tests/test_hyperframes_project_service.py`

- [ ] **Step 1: Write the failing export test**

```python
from pathlib import Path

from pixelle_video.models.render_package import CaptionCue, RenderManifest, VisualClip
from pixelle_video.services.hyperframes_project_service import HyperFramesProjectService


def test_hyperframes_project_service_writes_manifest_and_caption_data(tmp_path: Path):
    service = HyperFramesProjectService(template_root=tmp_path / "templates")
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        master_audio_path="master.wav",
        audio_blocks=[],
        sentence_units=[],
        visual_clips=[VisualClip(id="v1", frame_index=0, start=0.0, end=2.0, media_path="01_image.png", media_type="image", track_index=0)],
        caption_cues=[CaptionCue(id="c1", text="Sentence 1", start=0.0, end=2.0, frame_indices=[0], style_profile="image_life_insights_light")],
    )

    project_dir = service.write_project(tmp_path / "task-1", manifest)
    assert (project_dir / "data" / "render-manifest.json").exists()
    assert (project_dir / "data" / "captions.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hyperframes_project_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.services.hyperframes_project_service'`

- [ ] **Step 3: Write the exporter and shell-only frame path**

```python
# pixelle_video/services/frame_processor.py
async def _compose_frame_html(self, frame, storyboard, task_dir=None, body_text_override=None):
    rendered_text = body_text_override if body_text_override is not None else _strip_trailing_subtitle_punctuation(frame.narration)
    return await self.frame_html(
        template=storyboard.config.frame_template,
        title=storyboard.title,
        text=rendered_text,
        image=frame.image_path,
        output_path=str(task_dir / f"{frame.index + 1:02d}_composed.png"),
    )
```

```python
# pixelle_video/services/hyperframes_project_service.py
import json
from pathlib import Path

from pixelle_video.models.render_package import CaptionCue, RenderManifest, VisualClip
from pixelle_video.services.frame_processor import _strip_trailing_subtitle_punctuation


class HyperFramesProjectService:
    def __init__(self, template_root: Path):
        self.template_root = Path(template_root)

    def build_manifest(self, storyboard, timing_plan, sentences, master_audio_path: str):
        visual_clips = [
            VisualClip(
                id=f"visual-{frame.index}",
                frame_index=frame.index,
                start=sentence.remapped_start or sentence.source_start,
                end=sentence.remapped_end or sentence.source_end,
                media_path=frame.image_path or frame.video_path,
                media_type=frame.media_type or "image",
                track_index=0,
            )
            for frame, sentence in zip(storyboard.frames, sentences)
        ]
        caption_cues = [
            CaptionCue(
                id=f"caption-{sentence.id}",
                text=_strip_trailing_subtitle_punctuation(sentence.text),
                start=sentence.remapped_start or sentence.source_start,
                end=sentence.remapped_end or sentence.source_end,
                frame_indices=sentence.frame_indices,
                style_profile="image_life_insights_light",
            )
            for sentence in sentences
        ]
        return RenderManifest(
            task_id=storyboard.config.task_id,
            title=storyboard.title,
            width=storyboard.config.media_width,
            height=storyboard.config.media_height,
            fps=storyboard.config.video_fps,
            template_id="image_life_insights_light",
            master_audio_path=master_audio_path,
            audio_blocks=timing_plan.blocks,
            sentence_units=sentences,
            visual_clips=visual_clips,
            caption_cues=caption_cues,
        )

    def write_project(self, task_dir: Path, manifest):
        project_dir = Path(task_dir) / "hyperframes"
        data_dir = project_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "render-manifest.json").write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (data_dir / "captions.json").write_text(json.dumps([cue.__dict__ for cue in manifest.caption_cues], ensure_ascii=False, indent=2), encoding="utf-8")
        return project_dir
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_project_service.py tests/test_frame_processor_negative_prompt.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/hyperframes_project_service.py pixelle_video/services/frame_processor.py tests/test_hyperframes_project_service.py
git commit -m "feat: export hyperframes project data"
```

### Task 6: Add the Node render bridge and migrate the reference template

**Files:**
- Create: `pixelle_video/services/hyperframes_renderer.py`
- Modify: `pixelle_video/service.py`
- Test: `tests/test_hyperframes_renderer.py`
- Create: `tools/hyperframes_bridge/package.json`
- Create: `tools/hyperframes_bridge/src/render.mjs`
- Create: `tools/hyperframes_bridge/tests/render.test.mjs`
- Create: `resources/hyperframes/templates/image_life_insights_light/index.html`
- Create: `resources/hyperframes/templates/image_life_insights_light/compositions/captions.html`

- [ ] **Step 1: Write the failing Node and Python bridge tests**

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { resolveRenderConfig } from "../src/render.mjs";

test("resolveRenderConfig reads Pixelle manifest paths", () => {
  const config = resolveRenderConfig({
    projectDir: "output/task-1/hyperframes",
    outputPath: "output/task-1/final.mp4",
    width: 1080,
    height: 1920,
    fps: 30,
  });

  assert.equal(config.inputPath.endsWith("index.html"), true);
  assert.equal(config.outputPath.endsWith("final.mp4"), true);
});
```

```python
from unittest.mock import patch

import pytest

from pixelle_video.services.hyperframes_renderer import HyperFramesRenderer


@pytest.mark.asyncio
async def test_hyperframes_renderer_invokes_node_bridge():
    renderer = HyperFramesRenderer(entrypoint="tools/hyperframes_bridge/src/render.mjs")
    with patch("subprocess.run") as run_mock:
        result = await renderer.render(
            project_dir="output/task-1/hyperframes",
            output_path="output/task-1/final.mp4",
            width=1080,
            height=1920,
            fps=30,
        )

    run_mock.assert_called_once()
    assert result.endswith("final.mp4")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tools/hyperframes_bridge/tests/render.test.mjs`
Expected: FAIL with `Cannot find module '../src/render.mjs'`

Run: `uv run pytest tests/test_hyperframes_renderer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.services.hyperframes_renderer'`

- [ ] **Step 3: Write the bridge and template shell**

```json
{
  "name": "pixelle-hyperframes-bridge",
  "private": true,
  "type": "module",
  "dependencies": {
    "@hyperframes/producer": "^0.4.11"
  },
  "scripts": {
    "test": "node --test"
  }
}
```

```javascript
// tools/hyperframes_bridge/src/render.mjs
import { createRenderJob, executeRenderJob } from "@hyperframes/producer";
import path from "node:path";

export function resolveRenderConfig({ projectDir, outputPath, width, height, fps }) {
  return {
    inputPath: path.join(projectDir, "index.html"),
    outputPath,
    width,
    height,
    fps,
    quality: "standard",
  };
}

export async function renderProject(options) {
  const config = resolveRenderConfig(options);
  const job = createRenderJob(config);
  return executeRenderJob(job);
}

if (process.argv[1] && new URL(import.meta.url).pathname.endsWith("render.mjs") && process.argv[2]) {
  const payload = JSON.parse(process.argv[2]);
  await renderProject(payload);
}
```

```python
# pixelle_video/services/hyperframes_renderer.py
import json
import subprocess


class HyperFramesRenderer:
    def __init__(self, entrypoint: str = "tools/hyperframes_bridge/src/render.mjs"):
        self.entrypoint = entrypoint

    async def render(self, *, project_dir: str, output_path: str, width: int, height: int, fps: int) -> str:
        payload = json.dumps(
            {
                "projectDir": project_dir,
                "outputPath": output_path,
                "width": width,
                "height": height,
                "fps": fps,
            },
            ensure_ascii=False,
        )
        subprocess.run(["node", self.entrypoint, payload], check=True)
        return output_path
```

```python
# pixelle_video/service.py
from pixelle_video.services.hyperframes_renderer import HyperFramesRenderer
from pixelle_video.services.alignment_service import AlignmentService
from pixelle_video.services.audio_edit_service import AudioEditService
from pixelle_video.services.hyperframes_project_service import HyperFramesProjectService

# inside PixelleVideoCore.initialize()
self.alignment = AlignmentService()
self.audio_edit = AudioEditService()
self.hyperframes_project = HyperFramesProjectService(template_root="resources/hyperframes/templates")
self.hyperframes_renderer = HyperFramesRenderer()
```

```html
<!-- resources/hyperframes/templates/image_life_insights_light/index.html -->
<div id="root" data-duration="{{duration}}">
  <div data-track-index="0" id="visual-track"></div>
  <iframe src="./compositions/captions.html" data-timeline-role="captions" data-caption-root="true"></iframe>
  <audio src="./data/master-audio.wav" data-start="0" data-duration="{{duration}}"></audio>
</div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_renderer.py -v`
Expected: PASS

Run: `cd tools/hyperframes_bridge; npm install; npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/hyperframes_renderer.py pixelle_video/service.py tests/test_hyperframes_renderer.py tools/hyperframes_bridge resources/hyperframes/templates/image_life_insights_light
git commit -m "feat: add hyperframes render bridge"
```

### Task 7: Switch the standard pipeline to the HyperFrames render path and document the new dependencies

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Create: `tests/test_standard_pipeline_hyperframes_mode.py`
- Create: `workflows/down/hyperframes_render_依赖与下载说明.md`

- [ ] **Step 1: Write the failing pipeline integration test**

```python
from types import SimpleNamespace

import pytest

from pixelle_video.pipelines.standard import StandardPipeline


@pytest.mark.asyncio
async def test_standard_pipeline_uses_hyperframes_renderer_when_enabled(monkeypatch):
    pipeline = StandardPipeline(SimpleNamespace())
    ctx = SimpleNamespace(storyboard=SimpleNamespace(frames=[], config=SimpleNamespace(render_backend="hyperframes")))

    called = {"render": False}

    async def fake_render(_ctx):
        called["render"] = True

    monkeypatch.setattr(pipeline, "_render_with_hyperframes", fake_render)
    await pipeline.post_production(ctx)
    assert called["render"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_standard_pipeline_hyperframes_mode.py -v`
Expected: FAIL because `_render_with_hyperframes` does not exist

- [ ] **Step 3: Write the pipeline orchestration and dependency doc**

```python
# pixelle_video/pipelines/standard.py
from pathlib import Path

import ffmpeg

async def produce_assets(self, ctx: PipelineContext):
    if ctx.storyboard.config.render_backend == "hyperframes":
        await self._produce_hyperframes_assets(ctx)
        return
    return await super().produce_assets(ctx)


async def _produce_hyperframes_assets(self, ctx: PipelineContext):
    for frame in ctx.storyboard.frames:
        if frame.image_prompt is not None:
            await self.core.frame_processor._step_generate_media(frame, ctx.config)
        await self.core.frame_processor._step_compose_frame(
            frame,
            ctx.storyboard,
            ctx.config,
            body_text_override="",
        )


async def _synthesize_audio_blocks(self, ctx: PipelineContext):
    audio_paths = []
    for block in ctx.timing_plan.blocks:
        block.audio_path = await self.tts(
            text=block.text,
            workflow=ctx.storyboard.config.tts_workflow,
            inference_mode=ctx.storyboard.config.tts_inference_mode,
        )
        audio_paths.append(block.audio_path)
    filelist = self.core.persistence.get_task_dir(ctx.storyboard.config.task_id) / "master_audio.txt"
    filelist.write_text("".join(f"file '{Path(path).resolve()}'\n" for path in audio_paths), encoding="utf-8")
    ctx.master_audio_path = str(self.core.persistence.get_task_dir(ctx.storyboard.config.task_id) / "master_audio.wav")
    (
        ffmpeg
        .input(str(filelist), format="concat", safe=0)
        .output(ctx.master_audio_path, acodec="pcm_s16le", ar=24000)
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )


async def _render_with_hyperframes(self, ctx: PipelineContext):
    await self._synthesize_audio_blocks(ctx)
    timing_plan = ctx.timing_plan
    aligned_sentences = self.core.alignment.align_blocks(timing_plan.blocks, timing_plan.sentences)
    if ctx.storyboard.config.silence_trim_tool == "auto_editor":
        aligned_sentences = self.core.audio_edit.remap_sentences(ctx.master_audio_path, aligned_sentences)
    manifest = self.core.hyperframes_project.build_manifest(ctx.storyboard, timing_plan, aligned_sentences, ctx.master_audio_path)
    project_dir = self.core.hyperframes_project.write_project(self.core.persistence.get_task_dir(ctx.storyboard.config.task_id), manifest)
    final_video_path = await self.core.hyperframes_renderer.render(project_dir=project_dir, output_path=str(self.core.persistence.get_task_dir(ctx.storyboard.config.task_id) / "final.mp4"), width=manifest.width, height=manifest.height, fps=manifest.fps)
    ctx.storyboard.final_video_path = final_video_path


async def post_production(self, ctx: PipelineContext):
    if ctx.storyboard.config.render_backend == "hyperframes":
        await self._render_with_hyperframes(ctx)
        return
    return await super().post_production(ctx)
```

```python
# pixelle_video/services/frame_processor.py
async def _step_compose_frame(self, frame, storyboard, config, *, body_text_override: Optional[str] = None):
    task_dir = self._get_task_dir(frame, storyboard)
    task_dir.mkdir(parents=True, exist_ok=True)
    frame.composed_image_path = await self._compose_frame_html(
        frame,
        storyboard,
        task_dir=task_dir,
        body_text_override=body_text_override,
    )
```

```markdown
# workflows/down/hyperframes_render_依赖与下载说明.md
- ModelScope 优先下载：`modelscope download --model Qwen/Qwen3-ForcedAligner-0.6B --local_dir models/Qwen3-ForcedAligner-0.6B`
- Python 依赖：`uv pip install qwen-asr`
- Node 依赖：`cd tools/hyperframes_bridge && npm install`
- 静音修剪：`uv tool install auto-editor`
- 验证命令：
  - `python -c "from qwen_asr import Qwen3ForcedAligner; print('ok')"`
  - `auto-editor --help`
  - `node tools/hyperframes_bridge/src/render.mjs --help`
```

- [ ] **Step 4: Run the full verification set**

Run: `uv run pytest tests/test_render_package_models.py tests/test_timing_planner.py tests/test_alignment_service.py tests/test_audio_edit_service.py tests/test_hyperframes_project_service.py tests/test_standard_pipeline_hyperframes_mode.py -v`
Expected: PASS

Run: `cd tools/hyperframes_bridge; npm test`
Expected: PASS

Run:

```powershell
@'
import asyncio
from pixelle_video import pixelle_video

async def main():
    await pixelle_video.initialize()
    try:
        result = await pixelle_video.generate_video(
            text="Sentence 1. Sentence 2. Sentence 3.",
            pipeline="standard",
            n_storyboard=3,
            tts_inference_mode="comfyui",
            tts_workflow="selfhost/tts_index2.json",
            media_workflow="selfhost/image_z_image_turbo.json",
            frame_template="1080x1920/image_life_insights_light.html",
        )
        print(result.video_path)
    finally:
        await pixelle_video.cleanup()

asyncio.run(main())
'@ | uv run python -
```

Expected: prints a task-local `final.mp4` path rendered through the HyperFrames backend

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/pipelines/standard.py pixelle_video/services/frame_processor.py tests/test_standard_pipeline_hyperframes_mode.py workflows/down/hyperframes_render_依赖与下载说明.md
git commit -m "feat: render standard pipeline with hyperframes"
```
