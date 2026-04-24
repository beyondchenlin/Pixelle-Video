# Text Layer Full Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成图片加字平台文字层 C1-C5：语义规划、cue 编译、HyperFrames 渲染、ASS legacy burn-in、native prompt 实验和 History 摘要。

**Architecture:** `CreationPackage.text_overlay_plan` 是语义事实来源，`TextCueCompiler` 把它编译成 `RenderManifest.text_tracks/text_cues`。HyperFrames 直接消费 `TextCue` 静态编译 HTML，legacy 路线把同一批 `TextCue` 导出 ASS 后烧录，native prompt 只消费受控投影片段，不拥有完整文字层。

**Tech Stack:** Python dataclass models, pytest, Ruff, FFmpeg/ffmpeg-python, HyperFrames static HTML templates, GSAP timeline snippets.

---

## Execution Constraints

- 本仓库 `AGENTS.md` 禁止 `git worktree`，即使 superpowers 默认建议 worktree，本计划也必须在当前工作区执行。
- 每个任务只暂存本任务列出的文件，使用 `git add <exact files>`，不要提交当前工作区已有的无关改动。
- 当前分支如存在非本任务的未推送提交，提交完成后先运行 `git log --oneline origin/dev..HEAD`。如果会把无关提交一起推送，停止并说明 push 被阻塞；否则按仓库规则立即 `git push`。
- 每个代码任务先写失败测试，再写实现，再运行该任务测试。跨模块任务完成后运行对应集成测试，最后运行 `uv run pytest -q` 和 Ruff。

## File Structure

- Create `pixelle_video/services/text_overlay_planner.py`: 从 narrations、frame 语义和 `TextRenderingPolicy` 生成 `TextOverlayPlan`。
- Create `tests/test_text_overlay_planner.py`: 覆盖 density、候选来源、renderer target、frame index 和 native hint 限量。
- Create `pixelle_video/models/native_prompt.py`: 定义轻量 `NativePromptHint`，只承载 prompt fragment 和候选来源 ID。
- Create `pixelle_video/services/native_prompt_projection.py`: 从 `TextOverlayPlan` 投影 native prompt hints。
- Modify `pixelle_video/utils/prompt_helper.py`: 增加 policy-aware no-text helper，避免 native hint 与绝对 no-text 规则冲突。
- Modify `pixelle_video/utils/content_generators.py`: 给 `generate_styled_image_prompt_batch(...)` 增加 native hint 和 `TextRenderingPolicy` 入参。
- Create `tests/test_native_prompt_projection.py`: 覆盖只投影 allowed target、限量、摘要。
- Create `tests/test_content_generators_text_policy.py`: 覆盖 prompt 注入顺序与 legacy 兼容。
- Create `pixelle_video/services/text_cue_compiler.py`: 把 `CreationPackage.text_overlay_plan` 加 timing/storyboard 编译成 `TextTrack/TextCue`。
- Create `tests/test_text_cue_compiler.py`: 覆盖 frame-relative、sentence-relative、remapped timing、fallback timing 和 source 可追溯。
- Modify `pixelle_video/pipelines/linear.py`: 给 `PipelineContext` 增加 `creation_package`。
- Modify `pixelle_video/pipelines/standard.py`: 在 `plan_visuals` 和 `initialize_storyboard` 建立创作包，在 post-production 生成 text cues。
- Create `pixelle_video/models/template_text_capabilities.py`: 声明模板 slot/role/style 能力。
- Add `resources/hyperframes/templates/image_default/text_capabilities.json`.
- Add `resources/hyperframes/templates/image_life_insights_light/text_capabilities.json`.
- Modify `pixelle_video/services/hyperframes_project_service.py`: 归一化 `text_cues`，加载并校验 `TemplateTextCapabilities`。
- Modify `pixelle_video/services/hyperframes_compiler.py`: 静态编译 `text_layer.html`。
- Modify `resources/hyperframes/templates/image_default/index.template.html`.
- Modify `resources/hyperframes/templates/image_life_insights_light/index.template.html`.
- Add `resources/hyperframes/templates/image_default/compositions/text_layer.template.html`.
- Add `resources/hyperframes/templates/image_life_insights_light/compositions/text_layer.template.html`.
- Modify `tests/test_hyperframes_compiler.py` and `tests/test_hyperframes_project_service.py`: 覆盖文字层静态编译、HTML escape、capabilities 和 text cue clamp/filter。
- Create `pixelle_video/services/ass_text_adapter.py`: 导出 `master.ass`、`subtitle_only.ass`、`overlay_only.ass`。
- Modify `pixelle_video/services/video.py`: 增加 `burn_ass_subtitles(...)` 和 FFmpeg filter path escape。
- Modify `tests/test_video_service.py`: 覆盖 ASS 路径转义、禁止同路径覆写、可选真实 smoke。
- Create `tests/test_ass_text_adapter.py`: 覆盖中文、ASS 特殊字符、字幕/overlay 分离。
- Modify `tests/test_standard_pipeline_hyperframes_mode.py` and `tests/test_standard_pipeline_staged_mode.py`: 覆盖 HyperFrames manifest 接入和 legacy burn-in 顺序。
- Modify `web/pages/2_📚_History.py`, `web/i18n/locales/zh_CN.json`, `web/i18n/locales/en_US.json`: 展示 `metadata.result.text_layer_summary`。

---

### Task 1: TextOverlayPlanner

**Files:**
- Create: `pixelle_video/services/text_overlay_planner.py`
- Test: `tests/test_text_overlay_planner.py`

- [ ] **Step 1: Write failing planner tests**

Add `tests/test_text_overlay_planner.py`:

```python
from pixelle_video.models.text_overlay import TextRenderingPolicy
from pixelle_video.services.text_overlay_planner import TextOverlayPlanner


def test_planner_limits_keyword_candidates_by_density_and_frame():
    policy = TextRenderingPolicy(
        image_text_mode="programmatic_only",
        enabled_targets=("hyperframes", "ass"),
        density="low",
        max_items_per_frame=1,
    )

    plan = TextOverlayPlanner().plan(
        narrations=["保持专注，稳定行动。", "及时复盘，持续优化。"],
        policy=policy,
    )

    assert plan.version == "text_overlay_plan.v1"
    assert len(plan.candidates) == 2
    assert [item.source["frame_index"] for item in plan.candidates] == [0, 1]
    assert all(item.role == "keyword" for item in plan.candidates)
    assert all(item.renderer_targets == ("hyperframes", "ass") for item in plan.candidates)


def test_planner_emits_native_candidates_only_when_policy_allows_native_prompt():
    policy = TextRenderingPolicy(
        image_text_mode="native_hint",
        enabled_targets=("native_prompt",),
        density="medium",
        max_items_per_frame=2,
        allow_native_text_in_image=True,
    )

    plan = TextOverlayPlanner().plan(
        narrations=["把品牌名 Pixelle 放在画面中心。"],
        policy=policy,
    )

    assert [item.role for item in plan.candidates] == ["model_native_hint"]
    assert plan.candidates[0].renderer_targets == ("native_prompt",)
    assert plan.candidates[0].source["kind"] == "narration"
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
uv run pytest tests/test_text_overlay_planner.py -q
```

