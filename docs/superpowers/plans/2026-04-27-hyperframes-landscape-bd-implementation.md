# HyperFrames Landscape B/D Templates Implementation Plan

> 2026-04-27 amendment: `B`'s final dedicated template id is `image_landscape_full`, not `image_full`. Existing `templates/1920x1080/image_full.html` remains a legacy/UI template and should fall back under `HyperFrames Compiled`. When this document mentions the new horizontal B template, prefer `image_landscape_full` as the source of truth.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two `HyperFrames Compiled` horizontal templates for Pixelle: `image_full` (`B`) and `image_landscape_minimal` (`D`), both matching the approved subtitle and corner-info rules for `1920x1080`.

**Architecture:** Keep the existing `frame_template -> Path(...).stem -> HyperFrames template_id` contract unchanged. Implement the feature as paired assets: one legacy/UI entry template under `templates/1920x1080`, one native compiled template directory under `resources/hyperframes/templates`, plus contract tests that prove there is no fallback and that captions/text layers stay raised and background-free.

**Tech Stack:** Python 3.11+, pytest, existing Pixelle HTML template shells, HyperFrames compiled templates, local runtime fonts/GSAP assets

---

### Task 1: Add landscape contract scaffolding and entry assets

**Files:**
- Modify: `pixelle_video/models/template_render_context.py`
- Create: `templates/1920x1080/image_landscape_minimal.html`
- Create: `resources/hyperframes/templates/image_full/text_capabilities.json`
- Create: `resources/hyperframes/templates/image_landscape_minimal/text_capabilities.json`
- Test: `tests/test_hyperframes_compiler.py`

- [ ] **Step 1: Write the failing contract test**

```python
from pathlib import Path

from pixelle_video.models.template_render_context import PHASE1_TEMPLATE_FIELD_INVENTORY


def test_landscape_template_assets_and_inventory_exist():
    assert Path("templates/1920x1080/image_full.html").exists()
    assert Path("templates/1920x1080/image_landscape_minimal.html").exists()
    assert "image_full" in PHASE1_TEMPLATE_FIELD_INVENTORY
    assert "image_landscape_minimal" in PHASE1_TEMPLATE_FIELD_INVENTORY
    assert Path("resources/hyperframes/templates/image_full/text_capabilities.json").exists()
    assert Path("resources/hyperframes/templates/image_landscape_minimal/text_capabilities.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hyperframes_compiler.py -k landscape_template_assets_and_inventory_exist -v`
Expected: FAIL because `image_landscape_minimal.html`, both `text_capabilities.json` files, and the new inventory entries do not exist yet.

- [ ] **Step 3: Add the inventory entries and entry-template scaffolding**

```python
# pixelle_video/models/template_render_context.py
PHASE1_TEMPLATE_FIELD_INVENTORY.update(
    {
        "image_full": {
            "title_region": "Centered title band across the upper safe area of a 1920x1080 full-bleed image shell.",
            "media_slot": "Single full-bleed landscape visual that occupies the whole frame behind title and subtitle overlays.",
            "subtitle_safe_area": "Raised centered subtitle band above the footer zone with no background panel.",
            "author_footer_region": "Compact lower-left info cluster consuming author, author_desc, and footer away from captions.",
            "decorative_background": "No separate paper shell; readability comes from outline and shadow over the full-bleed visual.",
            "style_profile": "image_full",
        },
        "image_landscape_minimal": {
            "title_region": "Small left-aligned title block in the upper-left safe area of a 1920x1080 white composition.",
            "media_slot": "Centered framed landscape illustration with generous whitespace around it.",
            "subtitle_safe_area": "Raised centered subtitle line below the media frame with no card or panel background.",
            "author_footer_region": "Lightweight lower-right signature cluster consuming author, author_desc, and footer.",
            "decorative_background": "White paper-like background with restrained line and circle accents.",
            "style_profile": "image_landscape_minimal",
        },
    }
)
```

