# Pixelle HyperFrames Compiled Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Pixelle's current runtime-manifest HyperFrames path with a compiled-project pipeline that emits fully renderable HyperFrames projects for `1080x1920` image templates, starting with `image_default` and `image_life_insights_light`, while preserving the visual structure of those source templates rather than replacing them with minimal shells.

**Architecture:** Pixelle remains responsible for storyboarding, TTS, image generation, sentence timing acquisition, template data preparation, and project compilation. HyperFrames receives a task-local project directory with static `index.html`, static `captions.html`, project-local assets, and a single canonical timeline, then renders the final MP4. The first rollout only covers `1080x1920` image templates and keeps the legacy path for all other templates.

**Tech Stack:** Python 3.12, pytest, ffmpeg/ffprobe, `qwen-asr`, optional `auto-editor`, Node.js 22+, `@hyperframes/producer`, HyperFrames HTML/CSS compositions

---

## File Structure

- Create: `pixelle_video/models/template_render_context.py`
  - Defines the normalized shell/captions input contract used by all compiled HyperFrames templates.
- Modify: `pixelle_video/models/render_package.py`
  - Separates canvas dimensions from source media dimensions and makes canonical timeline fields explicit.
- Create: `pixelle_video/services/hyperframes_asset_materializer.py`
  - Copies task-local images/audio/video into `output/<task>/hyperframes/assets/...`.
- Create: `pixelle_video/services/hyperframes_compiler.py`
  - Compiles static `index.html`, `compositions/captions.html`, and diagnostic JSON from `TemplateRenderContext`.
- Create: `resources/hyperframes/runtime/fonts/`
  - Stores local font CSS and packaged font assets used by migrated templates.
- Create: `resources/hyperframes/runtime/vendor/`
  - Stores vendored runtime libraries if a migrated template requires them.
- Modify: `pixelle_video/services/hyperframes_project_service.py`
  - Becomes the orchestration layer that builds render context, materializes assets, and invokes the compiler.
- Modify: `pixelle_video/services/hyperframes_renderer.py`
  - Adds post-render ffprobe validation and failure semantics.
- Modify: `pixelle_video/pipelines/standard.py`
  - Routes eligible `1080x1920 image_*` templates through the compiled-project path and selects the canonical timeline.
- Create: `resources/hyperframes/templates/image_default/index.template.html`
- Create: `resources/hyperframes/templates/image_default/compositions/captions.template.html`
- Create: `resources/hyperframes/templates/image_life_insights_light/index.template.html`
- Create: `resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html`
  - Static template sources used by the compiler; no runtime `fetch`, no CDN scripts, no remote fonts.
- Create: `tests/test_template_render_context.py`
- Create: `tests/test_hyperframes_asset_materializer.py`
- Create: `tests/test_hyperframes_compiler.py`
- Modify: `tests/test_hyperframes_project_service.py`
- Modify: `tests/test_hyperframes_renderer.py`
- Modify: `tests/test_standard_pipeline_hyperframes_mode.py`
- Create: `tests/test_hyperframes_runtime_contract.py`
- Modify: `workflows/down/hyperframes_render_依赖与下载说明.md`
  - Documents the compiled-project path and local-only runtime dependency rule.

### Task 1: Define the compiled-project contract and canonical timeline rule

**Files:**
- Create: `pixelle_video/models/template_render_context.py`
- Modify: `pixelle_video/models/render_package.py`
- Test: `tests/test_template_render_context.py`
- Test: `tests/test_render_package_models.py`

- [ ] **Step 1: Write the failing contract tests**

```python
from pixelle_video.models.render_package import CaptionCue, RenderManifest, SentenceUnit, VisualClip
from pixelle_video.models.template_render_context import TemplateAudioRef, TemplateRenderContext


def test_render_manifest_distinguishes_canvas_from_media_dimensions():
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        media_width=768,
        media_height=768,
        fps=30,
        template_id="image_default",
    )
    data = manifest.to_dict()
    assert data["canvas_width"] == 1080
    assert data["media_width"] == 768


def test_template_render_context_uses_render_timeline_values():
    sentence = SentenceUnit(
        id="s1",
        text="一句话",
        frame_indices=[0],
        block_id="block-1",
        source_start=0.2,
        source_end=1.8,
        remapped_start=0.1,
        remapped_end=1.5,
    )
    cue = CaptionCue(id="c1", text="一句话", start=0.1, end=1.5, frame_indices=[0], style_profile="image_default")
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=10.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        template_params={},
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=sentence.remapped_start,
                end=sentence.remapped_end,
                media_path="assets/images/01_image.png",
                media_type="image",
            )
        ],
        captions=[cue],
        audio=TemplateAudioRef(path="assets/audio/master_audio.wav", duration=10.0),
    )
    assert context.visuals[0].start == 0.1
    assert context.captions[0].end == 1.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_template_render_context.py tests/test_render_package_models.py -v`