Expected: FAIL because `pixelle_video.services.text_overlay_planner` does not exist.

- [ ] **Step 3: Implement planner**

Create `pixelle_video/services/text_overlay_planner.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from pixelle_video.models.text_overlay import (
    TextOverlayCandidate,
    TextOverlayPlan,
    TextRenderingPolicy,
)


_PUNCTUATION_RE = re.compile(r"[\s,，。.!！?？;；:：、]+")


@dataclass(frozen=True)
class TextOverlayPlanner:
    """Build semantic text overlay candidates from frame narrations."""

    def plan(
        self,
        *,
        narrations: Sequence[str],
        policy: TextRenderingPolicy,
    ) -> TextOverlayPlan:
        candidates: list[TextOverlayCandidate] = []
        targets = tuple(policy.enabled_targets)
        if policy.image_text_mode in {"suppress"} or policy.max_items_per_frame == 0:
            return TextOverlayPlan(
                candidates=(),
                source_summary={
                    "narration_count": len(narrations),
                    "density": policy.density,
                    "candidate_count": 0,
                },
            )

        role = "model_native_hint" if "native_prompt" in targets else "keyword"
        suggested_slot = "native_prompt" if role == "model_native_hint" else "center"
        for frame_index, narration in enumerate(narrations):
            phrases = self._select_phrases(narration, policy.max_items_per_frame)
            for phrase_index, phrase in enumerate(phrases):
                candidates.append(
                    TextOverlayCandidate(
                        id=f"text-{frame_index + 1}-{phrase_index + 1}",
                        text=phrase,
                        role=role,
                        suggested_slot=suggested_slot,
                        renderer_targets=targets,
                        importance=max(0.1, 1.0 - phrase_index * 0.1),
                        confidence=0.75,
                        source={
                            "kind": "narration",
                            "frame_index": frame_index,
                            "phrase_index": phrase_index,
                        },
                    )
                )

        return TextOverlayPlan(
            candidates=tuple(candidates),
            source_summary={
                "narration_count": len(narrations),
                "density": policy.density,
                "candidate_count": len(candidates),
            },
        )

    def _select_phrases(self, narration: str, limit: int) -> list[str]:
        cleaned = [part.strip() for part in _PUNCTUATION_RE.split(narration or "")]
        tokens = [part for part in cleaned if part]
        if not tokens:
            return []
        ranked = sorted(tokens, key=lambda item: (-len(item), tokens.index(item)))
        return ranked[: max(0, limit)]
```

- [ ] **Step 4: Verify planner tests pass**

Run:

```powershell
uv run pytest tests/test_text_overlay_planner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit planner**

Run:

```powershell
git add pixelle_video/services/text_overlay_planner.py tests/test_text_overlay_planner.py
git commit -m "feat: add text overlay planner"
git log --oneline origin/dev..HEAD
```

Push only if the ahead list contains no unrelated commits.

---

### Task 2: Native Prompt Projection And Policy-Aware Prompts

**Files:**
- Create: `pixelle_video/models/native_prompt.py`
- Create: `pixelle_video/services/native_prompt_projection.py`
- Modify: `pixelle_video/utils/prompt_helper.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Test: `tests/test_native_prompt_projection.py`
- Test: `tests/test_content_generators_text_policy.py`

- [ ] **Step 1: Write failing projection tests**

Create `tests/test_native_prompt_projection.py`:

```python
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan, TextRenderingPolicy
from pixelle_video.services.native_prompt_projection import NativePromptProjection


def test_projection_only_uses_native_prompt_candidates_and_limits_per_frame():
    plan = TextOverlayPlan(
        candidates=(
            TextOverlayCandidate(
                id="native-1",
                text="Pixelle",
                role="model_native_hint",
                renderer_targets=("native_prompt",),
                source={"frame_index": 0},
            ),
            TextOverlayCandidate(
                id="overlay-1",
                text="稳定",
                role="keyword",
                renderer_targets=("hyperframes",),
                source={"frame_index": 0},
            ),
        )
    )
    policy = TextRenderingPolicy(
        image_text_mode="native_hint",
        enabled_targets=("native_prompt",),
        allow_native_text_in_image=True,
        max_items_per_frame=1,
    )

    projected = NativePromptProjection().project(plan=plan, policy=policy)

    assert list(projected.keys()) == [0]
    assert projected[0][0].prompt_fragment == 'render the planned text "Pixelle"'
    assert projected[0][0].source_candidate_ids == ("native-1",)
```

- [ ] **Step 2: Write failing prompt policy tests**

Create `tests/test_content_generators_text_policy.py`:

```python
from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.text_overlay import TextRenderingPolicy
from pixelle_video.utils.prompt_helper import (
    NO_TEXT_POSITIVE_RULE,
    apply_text_rendering_policy,
    select_negative_text_rules,
)


def test_policy_keeps_legacy_no_text_behavior_without_native_hints():
    policy = TextRenderingPolicy()

    prompt = apply_text_rendering_policy("a clean desk", policy=policy, has_native_hints=False)

    assert NO_TEXT_POSITIVE_RULE in prompt
    assert "text" in select_negative_text_rules(policy=policy, has_native_hints=False)


def test_policy_uses_planned_only_guard_when_native_hints_exist():
    policy = TextRenderingPolicy(
        image_text_mode="native_hint",
        enabled_targets=("native_prompt",),
        allow_native_text_in_image=True,
    )

    prompt = apply_text_rendering_policy(
        "a sign, render the planned text \"Pixelle\"",
        policy=policy,
        has_native_hints=True,
    )

    assert "render the planned text" in prompt
    assert NO_TEXT_POSITIVE_RULE not in prompt
    assert "no extra captions" in prompt
    assert "text" not in select_negative_text_rules(policy=policy, has_native_hints=True)


def test_native_prompt_hint_to_dict_is_lightweight():
    hint = NativePromptHint(prompt_fragment="render the planned text \"Pixelle\"", source_candidate_ids=("c1",))

    assert hint.to_dict() == {
        "prompt_fragment": "render the planned text \"Pixelle\"",
        "role": "model_native_hint",
        "source_candidate_ids": ["c1"],
    }
```

- [ ] **Step 3: Verify tests fail**

Run:

```powershell
uv run pytest tests/test_native_prompt_projection.py tests/test_content_generators_text_policy.py -q
```

Expected: FAIL because native prompt model, projection service, and helpers do not exist.

- [ ] **Step 4: Implement native prompt model and projection**

Create `pixelle_video/models/native_prompt.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativePromptHint:
    prompt_fragment: str
    role: str = "model_native_hint"
    source_candidate_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "prompt_fragment": self.prompt_fragment,
            "role": self.role,
            "source_candidate_ids": list(self.source_candidate_ids),
        }
```