```html
<!-- templates/1920x1080/image_landscape_minimal.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="template:media-width" content="768">
  <meta name="template:media-height" content="768">
  <meta name="viewport" content="width=1920, height=1080">
  <title>横屏极简留白 - 1920x1080</title>
  <style>
    html, body { width: 1920px; height: 1080px; overflow: hidden; }
    body { margin: 0; background: #f8f5ef; color: #171410; font-family: "Noto Serif SC", "Microsoft YaHei", serif; }
  </style>
</head>
<body>
  <div class="header">{{title}}</div>
  <div class="visual"><img src="{{image}}" alt=""></div>
  <div class="subtitle">{{text}}</div>
  <div class="signature">
    <div>{{brand=LanRen}}</div>
    <div>{{author=LanRen.AI}}</div>
    <div>{{describe=LanRen}}</div>
  </div>
</body>
</html>
```

```json
// resources/hyperframes/templates/image_full/text_capabilities.json
{
  "template_id": "image_full",
  "slots": [
    {
      "slot": "center",
      "roles": ["keyword", "title", "label"],
      "style_profiles": ["image_full", "default"],
      "layer_min": 0,
      "layer_max": 20
    },
    {
      "slot": "lower_third",
      "roles": ["subtitle", "keyword"],
      "style_profiles": ["image_full", "default"],
      "layer_min": 0,
      "layer_max": 20
    }
  ]
}
```

```json
// resources/hyperframes/templates/image_landscape_minimal/text_capabilities.json
{
  "template_id": "image_landscape_minimal",
  "slots": [
    {
      "slot": "center",
      "roles": ["keyword", "title", "label"],
      "style_profiles": ["image_landscape_minimal", "default"],
      "layer_min": 0,
      "layer_max": 20
    },
    {
      "slot": "lower_third",
      "roles": ["subtitle", "keyword"],
      "style_profiles": ["image_landscape_minimal", "default"],
      "layer_min": 0,
      "layer_max": 20
    }
  ]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hyperframes_compiler.py -k landscape_template_assets_and_inventory_exist -v`
Expected: PASS with both template ids documented and all entry assets present.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/template_render_context.py templates/1920x1080/image_landscape_minimal.html resources/hyperframes/templates/image_full/text_capabilities.json resources/hyperframes/templates/image_landscape_minimal/text_capabilities.json tests/test_hyperframes_compiler.py
git commit -m "feat: add landscape hyperframes template scaffolding"
```

### Task 2: Implement `image_full` native compiled template

**Files:**
- Create: `resources/hyperframes/templates/image_full/index.template.html`
- Create: `resources/hyperframes/templates/image_full/compositions/captions.template.html`
- Create: `resources/hyperframes/templates/image_full/compositions/text_layer.template.html`
- Modify: `tests/test_hyperframes_compiler.py`

- [ ] **Step 1: Write the failing `image_full` template tests**

```python
def test_image_full_landscape_template_uses_local_assets_and_raised_text_without_backplates():
    index_content = Path("resources/hyperframes/templates/image_full/index.template.html").read_text(encoding="utf-8")
    captions_content = Path("resources/hyperframes/templates/image_full/compositions/captions.template.html").read_text(encoding="utf-8")
    text_layer_content = Path("resources/hyperframes/templates/image_full/compositions/text_layer.template.html").read_text(encoding="utf-8")

    assert "./runtime/fonts/phase1_fonts.css" in index_content
    assert "../runtime/fonts/phase1_fonts.css" in captions_content
    assert "./runtime/vendor/gsap.min.js" in index_content
    assert "../runtime/vendor/gsap.min.js" in captions_content
    assert "https://fonts.googleapis.com" not in index_content
    assert "https://cdnjs.cloudflare.com" not in captions_content
    assert "bottom: 260px" not in captions_content
    assert "background: rgba(26, 37, 47, 0.78)" not in text_layer_content
    assert "top: 74%" not in text_layer_content