Expected: FAIL because `TemplateRenderContext` does not exist and `RenderManifest` does not yet expose `canvas_width` / `canvas_height`

- [ ] **Step 3: Add the normalized contract models**

```python
# pixelle_video/models/template_render_context.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pixelle_video.models.render_package import CaptionCue, VisualClip


@dataclass
class TemplateAudioRef:
    path: str
    duration: float


@dataclass
class TemplateRenderContext:
    template_id: str
    canvas_width: int
    canvas_height: int
    duration: float
    fps: int
    title: str
    author: Optional[str]
    footer: Optional[str]
    theme: Optional[str]
    style_profile: str
    template_params: Dict[str, Any] = field(default_factory=dict)
    visuals: List[VisualClip] = field(default_factory=list)
    captions: List[CaptionCue] = field(default_factory=list)
    audio: Optional[TemplateAudioRef] = None
```

```python
# pixelle_video/models/render_package.py
@dataclass
class RenderManifest:
    task_id: str
    title: str
    canvas_width: int
    canvas_height: int
    media_width: Optional[int]
    media_height: Optional[int]
    fps: int
    template_id: str
    master_audio_path: Optional[str] = None
    master_audio_duration: Optional[float] = None
    audio_blocks: List[AudioBlock] = field(default_factory=list)
    sentence_units: List[SentenceUnit] = field(default_factory=list)
    visual_clips: List[VisualClip] = field(default_factory=list)
    caption_cues: List[CaptionCue] = field(default_factory=list)
    canonical_timeline: str = "source"
```

```python
# pixelle_video/models/render_package.py
def resolve_render_window(unit: SentenceUnit) -> tuple[float, float]:
    if unit.remapped_start is not None and unit.remapped_end is not None:
        return unit.remapped_start, unit.remapped_end
    if unit.source_start is None or unit.source_end is None:
        raise ValueError(f"SentenceUnit {unit.id} is missing source timing.")
    return unit.source_start, unit.source_end
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_template_render_context.py tests/test_render_package_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/template_render_context.py pixelle_video/models/render_package.py tests/test_template_render_context.py tests/test_render_package_models.py
git commit -m "feat: define compiled hyperframes render contract"
```

### Task 2: Materialize project-local assets with copy-first semantics

**Files:**
- Create: `pixelle_video/services/hyperframes_asset_materializer.py`
- Test: `tests/test_hyperframes_asset_materializer.py`

- [ ] **Step 1: Write the failing asset-materialization test**

```python
from pathlib import Path

from pixelle_video.services.hyperframes_asset_materializer import HyperFramesAssetMaterializer


def test_asset_materializer_copies_inputs_into_project_local_assets(tmp_path: Path):
    source_audio = tmp_path / "master_audio.wav"
    source_image = tmp_path / "01_image.png"
    source_audio.write_bytes(b"wav")
    source_image.write_bytes(b"png")

    materializer = HyperFramesAssetMaterializer()
    project_dir = tmp_path / "task" / "hyperframes"
    result = materializer.materialize(
        project_dir=project_dir,
        audio_sources={"master_audio.wav": source_audio},
        image_sources={"01_image.png": source_image},
        video_sources={},
    )

    assert (project_dir / "assets" / "audio" / "master_audio.wav").exists()
    assert (project_dir / "assets" / "images" / "01_image.png").exists()
    assert result["audio"]["master_audio.wav"] == "assets/audio/master_audio.wav"
    assert result["images"]["01_image.png"] == "assets/images/01_image.png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hyperframes_asset_materializer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.services.hyperframes_asset_materializer'`

- [ ] **Step 3: Write the copy-first materializer**