Create `pixelle_video/services/native_prompt_projection.py`:

```python
from __future__ import annotations

from collections import defaultdict

from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.text_overlay import TextOverlayPlan, TextRenderingPolicy


class NativePromptProjection:
    def project(
        self,
        *,
        plan: TextOverlayPlan,
        policy: TextRenderingPolicy,
    ) -> dict[int, tuple[NativePromptHint, ...]]:
        if "native_prompt" not in policy.enabled_targets or not policy.allow_native_text_in_image:
            return {}

        grouped: dict[int, list[NativePromptHint]] = defaultdict(list)
        for candidate in plan.candidates:
            if candidate.role != "model_native_hint" and "native_prompt" not in candidate.renderer_targets:
                continue
            frame_index = int(candidate.source.get("frame_index", 0))
            if len(grouped[frame_index]) >= policy.max_items_per_frame:
                continue
            grouped[frame_index].append(
                NativePromptHint(
                    prompt_fragment=f'render the planned text "{candidate.text}"',
                    source_candidate_ids=(candidate.id,),
                )
            )

        return {index: tuple(hints) for index, hints in sorted(grouped.items())}
```

- [ ] **Step 5: Implement policy-aware prompt helpers**

Modify `pixelle_video/utils/prompt_helper.py`:

```python
PLANNED_TEXT_POSITIVE_GUARD = (
    "only render the explicitly requested planned text, no extra captions, "
    "no extra subtitles, no watermark, no logo text, no random letters"
)
PLANNED_TEXT_NEGATIVE_RULES: tuple[str, ...] = (
    "unplanned text",
    "random letters",
    "watermark",
    "logo text",
    "extra captions",
    "extra subtitles",
)


def apply_text_rendering_policy(prompt: str, *, policy, has_native_hints: bool) -> str:
    if has_native_hints and getattr(policy, "allow_native_text_in_image", False):
        return ", ".join(_normalize_prompt_list([prompt, PLANNED_TEXT_POSITIVE_GUARD]))
    return apply_no_text_policy(
        prompt,
        enabled=getattr(policy, "suppress_unplanned_embedded_text", True),
    )


def select_negative_text_rules(*, policy, has_native_hints: bool) -> tuple[str, ...] | None:
    if has_native_hints and getattr(policy, "allow_native_text_in_image", False):
        return PLANNED_TEXT_NEGATIVE_RULES
    if getattr(policy, "suppress_unplanned_embedded_text", True):
        return NO_TEXT_NEGATIVE_RULES
    return None
```

- [ ] **Step 6: Extend prompt batch interface without carrying full text layer**

Modify `generate_styled_image_prompt_batch(...)` in `pixelle_video/utils/content_generators.py`:

```python
from collections.abc import Mapping, Sequence
from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.text_overlay import build_text_rendering_policy, TextRenderingPolicy
from pixelle_video.utils.prompt_helper import apply_text_rendering_policy, select_negative_text_rules
```

Add parameters:

```python
    native_prompt_hints_by_frame: Mapping[int, Sequence[NativePromptHint | str]] | None = None,
    text_rendering_policy: TextRenderingPolicy | dict[str, Any] | None = None,
```

Before final prompt assembly:

```python
    policy = (
        text_rendering_policy
        if isinstance(text_rendering_policy, TextRenderingPolicy)
        else build_text_rendering_policy(
            text_rendering_policy,
            forbid_embedded_text_in_image=forbid_embedded_text_in_image,
        )
    )
    native_hints = dict(native_prompt_hints_by_frame or {})
```

After `final_prompts` is built and before no-text policy:

```python
    final_prompts = [
        ", ".join(
            _normalize_prompt_list(
                [
                    prompt,
                    *[
                        hint.prompt_fragment if hasattr(hint, "prompt_fragment") else str(hint)
                        for hint in native_hints.get(index, ())
                    ],
                ]
            )
        )
        for index, prompt in enumerate(final_prompts)
    ]

    final_prompts = [
        apply_text_rendering_policy(
            prompt,
            policy=policy,
            has_native_hints=bool(native_hints.get(index)),
        )
        for index, prompt in enumerate(final_prompts)
    ]
```

Replace negative prompt extra rules:

```python
    has_any_native_hints = any(native_hints.values())
    negative_prompt = assemble_negative_prompt(
        resolved_style,
        supports_negative_prompt=capabilities.supports_negative_prompt,
        extra_negative_rules=select_negative_text_rules(
            policy=policy,
            has_native_hints=has_any_native_hints,
        ),
    )
```

Store only a lightweight summary:

```python
    if planning_snapshot is None:
        planning_snapshot = {}
    planning_snapshot["text_rendering_policy"] = policy.to_dict()
    planning_snapshot["native_prompt_hint_count"] = sum(len(items) for items in native_hints.values())
    planning_snapshot["frames_with_native_hints"] = sorted(native_hints)
```

- [ ] **Step 7: Verify focused tests pass**

Run:

```powershell
uv run pytest tests/test_native_prompt_projection.py tests/test_content_generators_text_policy.py -q
uv run pytest tests/test_custom_pipeline_styled_batch.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit native prompt support**

Run:

```powershell
git add pixelle_video/models/native_prompt.py pixelle_video/services/native_prompt_projection.py pixelle_video/utils/prompt_helper.py pixelle_video/utils/content_generators.py tests/test_native_prompt_projection.py tests/test_content_generators_text_policy.py tests/test_custom_pipeline_styled_batch.py
git commit -m "feat: add controlled native text prompt hints"
git log --oneline origin/dev..HEAD
```

Push only if the ahead list contains no unrelated commits.

---

### Task 3: TextCueCompiler And CreationPackage Runtime Wiring

**Files:**
- Create: `pixelle_video/services/text_cue_compiler.py`
- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_text_cue_compiler.py`
- Test: `tests/test_render_package_models.py`

- [ ] **Step 1: Write failing compiler tests**

Create `tests/test_text_cue_compiler.py`:

```python
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.render_package import SentenceUnit
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan
from pixelle_video.services.text_cue_compiler import TextCueCompiler


def test_compiler_prefers_remapped_sentence_timing():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="重点词",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("hyperframes",),
                    source={"frame_index": 0, "sentence_id": "s1"},
                ),
            )
        ),
    )
    sentences = [
        SentenceUnit(
            id="s1",
            text="重点词来自这一句。",
            frame_indices=[0],
            source_start=1.0,
            source_end=3.0,
            remapped_start=0.5,
            remapped_end=2.2,
        )
    ]

    tracks, cues = TextCueCompiler().compile(package=package, sentence_units=sentences)

    assert tracks[0].id == "track-hyperframes-keyword"
    assert cues[0].start == 0.5
    assert cues[0].end == 2.2
    assert cues[0].source["candidate_id"] == "candidate-1"


def test_compiler_uses_frame_fallback_when_sentence_timing_missing():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="稳定",
                    role="keyword",
                    renderer_targets=("ass",),
                    source={"frame_index": 2},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(package=package, sentence_units=[], frame_duration=1.5)

    assert tracks[0].renderer_targets == ("ass",)
    assert cues[0].start == 3.0
    assert cues[0].end == 4.5
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
uv run pytest tests/test_text_cue_compiler.py -q
```