```

```python
def test_image_full_landscape_template_compiles_with_1920x1080_canvas(tmp_path: Path):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_full",
        canvas_width=1920,
        canvas_height=1080,
        duration=6.0,
        fps=30,
        title="横屏示例",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile="image_full",
        template_params={"author_desc": "Landscape"},
        visuals=[VisualClip(id="v1", frame_index=0, start=0.0, end=6.0, media_path="assets/images/01.png", media_type="image")],
        captions=[CaptionCue(id="c1", text="横屏字幕", start=0.0, end=2.0, frame_indices=[0], style_profile="image_full")],
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    captions_html = (tmp_path / "project" / "compositions" / "captions.html").read_text(encoding="utf-8")
    text_layer_html = (tmp_path / "project" / "compositions" / "text_layer.html").read_text(encoding="utf-8")
    assert 'data-width="1920"' in captions_html
    assert 'data-height="1080"' in captions_html
    assert "width: 1920px;" in text_layer_html
    assert "height: 1080px;" in text_layer_html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hyperframes_compiler.py -k image_full_landscape_template -v`
Expected: FAIL because the `image_full` native compiled templates do not exist yet.

- [ ] **Step 3: Implement the `image_full` shell, captions, and text layer**

```html
<!-- resources/hyperframes/templates/image_full/index.template.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=__CANVAS_WIDTH__, height=__CANVAS_HEIGHT__" />
    <title>Pixelle HyperFrames - Image Full</title>
    <link rel="stylesheet" href="./runtime/fonts/phase1_fonts.css" />
    <script src="./runtime/vendor/gsap.min.js"></script>
    <style>
      html, body, #main-comp { margin: 0; width: __CANVAS_WIDTH__px; height: __CANVAS_HEIGHT__px; overflow: hidden; }
      body { font-family: var(--hf-font-sans); color: #fff; }
      .visual-clip, .visual-frame, .visual-clip__media { position: absolute; inset: 0; width: 100%; height: 100%; }
      .visual-clip__media { object-fit: cover; display: block; }
      .title { position: absolute; top: 84px; left: 120px; right: 120px; text-align: center; font-size: 72px; font-weight: 700; text-shadow: 0 10px 32px rgba(0,0,0,0.45), -2px -2px 0 rgba(0,0,0,0.85), 2px -2px 0 rgba(0,0,0,0.85), -2px 2px 0 rgba(0,0,0,0.85), 2px 2px 0 rgba(0,0,0,0.85); }
      .info-cluster { position: absolute; left: 72px; bottom: 44px; display: flex; flex-direction: column; gap: 8px; z-index: 3; text-shadow: 0 4px 18px rgba(0,0,0,0.45); }
      .info-brand { font-size: 22px; font-weight: 600; letter-spacing: 0.08em; }
      .info-author { font-size: 28px; font-weight: 700; }
      .info-desc { font-size: 20px; font-weight: 400; opacity: 0.92; }
      #text-layer, #captions-layer { position: absolute; inset: 0; pointer-events: none; }
      #text-layer { z-index: 4; }
      #captions-layer { z-index: 5; }
    </style>
  </head>
  <body>
    <div id="main-comp" data-composition-id="main-comp" data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__" data-start="0" data-duration="__DURATION__" data-style-profile="__STYLE_PROFILE__">
      __VISUALS__
      <div class="title">__TITLE__</div>
      <div class="info-cluster">
        <div class="info-brand">__FOOTER__</div>
        <div class="info-author">__AUTHOR__</div>
        <div class="info-desc">__AUTHOR_DESC__</div>
      </div>
      <div id="text-layer" data-composition-id="text-layer" data-composition-src="compositions/text_layer.html" data-start="0" data-track-index="2" data-duration="__DURATION__"></div>
      <div id="captions-layer" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-track-index="3" data-duration="__DURATION__"></div>
      __AUDIO__
    </div>
    <script>
      const tl = gsap.timeline({ paused: true });
      window.__timelines = window.__timelines || {};
      window.__timelines["main-comp"] = tl;
    </script>
  </body>
</html>
```

```html
<!-- resources/hyperframes/templates/image_full/compositions/captions.template.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>Pixelle HyperFrames - Image Full Captions</title>
    <link rel="stylesheet" href="../runtime/fonts/phase1_fonts.css" />
    <script src="../runtime/vendor/gsap.min.js"></script>
    <style>
      html, body, [data-composition-id="captions"] { margin: 0; width: __CANVAS_WIDTH__px; height: __CANVAS_HEIGHT__px; overflow: hidden; }
      #captions-shell { position: absolute; left: 120px; right: 120px; bottom: 190px; }
      #captions-container { position: relative; min-height: 136px; }
      .caption-group { position: absolute; inset: 0; display: flex; justify-content: center; align-items: center; opacity: 0; visibility: hidden; }
      .caption-text { padding: 0; font-size: 54px; line-height: 1.35; font-weight: 700; color: #fff; text-align: center; text-shadow: 0 10px 30px rgba(0,0,0,0.48), -2px -2px 0 rgba(0,0,0,0.92), 2px -2px 0 rgba(0,0,0,0.92), -2px 2px 0 rgba(0,0,0,0.92), 2px 2px 0 rgba(0,0,0,0.92); }
    </style>
  </head>
  <body>
    <div id="captions-root" data-composition-id="captions" data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__" data-start="0" data-duration="__DURATION__">
      <div id="captions-shell"><div id="captions-container">__CAPTIONS__</div></div>
    </div>
    <script>/* keep tl.set visibility-only timeline, no fade */</script>
  </body>
</html>
```

```html
<!-- resources/hyperframes/templates/image_full/compositions/text_layer.template.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>Pixelle HyperFrames - Image Full Text Layer</title>
    <link rel="stylesheet" href="../runtime/fonts/phase1_fonts.css" />
    <script src="../runtime/vendor/gsap.min.js"></script>
    <style>
      html, body, #text-layer-root { margin: 0; width: __CANVAS_WIDTH__px; height: __CANVAS_HEIGHT__px; overflow: hidden; }
      .text-cue { position: absolute; left: 50%; top: 46%; transform: translate(-50%, -50%); opacity: 0; visibility: hidden; max-width: 1280px; text-align: center; }
      .text-cue[data-slot="lower_third"] { top: 66%; }
      .text-cue__content { display: inline-block; padding: 0; border-radius: 0; background: transparent; color: #fff; font-size: 50px; line-height: 1.35; font-weight: 700; box-shadow: none; text-shadow: 0 10px 30px rgba(0,0,0,0.48), -2px -2px 0 rgba(0,0,0,0.92), 2px -2px 0 rgba(0,0,0,0.92), -2px 2px 0 rgba(0,0,0,0.92), 2px 2px 0 rgba(0,0,0,0.92); }
    </style>
  </head>
  <body>
    <div id="text-layer-root" data-composition-id="text-layer" data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__" data-start="0" data-duration="__DURATION__">
      __TEXT_CUES__
    </div>
    <script>__TEXT_TIMELINE__</script>
  </body>
</html>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_compiler.py -k image_full_landscape_template -v`
Expected: PASS with local-only assets, raised captions, no caption/text-layer background panels, and successful `1920x1080` compilation.

- [ ] **Step 5: Commit**

```bash
git add resources/hyperframes/templates/image_full/index.template.html resources/hyperframes/templates/image_full/compositions/captions.template.html resources/hyperframes/templates/image_full/compositions/text_layer.template.html tests/test_hyperframes_compiler.py
git commit -m "feat: add hyperframes image_full landscape template"
```

### Task 3: Implement `image_landscape_minimal` native compiled template

**Files:**
- Create: `resources/hyperframes/templates/image_landscape_minimal/index.template.html`
- Create: `resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html`
- Create: `resources/hyperframes/templates/image_landscape_minimal/compositions/text_layer.template.html`
- Modify: `tests/test_hyperframes_compiler.py`

- [ ] **Step 1: Write the failing `image_landscape_minimal` template tests**

```python
def test_image_landscape_minimal_template_uses_local_assets_and_keeps_signature_in_right_corner():
    index_content = Path("resources/hyperframes/templates/image_landscape_minimal/index.template.html").read_text(encoding="utf-8")
    captions_content = Path("resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html").read_text(encoding="utf-8")
    text_layer_content = Path("resources/hyperframes/templates/image_landscape_minimal/compositions/text_layer.template.html").read_text(encoding="utf-8")

    assert "./runtime/fonts/phase1_fonts.css" in index_content
    assert "../runtime/fonts/phase1_fonts.css" in captions_content
    assert "https://fonts.googleapis.com" not in index_content
    assert "background: rgba(255, 250, 245, 0.9)" not in captions_content
    assert "background: rgba(26, 37, 47, 0.78)" not in text_layer_content
    assert "right: 72px" in index_content
    assert "__FOOTER__" in index_content
    assert "__AUTHOR__" in index_content
    assert "__AUTHOR_DESC__" in index_content
```

```python
def test_image_landscape_minimal_template_compiles_with_1920x1080_canvas(tmp_path: Path):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1920,
        canvas_height=1080,
        duration=6.0,
        fps=30,
        title="极简横屏",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile="image_landscape_minimal",
        template_params={"author_desc": "Minimal"},
        visuals=[VisualClip(id="v1", frame_index=0, start=0.0, end=6.0, media_path="assets/images/01.png", media_type="image")],
        captions=[CaptionCue(id="c1", text="简洁字幕", start=0.0, end=2.0, frame_indices=[0], style_profile="image_landscape_minimal")],
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    captions_html = (tmp_path / "project" / "compositions" / "captions.html").read_text(encoding="utf-8")
    assert 'data-width="1920"' in index_html
    assert 'data-height="1080"' in index_html
    assert 'data-width="1920"' in captions_html
    assert 'data-height="1080"' in captions_html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hyperframes_compiler.py -k image_landscape_minimal_template -v`
Expected: FAIL because the `image_landscape_minimal` compiled template files do not exist yet.

- [ ] **Step 3: Implement the `image_landscape_minimal` shell, captions, and text layer**

```html
<!-- resources/hyperframes/templates/image_landscape_minimal/index.template.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=__CANVAS_WIDTH__, height=__CANVAS_HEIGHT__" />
    <title>Pixelle HyperFrames - Image Landscape Minimal</title>
    <link rel="stylesheet" href="./runtime/fonts/phase1_fonts.css" />
    <script src="./runtime/vendor/gsap.min.js"></script>
    <style>
      html, body, #main-comp { margin: 0; width: __CANVAS_WIDTH__px; height: __CANVAS_HEIGHT__px; overflow: hidden; }
      body { font-family: var(--hf-font-serif, var(--hf-font-sans)); background: #f8f5ef; color: #171410; }
      .bg-decoration { position: absolute; inset: 0; pointer-events: none; }
      .header { position: absolute; top: 92px; left: 110px; max-width: 520px; z-index: 2; }
      .title { font-size: 68px; line-height: 1.15; font-weight: 400; letter-spacing: -0.03em; }
      .visual-shell { position: absolute; left: 540px; right: 300px; top: 170px; bottom: 210px; display: flex; align-items: center; justify-content: center; }
      .visual-shell .visual-clip { position: relative; width: 100%; height: 100%; max-width: 980px; max-height: 620px; }
      .visual-shell .visual-clip__media { width: 100%; height: 100%; object-fit: contain; display: block; background: #fff; }
      .signature { position: absolute; right: 72px; bottom: 48px; display: flex; flex-direction: column; align-items: flex-end; gap: 8px; z-index: 3; }
      .signature-brand { font-size: 22px; font-weight: 600; letter-spacing: 0.08em; }
      .signature-author { font-size: 24px; font-weight: 500; }
      .signature-desc { font-size: 18px; opacity: 0.8; }
      #text-layer, #captions-layer { position: absolute; inset: 0; pointer-events: none; }
      #text-layer { z-index: 4; }
      #captions-layer { z-index: 5; }
    </style>
  </head>
  <body>
    <div id="main-comp" data-composition-id="main-comp" data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__" data-start="0" data-duration="__DURATION__" data-style-profile="__STYLE_PROFILE__">
      <div class="bg-decoration"></div>
      <div class="header"><div class="title">__TITLE__</div></div>
      <div class="visual-shell">__VISUALS__</div>
      <div class="signature">
        <div class="signature-brand">__FOOTER__</div>
        <div class="signature-author">__AUTHOR__</div>
        <div class="signature-desc">__AUTHOR_DESC__</div>
      </div>
      <div id="text-layer" data-composition-id="text-layer" data-composition-src="compositions/text_layer.html" data-start="0" data-track-index="2" data-duration="__DURATION__"></div>
      <div id="captions-layer" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-track-index="3" data-duration="__DURATION__"></div>
      __AUDIO__
    </div>
    <script>
      const tl = gsap.timeline({ paused: true });
      window.__timelines = window.__timelines || {};
      window.__timelines["main-comp"] = tl;
    </script>
  </body>
</html>
```

```html
<!-- resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>Pixelle HyperFrames - Image Landscape Minimal Captions</title>
    <link rel="stylesheet" href="../runtime/fonts/phase1_fonts.css" />
    <script src="../runtime/vendor/gsap.min.js"></script>
    <style>
      html, body, [data-composition-id="captions"] { margin: 0; width: __CANVAS_WIDTH__px; height: __CANVAS_HEIGHT__px; overflow: hidden; }
      #captions-shell { position: absolute; left: 520px; right: 280px; bottom: 164px; }
      #captions-container { position: relative; min-height: 120px; }
      .caption-group { position: absolute; inset: 0; display: flex; justify-content: center; align-items: center; opacity: 0; visibility: hidden; }
      .caption-text { padding: 0; font-size: 44px; line-height: 1.45; font-weight: 500; color: #171410; text-align: center; text-shadow: 0 3px 12px rgba(255,255,255,0.28); }
    </style>
  </head>
  <body>
    <div id="captions-root" data-composition-id="captions" data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__" data-start="0" data-duration="__DURATION__">
      <div id="captions-shell"><div id="captions-container">__CAPTIONS__</div></div>
    </div>
    <script>/* keep tl.set visibility-only timeline, no fade */</script>
  </body>
</html>
```

```html
<!-- resources/hyperframes/templates/image_landscape_minimal/compositions/text_layer.template.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>Pixelle HyperFrames - Image Landscape Minimal Text Layer</title>
    <link rel="stylesheet" href="../runtime/fonts/phase1_fonts.css" />
    <script src="../runtime/vendor/gsap.min.js"></script>
    <style>
      html, body, #text-layer-root { margin: 0; width: __CANVAS_WIDTH__px; height: __CANVAS_HEIGHT__px; overflow: hidden; }
      .text-cue { position: absolute; left: 50%; top: 44%; transform: translate(-50%, -50%); opacity: 0; visibility: hidden; max-width: 1080px; text-align: center; }
      .text-cue[data-slot="lower_third"] { top: 63%; }
      .text-cue__content { display: inline-block; padding: 0; border-radius: 0; background: transparent; color: #171410; font-size: 42px; line-height: 1.45; font-weight: 500; box-shadow: none; text-shadow: 0 3px 12px rgba(255,255,255,0.28); }
    </style>
  </head>
  <body>
    <div id="text-layer-root" data-composition-id="text-layer" data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__" data-start="0" data-duration="__DURATION__">
      __TEXT_CUES__
    </div>
    <script>__TEXT_TIMELINE__</script>
  </body>
</html>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hyperframes_compiler.py -k image_landscape_minimal_template -v`
Expected: PASS with right-corner signature mapping, no caption/text-layer background panels, and successful `1920x1080` compilation.

- [ ] **Step 5: Commit**

```bash
git add resources/hyperframes/templates/image_landscape_minimal/index.template.html resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html resources/hyperframes/templates/image_landscape_minimal/compositions/text_layer.template.html tests/test_hyperframes_compiler.py
git commit -m "feat: add hyperframes image_landscape_minimal template"
```

### Task 4: Lock pipeline routing and landscape canvas behavior

**Files:**
- Modify: `tests/test_standard_pipeline_hyperframes_mode.py`
- Verify only: `pixelle_video/pipelines/standard.py`

- [ ] **Step 1: Write the failing pipeline regression tests**

```python
def test_landscape_hyperframes_templates_resolve_without_fallback(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)

    full_ctx = _build_storyboard_context(tmp_path, frame_template="1920x1080/image_full.html")
    minimal_ctx = _build_storyboard_context(tmp_path, frame_template="1920x1080/image_landscape_minimal.html")

    assert pipeline._resolve_hyperframes_template_id(full_ctx.config) == "image_full"
    assert pipeline._resolve_hyperframes_template_id(minimal_ctx.config) == "image_landscape_minimal"
    assert pipeline._get_hyperframes_fallback_reason(full_ctx) is None
    assert pipeline._get_hyperframes_fallback_reason(minimal_ctx) is None
```

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frame_template",
    ["1920x1080/image_full.html", "1920x1080/image_landscape_minimal.html"],
)
async def test_post_production_uses_landscape_template_canvas_size(monkeypatch, tmp_path, frame_template):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, frame_template=frame_template)
    ctx.config.media_width = 768
    ctx.config.media_height = 768
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", lambda input_path, output_path: output_path)
    monkeypatch.setattr(pipeline, "_concat_audio_files", lambda audio_paths, output_path, **kwargs: Path(output_path).write_bytes(b"master"))
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda audio_path: 4.0)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert (manifest.canvas_width, manifest.canvas_height) == (1920, 1080)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_standard_pipeline_hyperframes_mode.py -k "landscape_hyperframes_templates or landscape_template_canvas_size" -v`
Expected: FAIL before Tasks 2 and 3 are complete because the template directories are still missing and fallback remains active.

- [ ] **Step 3: Broaden the existing pipeline tests and keep production routing unchanged**

```python
# tests/test_standard_pipeline_hyperframes_mode.py
@pytest.mark.parametrize(
    "frame_template, expected_template_id",
    [
        ("1080x1920/default.html", "image_default"),
        ("1920x1080/image_full.html", "image_full"),
        ("1920x1080/image_landscape_minimal.html", "image_landscape_minimal"),
    ],
)
def test_hyperframes_template_id_resolution_and_fallback_contract(tmp_path, frame_template, expected_template_id):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, frame_template=frame_template)

    assert pipeline._resolve_hyperframes_template_id(ctx.config) == expected_template_id
    assert pipeline._get_hyperframes_fallback_reason(ctx) is None
```

Production note: `pixelle_video/pipelines/standard.py` should not need logic changes here. Passing tests are the signal that the existing stem-based routing already supports the new horizontal templates once the asset directories exist.

- [ ] **Step 4: Run the focused regression suites**

Run: `uv run pytest tests/test_hyperframes_compiler.py tests/test_standard_pipeline_hyperframes_mode.py -k "image_full_landscape_template or image_landscape_minimal_template or landscape_hyperframes_templates or landscape_template_canvas_size" -v`
Expected: PASS with no fallback, `1920x1080` canvas dimensions, and both subtitle systems remaining background-free.

- [ ] **Step 5: Commit**

```bash
git add tests/test_standard_pipeline_hyperframes_mode.py tests/test_hyperframes_compiler.py
git commit -m "test: cover hyperframes landscape template routing"
```

### Task 5: Run the full targeted verification pass

**Files:**
- Verify only: `resources/hyperframes/templates/image_full/*`
- Verify only: `resources/hyperframes/templates/image_landscape_minimal/*`
- Verify only: `templates/1920x1080/image_landscape_minimal.html`
- Verify only: `tests/test_hyperframes_compiler.py`
- Verify only: `tests/test_standard_pipeline_hyperframes_mode.py`

- [ ] **Step 1: Run the full HyperFrames compiler test file**

Run: `uv run pytest tests/test_hyperframes_compiler.py -v`
Expected: PASS, including local-font checks, local-GSAP checks, new landscape template source assertions, and `1920x1080` compile assertions.

- [ ] **Step 2: Run the HyperFrames pipeline regression file**

Run: `uv run pytest tests/test_standard_pipeline_hyperframes_mode.py -v`
Expected: PASS, including both new landscape template ids resolving without fallback and preserving `hyperframes_compiled` as the effective backend.

- [ ] **Step 3: Sanity-check the changed templates for accidental remote dependencies**

Run: `rg -n "https://fonts.googleapis.com|https://cdnjs.cloudflare.com|https://cdn" resources/hyperframes/templates/image_full resources/hyperframes/templates/image_landscape_minimal templates/1920x1080/image_landscape_minimal.html`
Expected: No output.

- [ ] **Step 4: Check the working tree and prepare the review handoff**

Run: `git status --short`
Expected: Only the planned template, inventory, and test files are modified.

- [ ] **Step 5: Commit the verification snapshot**

```bash
git add pixelle_video/models/template_render_context.py templates/1920x1080/image_landscape_minimal.html resources/hyperframes/templates/image_full resources/hyperframes/templates/image_landscape_minimal tests/test_hyperframes_compiler.py tests/test_standard_pipeline_hyperframes_mode.py
git commit -m "feat: add hyperframes landscape storyboard templates"
```