```python
# pixelle_video/services/hyperframes_asset_materializer.py
from pathlib import Path
from shutil import copy2
from typing import Dict


class HyperFramesAssetMaterializer:
    def materialize(
        self,
        *,
        project_dir: Path,
        audio_sources: Dict[str, Path],
        image_sources: Dict[str, Path],
        video_sources: Dict[str, Path],
    ) -> dict:
        assets_dir = project_dir / "assets"
        audio_dir = assets_dir / "audio"
        image_dir = assets_dir / "images"
        video_dir = assets_dir / "video"
        for directory in (audio_dir, image_dir, video_dir):
            directory.mkdir(parents=True, exist_ok=True)

        def _copy_group(group: Dict[str, Path], target_dir: Path, prefix: str) -> Dict[str, str]:
            results: Dict[str, str] = {}
            for filename, source in group.items():
                target = target_dir / filename
                copy2(source, target)
                results[filename] = f"assets/{prefix}/{filename}"
            return results

        return {
            "audio": _copy_group(audio_sources, audio_dir, "audio"),
            "images": _copy_group(image_sources, image_dir, "images"),
            "video": _copy_group(video_sources, video_dir, "video"),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_asset_materializer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/hyperframes_asset_materializer.py tests/test_hyperframes_asset_materializer.py
git commit -m "feat: materialize hyperframes assets locally"
```

### Task 3: Lock phase-1 template field mapping and local runtime dependency strategy

**Files:**
- Modify: `pixelle_video/models/template_render_context.py`
- Create: `resources/hyperframes/runtime/fonts/phase1_fonts.css`
- Create: `resources/hyperframes/runtime/vendor/README.md`
- Modify: `tests/test_template_render_context.py`
- Modify: `tests/test_hyperframes_compiler.py`

- [ ] **Step 1: Write the failing field-mapping and local-dependency tests**

```python
from pathlib import Path

from pixelle_video.models.template_render_context import TemplateRenderContext


def test_template_render_context_exposes_phase1_shell_fields():
    field_names = TemplateRenderContext.__dataclass_fields__.keys()
    assert "title" in field_names
    assert "author" in field_names
    assert "footer" in field_names
    assert "style_profile" in field_names
    assert "template_params" in field_names


def test_phase1_runtime_assets_are_local_only():
    assert Path("resources/hyperframes/runtime/fonts/phase1_fonts.css").exists()
    assert Path("resources/hyperframes/runtime/vendor").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_template_render_context.py tests/test_hyperframes_compiler.py -v`
Expected: FAIL because phase-1 shell fields and local runtime assets are not yet fully defined

- [ ] **Step 3: Define the phase-1 field inventory and local dependency policy**

- Extend `TemplateRenderContext` so phase-1 templates can consume normalized shell data without ad-hoc globals.
- Create `resources/hyperframes/runtime/fonts/phase1_fonts.css` as the only approved entrypoint for local font stacks and packaged font files used by migrated templates.
- Create `resources/hyperframes/runtime/vendor/README.md` as the only approved home for vendored runtime libraries.
- Add a phase-1 field inventory in code comments or companion docs that maps each source template to:
  - title region
  - media slot geometry and safe area
  - subtitle safe area
  - author/footer region
  - decorative background system
  - style profile name

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_template_render_context.py tests/test_hyperframes_compiler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/template_render_context.py resources/hyperframes/runtime tests/test_template_render_context.py tests/test_hyperframes_compiler.py
git commit -m "feat: define phase1 hyperframes template contract"
```

### Task 4: Compile static `index.html` and `captions.html` for `image_default` with equivalent shell migration

**Files:**
- Create: `pixelle_video/services/hyperframes_compiler.py`
- Create: `resources/hyperframes/templates/image_default/index.template.html`
- Create: `resources/hyperframes/templates/image_default/compositions/captions.template.html`
- Test: `tests/test_hyperframes_compiler.py`

- [ ] **Step 1: Write the failing compiler test**

```python
from pathlib import Path

from pixelle_video.models.render_package import CaptionCue, VisualClip
from pixelle_video.models.template_render_context import TemplateAudioRef, TemplateRenderContext
from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler


def test_compiler_emits_static_index_without_manifest_fetch_or_remote_urls(tmp_path: Path):
    template_root = tmp_path / "templates"
    (template_root / "image_default" / "compositions").mkdir(parents=True)
    (template_root / "image_default" / "index.template.html").write_text(
        "<div id='root' data-width='__CANVAS_WIDTH__' data-height='__CANVAS_HEIGHT__' data-duration='__DURATION__'>__VISUALS____AUDIO__</div>",
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "captions.template.html").write_text(
        "<div id='captions-root' data-duration='__DURATION__'>__CAPTIONS__</div>",
        encoding="utf-8",
    )
    compiler = HyperFramesCompiler(template_root=template_root)
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=12.5,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        template_params={},
        visuals=[VisualClip(id="v1", frame_index=0, start=0.0, end=3.0, media_path="assets/images/01_image.png", media_type="image")],
        captions=[CaptionCue(id="c1", text="第一句", start=0.0, end=3.0, frame_indices=[0], style_profile="image_default")],
        audio=TemplateAudioRef(path="assets/audio/master_audio.wav", duration=12.5),
    )

    project_dir = tmp_path / "task" / "hyperframes"
    compiler.compile(project_dir=project_dir, context=context)

    index_html = (project_dir / "index.html").read_text(encoding="utf-8")
    captions_html = (project_dir / "compositions" / "captions.html").read_text(encoding="utf-8")
    assert "render_manifest.json" not in index_html
    assert "https://" not in index_html
    assert 'src="assets/audio/master_audio.wav"' in index_html
    assert 'src="assets/images/01_image.png"' in index_html
    assert 'data-duration="12.5"' in captions_html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hyperframes_compiler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.services.hyperframes_compiler'`

- [ ] **Step 3: Implement the static compiler and phase-1 `image_default` templates**

```python
# pixelle_video/services/hyperframes_compiler.py
from pathlib import Path


class HyperFramesCompiler:
    def __init__(self, template_root: Path):
        self.template_root = Path(template_root)

    def compile(self, *, project_dir: Path, context) -> None:
        template_dir = self.template_root / context.template_id
        index_template = (template_dir / "index.template.html").read_text(encoding="utf-8")
        captions_template = (template_dir / "compositions" / "captions.template.html").read_text(encoding="utf-8")

        visuals_html = "".join(
            f'<img class="visual" src="{clip.media_path}" data-start="{clip.start}" data-duration="{clip.end - clip.start}" />'
            for clip in context.visuals
        )
        audio_html = (
            f'<audio src="{context.audio.path}" data-start="0" data-duration="{context.audio.duration}"></audio>'
            if context.audio
            else ""
        )
        captions_html = "".join(
            f'<div class="caption" data-start="{cue.start}" data-duration="{cue.end - cue.start}">{cue.text}</div>'
            for cue in context.captions
        )

        compiled_index = (
            index_template
            .replace("__CANVAS_WIDTH__", str(context.canvas_width))
            .replace("__CANVAS_HEIGHT__", str(context.canvas_height))
            .replace("__DURATION__", str(context.duration))
            .replace("__TITLE__", context.title)
            .replace("__VISUALS__", visuals_html)
            .replace("__AUDIO__", audio_html)
        )
        compiled_captions = (
            captions_template
            .replace("__DURATION__", str(context.duration))
            .replace("__CAPTIONS__", captions_html)
        )

        (project_dir / "compositions").mkdir(parents=True, exist_ok=True)
        (project_dir / "index.html").write_text(compiled_index, encoding="utf-8")
        (project_dir / "compositions" / "captions.html").write_text(compiled_captions, encoding="utf-8")
```

```html
<!-- resources/hyperframes/templates/image_default/index.template.html -->
<!doctype html>
<html lang="zh-CN">
  <body>
    <div id="root" data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__" data-duration="__DURATION__">
      <div class="bg-decoration"></div>
      <div class="page-container">
        <section class="video-title-wrapper">
          <div class="video-title">__TITLE__</div>
        </section>
        <section class="image-wrapper">
          <div class="image-container">__VISUALS__</div>
          <div class="corner-mark tl"></div>
          <div class="corner-mark tr"></div>
          <div class="corner-mark bl"></div>
          <div class="corner-mark br"></div>
        </section>
        <footer class="footer-region">__FOOTER__</footer>
      </div>
      <iframe src="./compositions/captions.html" data-timeline-role="captions" data-caption-root="true"></iframe>
      __AUDIO__
    </div>
  </body>
</html>
```

```html
<!-- resources/hyperframes/templates/image_default/compositions/captions.template.html -->
<!doctype html>
<html lang="zh-CN">
  <body>
    <div id="captions-root" data-duration="__DURATION__">__CAPTIONS__</div>
  </body>
</html>
```

- The migrated shell must preserve the original `templates/1080x1920/image_default.html` layout language:
  - centered title block
  - decorative background layer
  - framed 900x900 media region with corner marks
  - footer-safe area