Expected: FAIL because `TextCueCompiler` does not exist.

- [ ] **Step 3: Implement compiler**

Create `pixelle_video/services/text_cue_compiler.py`:

```python
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Sequence

from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.render_package import SentenceUnit, TextCue, TextTrack, resolve_render_window


@dataclass(frozen=True)
class TextCueCompiler:
    default_duration: float = 1.5

    def compile(
        self,
        *,
        package: CreationPackage,
        sentence_units: Sequence[SentenceUnit],
        frame_duration: float | None = None,
    ) -> tuple[list[TextTrack], list[TextCue]]:
        plan = package.text_overlay_plan
        if plan is None:
            return [], []

        sentences_by_id = {sentence.id: sentence for sentence in sentence_units}
        tracks: OrderedDict[str, TextTrack] = OrderedDict()
        cues: list[TextCue] = []
        fallback_duration = float(frame_duration or self.default_duration)

        for index, candidate in enumerate(plan.candidates, start=1):
            targets = tuple(candidate.renderer_targets or ("hyperframes",))
            primary_target = targets[0]
            track_id = f"track-{primary_target}-{candidate.role}"
            if track_id not in tracks:
                tracks[track_id] = TextTrack(
                    id=track_id,
                    kind=candidate.role if candidate.role != "model_native_hint" else "native_hint",
                    name=candidate.role,
                    renderer_targets=targets,
                    layer=index,
                )

            start, end = self._resolve_candidate_window(
                candidate_source=candidate.source,
                sentences_by_id=sentences_by_id,
                frame_duration=fallback_duration,
            )
            cues.append(
                TextCue(
                    id=f"text-cue-{index}",
                    track_id=track_id,
                    text=candidate.text,
                    start=start,
                    end=end,
                    role=candidate.role,
                    frame_indices=(int(candidate.source.get("frame_index", 0)),),
                    slot=candidate.suggested_slot,
                    layer=index,
                    priority=index,
                    source={
                        "kind": "text_overlay_plan",
                        "candidate_id": candidate.id,
                    },
                )
            )

        return list(tracks.values()), cues

    def _resolve_candidate_window(
        self,
        *,
        candidate_source,
        sentences_by_id: dict[str, SentenceUnit],
        frame_duration: float,
    ) -> tuple[float, float]:
        sentence_id = candidate_source.get("sentence_id")
        if sentence_id and sentence_id in sentences_by_id:
            try:
                start, end = resolve_render_window(sentences_by_id[str(sentence_id)])
                return float(start), max(float(end), float(start) + 0.1)
            except ValueError:
                pass

        frame_index = int(candidate_source.get("frame_index", 0))
        start = frame_index * frame_duration
        return start, start + frame_duration
```

- [ ] **Step 4: Wire CreationPackage into pipeline context**

Modify `pixelle_video/pipelines/linear.py`:

```python
from pixelle_video.models.creation_package import CreationPackage
```

Add field to `PipelineContext` after `planning_snapshot`:

```python
    creation_package: Optional[CreationPackage] = None
```

Modify `pixelle_video/pipelines/standard.py` imports:

```python
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.text_overlay import build_text_rendering_policy
from pixelle_video.services.native_prompt_projection import NativePromptProjection
from pixelle_video.services.text_cue_compiler import TextCueCompiler
from pixelle_video.services.text_overlay_planner import TextOverlayPlanner
```

In `plan_visuals`, before calling `generate_styled_image_prompt_batch(...)`, build policy and native hints:

```python
            text_policy = build_text_rendering_policy(
                ctx.params.get("text_layer"),
                forbid_embedded_text_in_image=ctx.params.get("forbid_embedded_text_in_image", True),
            )
            text_plan = TextOverlayPlanner().plan(narrations=ctx.narrations, policy=text_policy)
            ctx.creation_package = CreationPackage(
                task_id=ctx.task_id or "",
                text_overlay_plan=text_plan,
                prompt_plan={"text_rendering_policy": text_policy.to_dict()},
            )
            native_hints = NativePromptProjection().project(plan=text_plan, policy=text_policy)
```

Pass into prompt batch:

```python
                native_prompt_hints_by_frame=native_hints,
                text_rendering_policy=text_policy,
```

In `initialize_storyboard`, after `ctx.timing_plan = planner.build(...)`, persist the semantic plan:

```python
        if ctx.creation_package is not None and ctx.task_dir:
            text_plan_path = Path(ctx.task_dir) / "text_overlay_plan.json"
            text_plan_path.write_text(
                json.dumps(ctx.creation_package.text_overlay_plan.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
```

Add `import json`.

- [ ] **Step 5: Verify compiler and existing model tests**

Run:

```powershell
uv run pytest tests/test_text_cue_compiler.py tests/test_render_package_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit compiler wiring**

Run:

```powershell
git add pixelle_video/services/text_cue_compiler.py pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py tests/test_text_cue_compiler.py tests/test_render_package_models.py
git commit -m "feat: compile text overlay plans into render cues"
git log --oneline origin/dev..HEAD
```

Push only if the ahead list contains no unrelated commits.

---

### Task 4: TemplateTextCapabilities And HyperFrames Project Validation

**Files:**
- Create: `pixelle_video/models/template_text_capabilities.py`
- Add: `resources/hyperframes/templates/image_default/text_capabilities.json`
- Add: `resources/hyperframes/templates/image_life_insights_light/text_capabilities.json`
- Modify: `pixelle_video/services/hyperframes_project_service.py`
- Test: `tests/test_hyperframes_project_service.py`

- [ ] **Step 1: Write failing capabilities tests**

Add to `tests/test_hyperframes_project_service.py`:

```python
from pixelle_video.models.render_package import RenderManifest, TextCue, TextTrack
from pixelle_video.services.hyperframes_project_service import HyperFramesProjectService


def test_project_service_clamps_text_cues_to_manifest_duration(tmp_path):
    service = HyperFramesProjectService(output_dir=str(tmp_path))
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_duration=2.0,
        text_tracks=[TextTrack(id="track-1", kind="keyword", name="keyword", renderer_targets=("hyperframes",))],
        text_cues=[
            TextCue(id="cue-1", track_id="track-1", text="重点", start=1.0, end=4.0, role="keyword", slot="center")
        ],
    )

    paths = service.write_project_data(manifest, master_audio_duration=2.0)
    payload = paths.text_tracks_path.read_text(encoding="utf-8")

    assert '"end": 2.0' in payload