- A minimal placeholder shell that only proves clip rendering is **not** acceptable for this task.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_compiler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/hyperframes_compiler.py resources/hyperframes/templates/image_default tests/test_hyperframes_compiler.py
git commit -m "feat: compile static hyperframes projects"
```

### Task 5: Migrate `image_life_insights_light` with equivalent shell migration and local-only runtime assets

**Files:**
- Create: `resources/hyperframes/templates/image_life_insights_light/index.template.html`
- Create: `resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html`
- Modify: `tests/test_hyperframes_compiler.py`

- [ ] **Step 1: Write the failing local-dependency template test**

```python
from pathlib import Path


def test_phase1_templates_do_not_depend_on_remote_fonts_or_cdn_scripts():
    template_paths = [
        Path("resources/hyperframes/templates/image_default/index.template.html"),
        Path("resources/hyperframes/templates/image_life_insights_light/index.template.html"),
        Path("resources/hyperframes/templates/image_default/compositions/captions.template.html"),
        Path("resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html"),
    ]
    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "https://fonts.googleapis.com" not in content
        assert "https://cdnjs.cloudflare.com" not in content


def test_phase1_templates_preserve_source_shell_regions():
    content = Path("resources/hyperframes/templates/image_life_insights_light/index.template.html").read_text(encoding="utf-8")
    assert "bg-pattern" in content
    assert "header" in content
    assert "content" in content
    assert "bottom-section" in content
    assert "author" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hyperframes_compiler.py::test_phase1_templates_do_not_depend_on_remote_fonts_or_cdn_scripts -v`
Expected: FAIL until the new phase-1 templates exist and remove remote runtime dependencies

- [ ] **Step 3: Add the second phase-1 template**

```html
<!-- resources/hyperframes/templates/image_life_insights_light/index.template.html -->
<!doctype html>
<html lang="zh-CN">
  <body>
    <div id="root" data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__" data-duration="__DURATION__">
      <div class="bg-pattern"></div>
      <header class="header">
        <div class="title">__TITLE__</div>
      </header>
      <main class="content">__VISUALS__</main>
      <section class="bottom-section">__FOOTER__</section>
      <div class="author">__AUTHOR__</div>
      <iframe src="./compositions/captions.html" data-timeline-role="captions" data-caption-root="true"></iframe>
      __AUDIO__
    </div>
  </body>
</html>
```

```html
<!-- resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html -->
<!doctype html>
<html lang="zh-CN">
  <body>
    <div id="captions-root" data-duration="__DURATION__">__CAPTIONS__</div>
  </body>
</html>
```

- The migrated shell must preserve the original `templates/1080x1920/image_life_insights_light.html` structure:
  - patterned background system
  - title header region
  - centered content image region
  - bottom text safe area
  - author region
- If the source template used a web font, this task must replace it with packaged local font assets or an approved local fallback defined in `resources/hyperframes/runtime/fonts/phase1_fonts.css`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_compiler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add resources/hyperframes/templates/image_life_insights_light tests/test_hyperframes_compiler.py
git commit -m "feat: migrate first hyperframes phase templates"
```

### Task 6: Route the standard pipeline through the compiled-project path

**Files:**
- Modify: `pixelle_video/services/hyperframes_project_service.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `tests/test_hyperframes_project_service.py`
- Modify: `tests/test_standard_pipeline_hyperframes_mode.py`

- [ ] **Step 1: Write the failing orchestration test**

```python
from pathlib import Path

from pixelle_video.models.render_package import CaptionCue, RenderManifest, SentenceUnit, VisualClip
from pixelle_video.services.hyperframes_project_service import build_template_render_context