def test_project_service_rejects_unknown_text_slot(tmp_path):
    service = HyperFramesProjectService(output_dir=str(tmp_path))
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_duration=2.0,
        text_tracks=[TextTrack(id="track-1", kind="keyword", name="keyword", renderer_targets=("hyperframes",))],
        text_cues=[
            TextCue(id="cue-1", track_id="track-1", text="重点", start=0.0, end=1.0, role="keyword", slot="unknown")
        ],
    )

    with pytest.raises(ValueError, match="unsupported text slot"):
        service.write_project_data(manifest, master_audio_duration=2.0)
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
uv run pytest tests/test_hyperframes_project_service.py -q
```

Expected: FAIL because text cue normalization/capabilities are not implemented.

- [ ] **Step 3: Implement capabilities model**

Create `pixelle_video/models/template_text_capabilities.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TextSlotSpec:
    slot: str
    roles: tuple[str, ...]
    style_profiles: tuple[str, ...] = ()
    layer_min: int = 0
    layer_max: int = 99


@dataclass(frozen=True)
class TemplateTextCapabilities:
    template_id: str
    slots: tuple[TextSlotSpec, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TemplateTextCapabilities":
        return cls(
            template_id=str(data["template_id"]),
            slots=tuple(
                TextSlotSpec(
                    slot=str(item["slot"]),
                    roles=tuple(str(role) for role in item.get("roles", ())),
                    style_profiles=tuple(str(style) for style in item.get("style_profiles", ())),
                    layer_min=int(item.get("layer_min", 0)),
                    layer_max=int(item.get("layer_max", 99)),
                )
                for item in data.get("slots", ())
            ),
        )

    def validate(self, *, slot: str | None, role: str, style_profile: str | None, layer: int) -> None:
        effective_slot = slot or "center"
        matching = [item for item in self.slots if item.slot == effective_slot]
        if not matching:
            raise ValueError(f"unsupported text slot: {effective_slot}")
        spec = matching[0]
        if role not in spec.roles:
            raise ValueError(f"unsupported text role for slot {effective_slot}: {role}")
        if spec.style_profiles and style_profile and style_profile not in spec.style_profiles:
            raise ValueError(f"unsupported text style for slot {effective_slot}: {style_profile}")
        if layer < spec.layer_min or layer > spec.layer_max:
            raise ValueError(f"unsupported text layer for slot {effective_slot}: {layer}")
```

- [ ] **Step 4: Add template capability JSON files**

Create `resources/hyperframes/templates/image_default/text_capabilities.json`:

```json
{
  "template_id": "image_default",
  "slots": [
    {"slot": "center", "roles": ["keyword"], "style_profiles": ["image_default", "default"], "layer_min": 0, "layer_max": 20},
    {"slot": "lower_third", "roles": ["subtitle", "keyword"], "style_profiles": ["image_default", "default"], "layer_min": 0, "layer_max": 20}
  ]
}
```

Create `resources/hyperframes/templates/image_life_insights_light/text_capabilities.json` with the same roles and slots, replacing `image_default` with `image_life_insights_light`.

- [ ] **Step 5: Normalize and validate text cues in project service**

Modify `pixelle_video/services/hyperframes_project_service.py`:

```python
from pixelle_video.models.render_package import TextCue
from pixelle_video.models.template_text_capabilities import TemplateTextCapabilities
```

Add `_normalize_text_cues`:

```python
    def _normalize_text_cues(self, text_cues: list[TextCue], duration: float) -> list[TextCue]:
        normalized_cues: list[TextCue] = []
        for cue in text_cues:
            span = self._normalize_time_span(cue.start, cue.end, duration)
            if span is None:
                continue
            normalized_cues.append(replace(cue, start=span[0], end=span[1]))
        return normalized_cues
```

Add to `_normalize_manifest_timeline(...)` replace call:

```python
            text_cues=self._normalize_text_cues(manifest.text_cues, duration),
```

Add load/validate helpers:

```python
    def _load_text_capabilities(self, template_id: str) -> TemplateTextCapabilities | None:
        path = self.compiler.template_root / template_id / "text_capabilities.json"
        if not path.exists():
            return None
        return TemplateTextCapabilities.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _validate_text_capabilities(self, manifest: RenderManifest) -> None:
        capabilities = self._load_text_capabilities(manifest.template_id)
        if capabilities is None:
            if manifest.text_cues:
                raise ValueError(f"template {manifest.template_id} has no text capabilities")
            return
        tracks = {track.id: track for track in manifest.text_tracks if track.enabled}
        for cue in manifest.text_cues:
            track = tracks.get(cue.track_id)
            if track is None or "hyperframes" not in track.renderer_targets:
                continue
            capabilities.validate(
                slot=cue.slot,
                role=cue.role,
                style_profile=cue.style_profile or track.style_profile,
                layer=cue.layer,
            )
```

Call `_validate_text_capabilities(normalized_manifest)` in `_prepare_manifest_for_export(...)` after normalization.

- [ ] **Step 6: Verify project service tests pass**

Run:

```powershell
uv run pytest tests/test_hyperframes_project_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit capabilities**

Run:

```powershell
git add pixelle_video/models/template_text_capabilities.py pixelle_video/services/hyperframes_project_service.py resources/hyperframes/templates/image_default/text_capabilities.json resources/hyperframes/templates/image_life_insights_light/text_capabilities.json tests/test_hyperframes_project_service.py
git commit -m "feat: validate hyperframes text layer capabilities"
git log --oneline origin/dev..HEAD
```

Push only if the ahead list contains no unrelated commits.

---

### Task 5: HyperFrames Static Text Layer Rendering

**Files:**
- Modify: `pixelle_video/services/hyperframes_compiler.py`
- Modify: `resources/hyperframes/templates/image_default/index.template.html`
- Modify: `resources/hyperframes/templates/image_life_insights_light/index.template.html`
- Add: `resources/hyperframes/templates/image_default/compositions/text_layer.template.html`
- Add: `resources/hyperframes/templates/image_life_insights_light/compositions/text_layer.template.html`
- Test: `tests/test_hyperframes_compiler.py`

- [ ] **Step 1: Write failing compiler test**

Add to `tests/test_hyperframes_compiler.py`:

```python
from pixelle_video.models.render_package import TextCue, TextTrack


def test_compiler_emits_static_text_layer_without_fetch_and_escapes_text(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    (template_root / "image_default" / "compositions").mkdir(parents=True)
    (runtime_root / "vendor").mkdir(parents=True)
    (template_root / "image_default" / "index.template.html").write_text(
        '<div id="main">__VISUALS__<div data-composition-src="compositions/text_layer.html"></div></div>',
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "captions.template.html").write_text(
        '<div>__CAPTIONS__</div>',
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "text_layer.template.html").write_text(
        '<div id="text-layer">__TEXT_CUES__</div><script>__TEXT_TIMELINE__</script>',
        encoding="utf-8",
    )
    (runtime_root / "vendor" / "gsap.min.js").write_text("", encoding="utf-8")
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=3.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_tracks=[TextTrack(id="track-1", kind="keyword", name="keyword", renderer_targets=("hyperframes",))],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-1",
                text='<Pixelle & 字>',
                start=0.5,
                end=1.5,
                role="keyword",
                slot="center",
                layer=4,
            )
        ],
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    text_layer = (tmp_path / "project" / "compositions" / "text_layer.html").read_text(encoding="utf-8")
    assert "&lt;Pixelle &amp; 字&gt;" in text_layer
    assert 'data-start="0.5"' in text_layer
    assert 'data-duration="1.0"' in text_layer
    assert 'data-slot="center"' in text_layer
    assert "text_tracks.json" not in text_layer
```

- [ ] **Step 2: Verify test fails**

Run:

```powershell
uv run pytest tests/test_hyperframes_compiler.py::test_compiler_emits_static_text_layer_without_fetch_and_escapes_text -q
```

Expected: FAIL because `text_layer.template.html` is not read or written.

- [ ] **Step 3: Implement compiler text layer**

Modify `HyperFramesCompiler.compile(...)`:

```python
        text_layer_template_path = template_dir / "compositions" / "text_layer.template.html"
        text_layer_template = (
            text_layer_template_path.read_text(encoding="utf-8")
            if text_layer_template_path.exists()
            else '<div id="text-layer">__TEXT_CUES__</div><script>__TEXT_TIMELINE__</script>'
        )
```

Add replacements:

```python
            "__TEXT_CUES__": self._render_text_cues(context),
            "__TEXT_TIMELINE__": self._render_text_timeline(context),
```

Write output:

```python
        compiled_text_layer = self._replace_placeholders(text_layer_template, replacements)
        (project_dir / "compositions" / "text_layer.html").write_text(compiled_text_layer, encoding="utf-8")
```

Add methods:

```python
    def _render_text_cues(self, context: TemplateRenderContext) -> str:
        tracks = {track.id: track for track in context.text_tracks if track.enabled}
        rendered: list[str] = []
        for cue in context.text_cues:
            track = tracks.get(cue.track_id)
            if track is None or "hyperframes" not in track.renderer_targets:
                continue
            duration = max(float(cue.end) - float(cue.start), 0.1)
            rendered.append(
                (
                    f'<div id="{escape(cue.id, quote=True)}" '
                    f'class="clip text-cue text-cue--{escape(cue.role, quote=True)}" '
                    f'data-start="{cue.start}" data-duration="{duration}" '
                    f'data-track-id="{escape(cue.track_id, quote=True)}" '
                    f'data-role="{escape(cue.role, quote=True)}" '
                    f'data-slot="{escape(cue.slot or "center", quote=True)}" '
                    f'data-layer="{cue.layer}">'
                    f'<span class="text-cue__content">{escape(cue.text)}</span>'
                    "</div>"
                )
            )
        return "".join(rendered)

    def _render_text_timeline(self, context: TemplateRenderContext) -> str:
        return (
            'const textCues = Array.from(document.querySelectorAll(".text-cue"));\n'
            'const tl = gsap.timeline({ paused: true });\n'
            'textCues.forEach((cue) => {\n'
            '  const start = Number(cue.dataset.start || 0);\n'
            '  const duration = Number(cue.dataset.duration || 0.1);\n'
            '  tl.set(cue, { autoAlpha: 1 }, start);\n'
            '  tl.set(cue, { autoAlpha: 0 }, start + duration);\n'
            '});\n'
            'window.__timelines = window.__timelines || {};\n'
            'window.__timelines["text-layer"] = tl;'
        )
```

- [ ] **Step 4: Add text layer templates and main template composition mounts**

For both template directories, add `compositions/text_layer.template.html`:

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <script src="../runtime/vendor/gsap.min.js"></script>
  <style>
    html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; }
    #text-layer { position: relative; width: 100%; height: 100%; pointer-events: none; }
    .text-cue { position: absolute; left: 50%; top: 48%; transform: translate(-50%, -50%); opacity: 0; z-index: 10; }
    .text-cue[data-slot="lower_third"] { top: 78%; }
    .text-cue__content { display: inline-block; padding: 0.18em 0.42em; color: #fff; background: rgba(20,20,20,0.62); border-radius: 6px; font-weight: 700; }
  </style>
</head>
<body>
  <div id="text-layer">__TEXT_CUES__</div>
  <script>__TEXT_TIMELINE__</script>
</body>
</html>
```

Add a text layer composition mount to each `index.template.html` near the captions composition:

```html
<div
  id="text-layer-composition"
  class="composition-layer text-layer-composition"
  data-composition-src="compositions/text_layer.html"
  data-track-index="3">
</div>
```

- [ ] **Step 5: Verify compiler tests pass**

Run:

```powershell
uv run pytest tests/test_hyperframes_compiler.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit HyperFrames renderer**

Run:

```powershell
git add pixelle_video/services/hyperframes_compiler.py resources/hyperframes/templates/image_default/index.template.html resources/hyperframes/templates/image_life_insights_light/index.template.html resources/hyperframes/templates/image_default/compositions/text_layer.template.html resources/hyperframes/templates/image_life_insights_light/compositions/text_layer.template.html tests/test_hyperframes_compiler.py
git commit -m "feat: render text cues in compiled hyperframes templates"
git log --oneline origin/dev..HEAD
```

Push only if the ahead list contains no unrelated commits.

---

### Task 6: ASS Exporter And Video Burn-In

**Files:**
- Create: `pixelle_video/services/ass_text_adapter.py`
- Modify: `pixelle_video/services/video.py`
- Test: `tests/test_ass_text_adapter.py`
- Test: `tests/test_video_service.py`

- [ ] **Step 1: Write failing ASS exporter tests**

Create `tests/test_ass_text_adapter.py`:

```python
from pixelle_video.models.render_package import RenderManifest, TextCue, TextTrack
from pixelle_video.services.ass_text_adapter import AssTextAdapter


def test_ass_adapter_exports_master_and_split_files(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="legacy",
        text_tracks=[
            TextTrack(id="subtitle", kind="subtitle", name="subtitle", renderer_targets=("ass",)),
            TextTrack(id="overlay", kind="keyword", name="overlay", renderer_targets=("ass",)),
        ],
        text_cues=[
            TextCue(id="s1", track_id="subtitle", text="第一句{测试}", start=0.0, end=1.0, role="subtitle"),
            TextCue(id="k1", track_id="overlay", text="重点,词", start=0.5, end=1.5, role="keyword", slot="center"),
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)

    assert outputs.master.name == "master.ass"
    assert outputs.subtitle_only.name == "subtitle_only.ass"
    assert outputs.overlay_only.name == "overlay_only.ass"
    assert r"\{测试\}" in outputs.master.read_text(encoding="utf-8")
    assert "重点，词" in outputs.overlay_only.read_text(encoding="utf-8")
```

- [ ] **Step 2: Write failing burn-in tests**

Add to `tests/test_video_service.py`:

```python
from pathlib import Path
import pytest

from pixelle_video.services.video import VideoService


def test_burn_ass_subtitles_rejects_same_input_and_output(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    ass = tmp_path / "master.ass"
    ass.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="same path"):
        VideoService().burn_ass_subtitles(str(video), str(ass), str(video))


def test_escape_ffmpeg_filter_path_handles_windows_drive_and_spaces():
    escaped = VideoService()._escape_ffmpeg_filter_path(r"C:\测试 路径\master.ass")

    assert r"C\\:" in escaped
    assert r"测试 路径" in escaped
    assert r"master.ass" in escaped
```

- [ ] **Step 3: Verify tests fail**

Run:

```powershell
uv run pytest tests/test_ass_text_adapter.py tests/test_video_service.py -q
```

Expected: FAIL because adapter and burn-in methods do not exist.

- [ ] **Step 4: Implement ASS adapter**

Create `pixelle_video/services/ass_text_adapter.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pixelle_video.models.render_package import RenderManifest, TextCue


@dataclass(frozen=True)
class AssExportOutputs:
    master: Path
    subtitle_only: Path
    overlay_only: Path


class AssTextAdapter:
    def export(self, *, manifest: RenderManifest, output_dir: str | Path) -> AssExportOutputs:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        tracks = {track.id: track for track in manifest.text_tracks if track.enabled and "ass" in track.renderer_targets}
        cues = [cue for cue in manifest.text_cues if cue.track_id in tracks]

        master = target / "master.ass"
        subtitle_only = target / "subtitle_only.ass"
        overlay_only = target / "overlay_only.ass"
        master.write_text(self._render_ass(cues), encoding="utf-8")
        subtitle_only.write_text(self._render_ass([cue for cue in cues if cue.role == "subtitle"]), encoding="utf-8")
        overlay_only.write_text(self._render_ass([cue for cue in cues if cue.role != "subtitle"]), encoding="utf-8")
        return AssExportOutputs(master=master, subtitle_only=subtitle_only, overlay_only=overlay_only)

    def _render_ass(self, cues: list[TextCue]) -> str:
        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "ScaledBorderAndShadow: yes",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,Noto Sans CJK SC,64,&H00FFFFFF,&H80000000,&H40000000,1,0,1,2,0,2,80,80,140,1",
            "Style: Overlay,Noto Sans CJK SC,76,&H00FFFFFF,&H80000000,&H40000000,1,0,1,2,0,5,80,80,80,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
        for cue in cues:
            style = "Default" if cue.role == "subtitle" else "Overlay"
            lines.append(
                f"Dialogue: {cue.layer},{self._format_time(cue.start)},{self._format_time(cue.end)},{style},,0,0,0,,{self._escape_text(cue.text)}"
            )
        return "\n".join(lines) + "\n"

    def _format_time(self, value: float) -> str:
        total_centiseconds = max(0, int(round(float(value) * 100)))
        hours, remainder = divmod(total_centiseconds, 360000)
        minutes, remainder = divmod(remainder, 6000)
        seconds, centiseconds = divmod(remainder, 100)
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    def _escape_text(self, text: str) -> str:
        return (text or "").replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace(",", "，").replace("\n", r"\N")
```

- [ ] **Step 5: Implement burn-in service**

Modify `pixelle_video/services/video.py`:

```python
    def burn_ass_subtitles(self, input_video: str, ass_file: str, output: str) -> str:
        input_path = Path(input_video).resolve()
        output_path = Path(output).resolve()
        if input_path == output_path:
            raise ValueError("input_video and output cannot be the same path")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        escaped_ass = self._escape_ffmpeg_filter_path(ass_file)
        try:
            (
                ffmpeg
                .input(str(input_path))
                .output(str(output_path), vf=f"subtitles='{escaped_ass}'", c_a="copy")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            return str(output_path)
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
            raise RuntimeError(f"Failed to burn ASS subtitles: {error_msg}")

    def _escape_ffmpeg_filter_path(self, value: str) -> str:
        path = Path(value).resolve().as_posix()
        return (
            path.replace("\\", r"\\")
            .replace(":", r"\\:")
            .replace("'", r"\\'")
            .replace(",", r"\\,")
            .replace("[", r"\\[")
            .replace("]", r"\\]")
        )
```

- [ ] **Step 6: Verify ASS tests pass**

Run:

```powershell
uv run pytest tests/test_ass_text_adapter.py tests/test_video_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit ASS foundation**

Run:

```powershell
git add pixelle_video/services/ass_text_adapter.py pixelle_video/services/video.py tests/test_ass_text_adapter.py tests/test_video_service.py
git commit -m "feat: add ASS text export and burn-in"
git log --oneline origin/dev..HEAD
```

Push only if the ahead list contains no unrelated commits.

---

### Task 7: StandardPipeline Renderer Integration And Metadata Summary

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_standard_pipeline_hyperframes_mode.py`
- Test: `tests/test_standard_pipeline_staged_mode.py`

- [ ] **Step 1: Write failing HyperFrames integration test**

Add to `tests/test_standard_pipeline_hyperframes_mode.py`:

```python
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan


@pytest.mark.asyncio
async def test_hyperframes_manifest_receives_compiled_text_cues(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")
    ctx.creation_package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="重点词",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("hyperframes",),
                    source={"frame_index": 0, "sentence_id": "sentence-1"},
                ),
            )
        ),
    )

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        frame.composed_image_path = str(tmp_path / f"{frame.index:02d}_shell.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")
        Path(frame.composed_image_path).write_text("shell", encoding="utf-8")

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda audio_path: 2.0)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert manifest.text_tracks
    assert manifest.text_cues[0].text == "重点词"
    assert manifest.text_cues[0].source["candidate_id"] == "candidate-1"
    assert manifest.text_cues[0].start == pytest.approx(0.1)
```

- [ ] **Step 2: Write failing legacy burn-in order test**

Add to `tests/test_standard_pipeline_staged_mode.py`:

```python
from pathlib import Path

from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.render_package import SentenceUnit
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan


@pytest.mark.asyncio
async def test_legacy_post_production_burns_ass_before_user_output_copy(monkeypatch, tmp_path):
    calls = []

    class _VideoService:
        def concat_videos(self, videos, output, **kwargs):
            calls.append(("concat", output))
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"concat")
            return output

        def burn_ass_subtitles(self, input_video, ass_file, output):
            calls.append(("burn", input_video, ass_file, output))
            Path(output).write_bytes(b"burned")
            return output

    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _VideoService)

    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_storyboard_ctx()
    ctx.task_id = "task-1"
    ctx.task_dir = str(tmp_path / "task-1")
    Path(ctx.task_dir).mkdir(parents=True, exist_ok=True)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")
    ctx.params["output_path"] = str(tmp_path / "deliverables" / "final.mp4")
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
    ctx.storyboard.frames[1].video_segment_path = "segment-1.mp4"
    ctx.timing_plan = SimpleNamespace(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="scene 1",
                frame_indices=[0],
                source_start=0.0,
                source_end=1.0,
            )
        ]
    )
    ctx.creation_package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="重点词",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("ass",),
                    source={"frame_index": 0, "sentence_id": "sentence-1"},
                ),
            )
        ),
    )

    await pipeline.post_production(ctx)

    assert [item[0] for item in calls] == ["concat", "burn"]
    assert Path(ctx.params["output_path"]).read_bytes() == b"burned"
    assert ctx.final_video_path == ctx.params["output_path"]
```

- [ ] **Step 3: Verify tests fail**

Run:

```powershell
uv run pytest tests/test_standard_pipeline_hyperframes_mode.py tests/test_standard_pipeline_staged_mode.py -q
```

Expected: FAIL because StandardPipeline does not yet compile text cues into renderers.

- [ ] **Step 4: Add helper methods to StandardPipeline**

Modify `pixelle_video/pipelines/standard.py`:

```python
    def _compile_text_layer_for_render(self, ctx: PipelineContext):
        if ctx.creation_package is None or ctx.timing_plan is None:
            return [], []
        return TextCueCompiler().compile(
            package=ctx.creation_package,
            sentence_units=list(ctx.timing_plan.sentences),
        )

    def _record_text_layer_summary(self, ctx: PipelineContext, *, renderer: str, text_tracks, text_cues, native_hint_count: int = 0) -> None:
        summary = {
            "enabled": bool(text_tracks or text_cues or native_hint_count),
            "renderer": renderer,
            "track_count": len(text_tracks),
            "cue_count": len(text_cues),
            "native_prompt_hint_count": native_hint_count,
            "targets": sorted({target for track in text_tracks for target in track.renderer_targets}),
        }
        ctx.observability["text_layer_summary"] = summary
```

- [ ] **Step 5: Wire HyperFrames manifest**

In `_post_production_hyperframes`, before `RenderManifest(...)`:

```python
        text_tracks, text_cues = self._compile_text_layer_for_render(ctx)
```

Pass to manifest:

```python
            text_tracks=text_tracks,
            text_cues=text_cues,
```

After project write:

```python
        self._record_text_layer_summary(
            ctx,
            renderer="hyperframes",
            text_tracks=text_tracks,
            text_cues=text_cues,
        )
```

- [ ] **Step 6: Wire legacy ASS burn-in**

In legacy `post_production`, after `concat_videos(...)` and before user output copy:

```python
        text_tracks, text_cues = self._compile_text_layer_for_render(ctx)
        if text_cues:
            ass_dir = Path(ctx.task_dir) / "text_layer"
            manifest = RenderManifest(
                task_id=ctx.task_id,
                title=storyboard.title,
                width=storyboard.config.media_width,
                height=storyboard.config.media_height,
                fps=storyboard.config.video_fps,
                template_id="legacy",
                text_tracks=text_tracks,
                text_cues=text_cues,
            )
            ass_outputs = AssTextAdapter().export(manifest=manifest, output_dir=ass_dir)
            burned_path = str(Path(final_video_path).with_name("final_text_burned.mp4"))
            final_video_path = video_service.burn_ass_subtitles(
                final_video_path,
                str(ass_outputs.master),
                burned_path,
            )
```

Record summary after optional burn:

```python
        self._record_text_layer_summary(
            ctx,
            renderer="ass" if text_cues else "disabled",
            text_tracks=text_tracks,
            text_cues=text_cues,
        )
```

Add import:

```python
from pixelle_video.services.ass_text_adapter import AssTextAdapter
```

- [ ] **Step 7: Persist summary under result metadata**

In `_persist_task_data`, add inside `"result"`:

```python
                    "text_layer_summary": ctx.observability.get("text_layer_summary"),
```

- [ ] **Step 8: Verify integration tests pass**

Run:

```powershell
uv run pytest tests/test_standard_pipeline_hyperframes_mode.py tests/test_standard_pipeline_staged_mode.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit pipeline integration**

Run:

```powershell
git add pixelle_video/pipelines/standard.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_standard_pipeline_staged_mode.py
git commit -m "feat: integrate text layer renderers in standard pipeline"
git log --oneline origin/dev..HEAD
```

Push only if the ahead list contains no unrelated commits.

---

### Task 8: History UI Summary And Final Verification

**Files:**
- Modify: `web/pages/2_📚_History.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Test: existing UI and metadata tests where applicable.

- [ ] **Step 1: Add text layer summary display**

In `web/pages/2_📚_History.py`, in the detail view after render backend display:

```python
        text_layer_summary = metadata.get("result", {}).get("text_layer_summary") or {}
        if text_layer_summary:
            st.markdown(f"**{tr('history.detail.text_layer')}**")
            st.markdown(
                tr(
                    "history.detail.text_layer_summary",
                    renderer=text_layer_summary.get("renderer", "N/A"),
                    cue_count=text_layer_summary.get("cue_count", 0),
                    native_count=text_layer_summary.get("native_prompt_hint_count", 0),
                )
            )
```

- [ ] **Step 2: Add i18n strings**

Add to `web/i18n/locales/zh_CN.json`:

```json
"history.detail.text_layer": "文字层",
"history.detail.text_layer_summary": "渲染器：{renderer}；Cue 数量：{cue_count}；原生提示：{native_count}"
```

Add to `web/i18n/locales/en_US.json`:

```json
"history.detail.text_layer": "Text layer",
"history.detail.text_layer_summary": "Renderer: {renderer}; cues: {cue_count}; native hints: {native_count}"
```

- [ ] **Step 3: Run focused tests**

Run:

```powershell
uv run pytest tests/test_task_log_persistence.py tests/test_render_backend_ui.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full verification**

Run:

```powershell
uv run ruff check pixelle_video tests web
uv run pytest -q
```

Expected: Ruff all checks passed, pytest all passed.

- [ ] **Step 5: Commit UI and verification**

Run:

```powershell
git add "web/pages/2_📚_History.py" web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json
git commit -m "feat: show text layer summary in history"
git log --oneline origin/dev..HEAD
```

Push only if the ahead list contains no unrelated commits.

---

## Self-Review

- Spec coverage: 阶段 1 由 Tasks 1-3 覆盖；阶段 2 由 Tasks 4-5 覆盖；阶段 3 由 Tasks 6-7 覆盖；阶段 4 由 Task 2 和 Task 7 摘要覆盖；阶段 5 由 Task 8 和最终 verification 覆盖。
- Red flag scan: 本计划没有 `TBD`、`TODO`、`implement later`，也没有要求执行者自行补齐的测试占位块。
- Type consistency: `TextOverlayPlan`、`CreationPackage`、`TextTrack`、`TextCue`、`RenderManifest` 使用阶段 0 已存在模型；新增 `NativePromptHint`、`TemplateTextCapabilities`、`AssExportOutputs` 均在本计划中定义。
- Known risk: 当前 `dev` 有非本次任务的 ahead commit 时，不能按仓库默认规则推送本任务提交，因为会一起推送无关提交。执行者必须在每次 commit 后检查 ahead 列表并报告 push 阻塞。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-24-text-layer-full-feature-implementation.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration. Because `AGENTS.md` forbids worktrees, subagents must either do read-only review or edit disjoint files in the shared workspace under main-session coordination.
2. **Inline Execution** - execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.