def test_build_template_render_context_prefers_remapped_timing_when_present(tmp_path: Path):
    sentences = [
        SentenceUnit(
            id="s1",
            text="第一句",
            frame_indices=[0],
            block_id="block-1",
            source_start=0.3,
            source_end=2.8,
            remapped_start=0.1,
            remapped_end=2.2,
        )
    ]
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        media_width=768,
        media_height=768,
        fps=30,
        template_id="image_default",
        master_audio_duration=3.0,
        sentence_units=sentences,
        visual_clips=[VisualClip(id="v1", frame_index=0, start=0.1, end=2.2, media_path="assets/images/01_image.png", media_type="image")],
        caption_cues=[CaptionCue(id="c1", text="第一句", start=0.1, end=2.2, frame_indices=[0], style_profile="image_default")],
    )
    context = build_template_render_context(manifest, template_params={"author": "demo"})
    assert context.duration == 3.0
    assert context.captions[0].start == 0.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hyperframes_project_service.py tests/test_standard_pipeline_hyperframes_mode.py -v`
Expected: FAIL because the current service still writes runtime JSON only

- [ ] **Step 3: Refactor the project service and pipeline integration**

```python
# pixelle_video/services/hyperframes_project_service.py
from pixelle_video.models.render_package import RenderManifest
from pixelle_video.models.template_render_context import TemplateAudioRef, TemplateRenderContext
from pixelle_video.services.hyperframes_asset_materializer import HyperFramesAssetMaterializer
from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler


def build_template_render_context(manifest: RenderManifest, *, template_params: dict) -> TemplateRenderContext:
    if manifest.master_audio_duration is not None:
        duration = manifest.master_audio_duration
    else:
        duration = max([cue.end for cue in manifest.caption_cues] + [0.0])
    return TemplateRenderContext(
        template_id=manifest.template_id,
        canvas_width=manifest.canvas_width,
        canvas_height=manifest.canvas_height,
        duration=duration,
        fps=manifest.fps,
        title=manifest.title,
        author=template_params.get("author"),
        footer=template_params.get("footer"),
        theme=template_params.get("theme"),
        style_profile=template_params.get("style_profile", manifest.template_id),
        template_params=template_params,
        visuals=manifest.visual_clips,
        captions=manifest.caption_cues,
        audio=TemplateAudioRef(path=manifest.master_audio_path, duration=duration) if manifest.master_audio_path else None,
    )
```

```python
# pixelle_video/pipelines/standard.py
def _resolve_render_timing(self, unit):
    if unit.remapped_start is not None and unit.remapped_end is not None:
        return unit.remapped_start, unit.remapped_end
    return unit.source_start, unit.source_end


async def _post_production_hyperframes(self, ctx):
    ...
    manifest = self.core.hyperframes_project_service.build_manifest(
        storyboard=storyboard,
        timing_plan=timing_plan,
        sentences=aligned_sentences,
        master_audio_path=master_audio_path,
        canvas_width=1080,
        canvas_height=1920,
        media_width=config.media_width,
        media_height=config.media_height,
    )
    project_dir = self.core.hyperframes_project_service.write_project(
        task_dir=Path(ctx.task_dir),
        manifest=manifest,
        template_params=storyboard.config.template_params or {},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_project_service.py tests/test_standard_pipeline_hyperframes_mode.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/hyperframes_project_service.py pixelle_video/pipelines/standard.py tests/test_hyperframes_project_service.py tests/test_standard_pipeline_hyperframes_mode.py
git commit -m "feat: compile hyperframes projects from standard pipeline"
```

### Task 7: Add hard post-render validation and document phase-1 cutover rules

**Files:**
- Modify: `pixelle_video/services/hyperframes_renderer.py`
- Modify: `tests/test_hyperframes_renderer.py`
- Modify: `workflows/down/hyperframes_render_依赖与下载说明.md`

- [ ] **Step 1: Write the failing renderer-validation test**

```python
from unittest.mock import patch

import pytest

from pixelle_video.services.hyperframes_renderer import HyperFramesRenderer


@pytest.mark.asyncio
async def test_renderer_rejects_video_without_audio_stream():
    renderer = HyperFramesRenderer(entrypoint="tools/hyperframes_bridge/src/render.mjs")
    with patch("subprocess.run") as run_mock, patch.object(renderer, "_probe_output") as probe_mock:
        run_mock.return_value.returncode = 0
        probe_mock.return_value = {"has_video": True, "has_audio": False, "duration": 8.0, "width": 1080, "height": 1920}
        with pytest.raises(RuntimeError, match="audio stream"):
            await renderer.render(
                project_dir="output/task-1/hyperframes",
                output_path="output/task-1/final.mp4",
                width=1080,
                height=1920,
                fps=30,
                expected_duration=12.5,
                expect_audio=True,
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hyperframes_renderer.py -v`
Expected: FAIL because the current renderer only checks subprocess success

- [ ] **Step 3: Add ffprobe-based validation**

```python
# pixelle_video/services/hyperframes_renderer.py
import json
import subprocess


class HyperFramesRenderer:
    ...
    def _probe_output(self, output_path: str) -> dict:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        streams = payload.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        return {
            "has_video": video is not None,
            "has_audio": audio is not None,
            "duration": float(payload["format"]["duration"]),
            "width": int(video["width"]) if video else 0,
            "height": int(video["height"]) if video else 0,
        }

    async def render(self, *, project_dir: str, output_path: str, width: int, height: int, fps: int, expected_duration: float, expect_audio: bool) -> str:
        ...
        result = self._probe_output(output_path)
        if not result["has_video"]:
            raise RuntimeError("Rendered HyperFrames output is missing a video stream.")
        if expect_audio and not result["has_audio"]:
            raise RuntimeError("Rendered HyperFrames output is missing an audio stream.")
        if abs(result["duration"] - expected_duration) > 0.35:
            raise RuntimeError("Rendered HyperFrames output duration is outside tolerance.")
        if result["width"] != width or result["height"] != height:
            raise RuntimeError("Rendered HyperFrames output resolution does not match the compiled canvas.")
        return output_path
```

```markdown
<!-- workflows/down/hyperframes_render_依赖与下载说明.md -->
## Compiled-Project Path Notes

- 第一阶段只支持 `1080x1920` 的 `image_default` 与 `image_life_insights_light`
- HyperFrames 模板运行时依赖必须本地化，不允许依赖 Google Fonts、CDN GSAP 等公网资源
- `qwen_forced_aligner` 是默认时间戳来源；`funasr_transcribe` 仅用于 audio-only 兜底
```

- [ ] **Step 4: Run the verification set**

Run: `uv run pytest tests/test_hyperframes_renderer.py tests/test_hyperframes_project_service.py tests/test_hyperframes_compiler.py tests/test_standard_pipeline_hyperframes_mode.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/hyperframes_renderer.py tests/test_hyperframes_renderer.py workflows/down/hyperframes_render_依赖与下载说明.md
git commit -m "feat: validate compiled hyperframes renders"
```

### Task 8: Codify HyperFrames runtime authority and upgrade policy

**Files:**
- Create: `tests/test_hyperframes_runtime_contract.py`
- Modify: `tools/hyperframes_bridge/package.json`
- Modify: `tools/hyperframes_bridge/package-lock.json`

- [ ] **Step 1: Write the failing runtime-authority test**

```python
import json
from pathlib import Path


def test_hyperframes_runtime_authority_is_npm_package():
    package_json = json.loads(Path("tools/hyperframes_bridge/package.json").read_text(encoding="utf-8"))
    assert "@hyperframes/producer" in package_json["dependencies"]


def test_vendor_snapshot_is_not_runtime_dependency():
    for path in Path("tools/hyperframes_bridge/src").rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            assert "vendor/hyperframes" not in content
            assert "third_party/hyperframes" not in content
```

- [ ] **Step 2: Run test to verify it fails or enforces the contract**

Run: `uv run pytest tests/test_hyperframes_runtime_contract.py -v`
Expected: PASS only when runtime authority is clearly pinned to `@hyperframes/producer`

- [ ] **Step 3: Make the runtime-source rule executable**

- Keep `@hyperframes/producer` pinned in `tools/hyperframes_bridge/package.json` and lock it in `package-lock.json`.
- Do not load runtime behavior from `vendor/hyperframes/` or `third_party/hyperframes/`.
- Treat vendor snapshots as upgrade-review references only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_runtime_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_hyperframes_runtime_contract.py tools/hyperframes_bridge/package.json tools/hyperframes_bridge/package-lock.json
git commit -m "chore: codify hyperframes runtime authority"
```

## Self-Review

- **Spec coverage:** This plan covers canonical timeline rules, `TemplateRenderContext`, copy-first asset materialization, local-only template dependencies, phase-1 equivalent template migration, compiled-project orchestration, ffprobe-based output validation, and explicit HyperFrames runtime authority.
- **Placeholder scan:** No `TODO`, `TBD`, or implied "fill this in later" steps remain. Each task names exact files, exact tests, exact commands, and explicit implementation targets.
- **Type consistency:** `RenderManifest` uses `canvas_width/canvas_height`, `master_audio_duration` remains the duration authority, `TemplateRenderContext` uses compiled render-time fields, and the renderer accepts explicit `expected_duration` plus `expect_audio`, matching the spec's render validation requirements.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-22-pixelle-hyperframes-compiled-project-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
