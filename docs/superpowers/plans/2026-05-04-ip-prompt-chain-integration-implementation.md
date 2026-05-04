# IP Prompt Chain Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 IP 设计与 SceneCast 资产能力真正接入图片提示词主链路，让长文案生成图片时可以基于高级分镜、风格提示词、IP 使用策略、中文画面文字和 Z-Image 约束产出稳定可执行的最终 prompt。

**Architecture:** 保留现有 `AssetBible / SceneCast / IP Design Workbench / IP Workbench apply` 作为资产编辑与手工绑定能力，不重做 UI 基座。新增一条面向图片生成主链路的结构化 IP 使用规划层：`StoryboardPlan -> IP Usage Planner -> ImagePromptComposer prompt_context -> image_generation prompt -> Prompt Composer / helper finalization`。IP 不直接拼接到 `final_prompt`，而是先生成结构化帧级上下文，再由 LLM 和本地 helper 协同重写为最终 Z-Image prompt。

**Tech Stack:** Python dataclasses, existing PromptContext contract, StandardPipeline, FastAPI/Pydantic request contracts, Streamlit UI payload wiring, pytest, ruff.

---

## Scope Guard

这份计划只解决“IP 如何进入图片提示词生成主链路”。

明确不做：

- 不重做现有 `IP Design Workbench`
- 不重做现有 `IP Workbench apply`
- 不扩展图生图、LoRA、参考图管理
- 不在这一轮做复杂聊天式 IP 创作 UI
- 不做新的独立存储后端或数据库迁移

这轮的完成标准是：

1. 用户在当前生成流程里可以显式启用一个 IP 资产。
2. 标准视频图片 prompt 生成时，IP 能按帧裁决是否出现以及如何出现。
3. 最终 prompt 能融合高级分镜、风格提示词、中文画面文字和 Z-Image 单段输出约束。
4. 色号、字段名、JSON、英文参数不会泄漏到最终 Z-Image prompt。

## Current State Summary

当前仓库已经具备这些基础：

- `pixelle_video/models/asset_bible.py`
  - 已有 `IPProfile / CharacterProfile / SceneAsset / PropAsset / StyleProfile / AssetBible`
- `pixelle_video/models/scene_cast.py`
  - 已有按 `storyboard_plan_id + frame_id` 绑定资产的 `SceneCast`
- `web/pages/3_IP_Design_Workbench.py`
  - 已有独立 IP 设计页面
- `web/components/ip_workbench_panel.py`
  - 已有 Storyboard Workbench 中的手工 apply 面板
- `pixelle_video/services/asset_prompt_plan_apply.py`
  - 已有将 `SceneCast` 应用回 `PromptPlan` 的保存链路
- `pixelle_video/services/image_prompt_composer.py`
  - 已负责从 `StoryboardPlan` 构造 `PromptContextEnvelope`
- `pixelle_video/utils/content_generators.py`
  - 已负责 style resolution、storyboard planning、base prompt 生成和最终 prompt 组装
- `pixelle_video/prompts/image_generation.py`
  - 已支持 `prompt_contexts` 结构化输入

当前关键缺口：

- `IPProfile` 还只是轻量 profile，缺少“固定身份 / 可变槽位 / 色彩结构 / 中文画面文字白名单 / 负向约束”的主链路结构。
- `PromptContextEnvelope` 还没有承载 IP 使用规划结果。
- `generate_styled_image_prompt_batch(...)` 还没有 “IP Usage Planner -> Prompt Composer 重写” 这一层。
- `build_image_prompt_prompt(...)` 没有明确告诉 LLM 如何选择 `ip_presence_type`、如何生成 `summary_text / scene_text`。
- Z-Image 不支持独立 negative prompt 时，还没有把 IP 约束和文字约束合并成单段最终 prompt 的正式规则。
- 标准生成入口还没有“选择 IP / 是否启用 IP / 自动融合”这组最小控制项。

## File Structure

- Create: `pixelle_video/models/ip_prompt_planning.py`
  - 新的主链路模型：`IPIdentityAnchor`、`IPColorToken`、`IPImageTextPlan`、`IPFrameAdaptationPackage`、`IPPresenceType`
- Create: `pixelle_video/services/ip_usage_planner.py`
  - 按帧生成 IP 使用规划，不直接依赖 UI
- Modify: `pixelle_video/models/asset_bible.py`
  - 扩展 `IPProfile`，让它承载主链路所需的结构化字段
- Modify: `pixelle_video/models/prompt_context.py`
  - 支持更丰富的帧级规划上下文
- Modify: `pixelle_video/services/image_prompt_composer.py`
  - 在 `_build_prompt_contexts(...)` 中注入 IP 使用规划结果
- Modify: `pixelle_video/utils/content_generators.py`
  - 调用 `IPUsagePlanner`，并在 final prompt 组装阶段应用 Z-Image/IP 规则
- Modify: `pixelle_video/utils/prompt_helper.py`
  - 新增“单段最终 prompt 合并”和“禁止色号/字段名泄漏”的 helper
- Modify: `pixelle_video/prompts/image_generation.py`
  - 扩展 LLM 提示模板，明确 IP 规划、中文画面文字和 Z-Image 输出规则
- Modify: `pixelle_video/models/prompt_plan.py`
  - 为 `PromptPlan.metadata` 或 `prompt_sections` 增加 IP 规划摘要，保证可追踪
- Modify: `pixelle_video/services/prompt_plan_service.py`
  - 把 IP 规划摘要写入 `PromptPlanBundle`
- Modify: `pixelle_video/models/video_generation_contract.py`
  - 增加最小 IP 主链路请求参数
- Modify: `api/schemas/video.py`
  - 暴露标准生成 API 的 IP 入口参数
- Modify: `api/routers/video.py`
  - 把 IP 参数写入 `video_params`
- Modify: `pixelle_video/pipelines/standard.py`
  - 在 `plan_visuals(...)` 调用 `ImagePromptComposer.compose(...)` 时传入 IP 控制信息
- Modify: `web/components/style_config.py`
  - 增加最小 IP 选择与启用控制
- Modify: `web/components/output_preview.py`
  - 保持参数透传与 storyboard snapshot 一致
- Tests:
  - Create `tests/test_ip_prompt_planning_models.py`
  - Create `tests/test_ip_usage_planner.py`
  - Modify `tests/test_asset_bible_models.py`
  - Modify `tests/test_prompt_context_contract.py`
  - Modify `tests/test_image_prompt_composer.py`
  - Modify `tests/test_styled_image_prompt_batch.py`
  - Modify `tests/test_content_generators_text_policy.py`
  - Modify `tests/test_video_api.py`
  - Modify `tests/test_standard_pipeline_storyboard_generation.py`
  - Create `tests/test_style_config_ip_controls.py`

## Task 1: IP 主链路数据模型

**Files:**
- Create: `pixelle_video/models/ip_prompt_planning.py`
- Modify: `pixelle_video/models/asset_bible.py`
- Test: `tests/test_ip_prompt_planning_models.py`
- Test: `tests/test_asset_bible_models.py`

- [ ] **Step 1: 写失败测试，锁定主链路数据结构**

创建 `tests/test_ip_prompt_planning_models.py`，覆盖：

```python
from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPImageTextPlan,
    IPPresenceType,
)


def test_ip_frame_adaptation_package_serializes_presence_text_and_color_terms():
    package = IPFrameAdaptationPackage(
        frame_id="frame_0001",
        ip_presence_type=IPPresenceType.SCENE_INTEGRATED,
        presence_mode="support",
        semantic_reason="opening establishing frame should keep the gate as the primary subject",
        identity_anchors_visible=("white rabbit silhouette", "blue tie"),
        identity_color_terms=("纯白色身体", "鲜明宝蓝色领带"),
        image_text_plan=IPImageTextPlan(
            summary_text="从长乐门出发",
            scene_text=("长乐门", "正定古城"),
            visible_text_whitelist=("从长乐门出发", "长乐门", "正定古城"),
        ),
        negative_constraints=("避免角色贴纸感", "避免多余文字"),
    )

    payload = package.to_dict()

    assert payload["ip_presence_type"] == "scene_integrated"
    assert payload["image_text_plan"]["summary_text"] == "从长乐门出发"
    assert "#5A2A12" not in str(payload)
```

补充 `tests/test_asset_bible_models.py`，覆盖：

```python
def test_ip_profile_supports_identity_locks_color_tokens_and_text_rules():
    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子", "长耳朵", "圆润脸型"),
        identity_anchors=("蓝色领带", "浅粉色耳朵内侧"),
        variable_slots=("动作", "表情", "服装", "道具", "站位"),
        semantic_boundary=("不能替代历史建筑", "不能替代宗教人物"),
        negative_constraints=("避免贴纸感", "避免多余文字"),
        color_palette={
            "body": {"hex": "#FFFFFF", "prompt": "纯白色身体"},
            "tie": {"hex": "#006BFF", "prompt": "鲜明宝蓝色领带"},
        },
        image_text_palette={
            "title": {"hex": "#5A2A12", "prompt": "深棕色墨迹"},
        },
        visible_text_whitelist=("长乐门", "正定古城"),
    )

    restored = IPProfile.from_dict(profile.to_dict())

    assert restored.identity_lock == ("白色卡通兔子", "长耳朵", "圆润脸型")
    assert restored.variable_slots == ("动作", "表情", "服装", "道具", "站位")
    assert restored.color_palette["tie"]["prompt"] == "鲜明宝蓝色领带"
    assert restored.visible_text_whitelist == ("长乐门", "正定古城")
```

- [ ] **Step 2: 运行测试，确认 RED**

运行：

```powershell
python -m pytest -q tests/test_ip_prompt_planning_models.py tests/test_asset_bible_models.py
```

预期：失败，因为新模型和扩展字段尚不存在。

- [ ] **Step 3: 实现最小模型**

在 `pixelle_video/models/ip_prompt_planning.py` 中实现：

- `IPPresenceType(str, Enum)`
  - `strong_identity`
  - `balanced_narrative`
  - `scene_integrated`
  - `low_intrusion`
  - `symbolic_only`
  - `absent`
- `IPImageTextPlan`
  - `summary_text`
  - `scene_text`
  - `visible_text_whitelist`
  - `text_safety_rules`
- `IPFrameAdaptationPackage`
  - `frame_id`
  - `ip_presence_type`
  - `presence_mode`
  - `semantic_reason`
  - `must_not_replace`
  - `identity_anchors_visible`
  - `identity_anchors_suppressed`
  - `identity_color_terms`
  - `outfit_theme`
  - `outfit_condition`
  - `accessories`
  - `action`
  - `expression`
  - `pose`
  - `camera_relationship`
  - `depth_layer`
  - `interaction_target`
  - `continuity_from_previous`
  - `shot_fit_notes`
  - `image_text_plan`
  - `prompt_weight`
  - `negative_constraints`

扩展 `pixelle_video/models/asset_bible.py` 中 `IPProfile`：

- 增加固定身份与主链路字段：
  - `identity_lock`
  - `identity_anchors`
  - `identity_suppression_rules`
  - `variable_slots`
  - `semantic_boundary`
  - `negative_constraints`
  - `color_palette`
  - `image_text_palette`
  - `visible_text_whitelist`

要求：

- 继续保持 dataclass/frozen 风格
- 保持 `to_dict / from_dict`
- 不把色号直接混进最终 prompt 字段；色号只允许存在于结构化 palette

- [ ] **Step 4: 再跑测试，确认 GREEN**

运行：

```powershell
python -m pytest -q tests/test_ip_prompt_planning_models.py tests/test_asset_bible_models.py
```

预期：通过。

- [ ] **Step 5: 提交并推送**

```powershell
git add -- pixelle_video/models/ip_prompt_planning.py pixelle_video/models/asset_bible.py tests/test_ip_prompt_planning_models.py tests/test_asset_bible_models.py
git commit -m "feat: 增加IP提示词主链路数据模型"
git push origin $(git branch --show-current)
```

## Task 2: IP Usage Planner 按帧裁决

**Files:**
- Create: `pixelle_video/services/ip_usage_planner.py`
- Modify: `pixelle_video/models/prompt_context.py`
- Test: `tests/test_ip_usage_planner.py`
- Test: `tests/test_prompt_context_contract.py`

- [ ] **Step 1: 写失败测试，固定裁决规则**

创建 `tests/test_ip_usage_planner.py`：

```python
from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.ip_prompt_planning import IPPresenceType
from pixelle_video.services.ip_usage_planner import IPUsagePlanner


def _profile():
    return IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子", "长耳朵"),
        identity_anchors=("蓝色领带",),
        variable_slots=("动作", "表情", "服装", "道具", "站位"),
        semantic_boundary=("不能替代历史建筑", "不能替代宗教人物"),
        color_palette={"tie": {"hex": "#006BFF", "prompt": "鲜明宝蓝色领带"}},
    )


def _plan(frame):
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=frame.source_text,
        frames=[frame],
    )


def test_usage_planner_marks_establishing_frame_as_scene_integrated_by_default():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="从长乐门出发，这是正定的南大门。",
        visual_goal="表现正定长乐门作为古城入口的历史感和出发感",
        prompt_intent="建立古城空间和旅程开篇",
        shot_type="中远景",
        shot_purpose="建立场景",
        primary_subject="正定长乐门、青砖城墙",
        world_elements=("青砖城墙", "城楼", "晨光"),
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    assert package.ip_presence_type is IPPresenceType.SCENE_INTEGRATED
    assert package.presence_mode in {"support", "ambient"}
    assert "长乐门" in package.must_not_replace


def test_usage_planner_marks_historical_subject_as_low_intrusion_or_absent():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="古寺中讲述佛祖故事，香火与壁画静静铺开。",
        visual_goal="表现古寺宗教叙事的庄重感",
        prompt_intent="严肃历史宗教场景",
        shot_type="全景",
        shot_purpose="历史说明",
        primary_subject="佛祖故事与古寺壁画",
        world_elements=("古寺", "香火", "壁画"),
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    assert package.ip_presence_type in {
        IPPresenceType.LOW_INTRUSION,
        IPPresenceType.SYMBOLIC_ONLY,
        IPPresenceType.ABSENT,
    }
    assert "不能替代" in " ".join(package.negative_constraints)


def test_usage_planner_generates_summary_and_scene_text_plan():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="从长乐门出发，走进正定古城的七处印记。",
        visual_goal="表现第一站与旅行手账感",
        prompt_intent="文旅开篇",
        primary_subject="长乐门",
        world_elements=("地图", "手账", "古城路线"),
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    assert package.image_text_plan.summary_text in {"从长乐门出发", "正定古城"}
    assert "长乐门" in package.image_text_plan.visible_text_whitelist
```

扩展 `tests/test_prompt_context_contract.py`：

```python
def test_prompt_context_payload_can_carry_ip_adaptation_package():
    envelope = PromptContextEnvelope(
        plan_context={"plan_source_text": "从长乐门出发。"},
        frame_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "ip_adaptation": {
                    "ip_presence_type": "scene_integrated",
                    "presence_mode": "support",
                },
                "ip_presence_options": ["scene_integrated", "low_intrusion", "absent"],
                "style_context": {"style_kind": "visual_only"},
            }
        ],
    )

    payload = envelope.to_prompt_payload()

    assert payload["prompt_contexts"][0]["ip_adaptation"]["ip_presence_type"] == "scene_integrated"
    assert "low_intrusion" in payload["prompt_contexts"][0]["ip_presence_options"]
    assert payload["prompt_contexts"][0]["style_context"]["style_kind"] == "visual_only"
```

- [ ] **Step 2: 运行测试，确认 RED**

运行：

```powershell
python -m pytest -q tests/test_ip_usage_planner.py tests/test_prompt_context_contract.py
```

预期：失败，因为 planner 和新上下文字段尚不存在。

- [ ] **Step 3: 实现 IPUsagePlanner**

在 `pixelle_video/services/ip_usage_planner.py` 中实现：

- `IPUsagePlanner.plan_frame(...) -> IPFrameAdaptationPackage`
- `IPUsagePlanner.plan_batch(...) -> list[IPFrameAdaptationPackage]`

输入至少包含：

- `ip_profile`
- `storyboard_plan.frames`
- `resolved_style` 或标准化 style context
- 可选 `scene_casts_by_frame`

规则最少包括：

- 开篇建立场景：
  - 默认 `scene_integrated` 或 `low_intrusion`
- 讲解/叙事帧：
  - 默认 `balanced_narrative`
- 强品牌/IP 主画面：
  - `strong_identity`
- 历史主体、宗教主体、真实人物主体、严肃纪实：
  - 优先 `low_intrusion` / `symbolic_only` / `absent`
- 纯风景空镜：
  - `absent` 或 `symbolic_only`

`prompt_context.py` 不改 schema 风格，只保证 envelope 可以承载这些字段进入 LLM prompt payload。

- [ ] **Step 4: 运行测试，确认 GREEN**

运行：

```powershell
python -m pytest -q tests/test_ip_usage_planner.py tests/test_prompt_context_contract.py
```

预期：通过。

- [ ] **Step 5: 提交并推送**

```powershell
git add -- pixelle_video/services/ip_usage_planner.py pixelle_video/models/prompt_context.py tests/test_ip_usage_planner.py tests/test_prompt_context_contract.py
git commit -m "feat: 增加IP按帧使用规划器"
git push origin $(git branch --show-current)
```

## Task 3: 把 IP 规划注入 ImagePromptComposer 与 PromptPlan

**Files:**
- Modify: `pixelle_video/services/image_prompt_composer.py`
- Modify: `pixelle_video/models/prompt_plan.py`
- Modify: `pixelle_video/services/prompt_plan_service.py`
- Test: `tests/test_image_prompt_composer.py`
- Test: `tests/test_prompt_plan_model.py`

- [ ] **Step 1: 写失败测试，锁定 composer 注入行为**

扩展 `tests/test_image_prompt_composer.py`：

```python
@pytest.mark.asyncio
async def test_composer_injects_ip_adaptation_into_prompt_contexts(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one", "prompt two"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": {},
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=_plan(),
        image_config={},
        ip_enabled=True,
        ip_profile=_ip_profile(),
    )

    frame_context = captured["prompt_contexts"].frame_contexts[0]
    assert frame_context["ip_adaptation"]["ip_presence_type"] in {
        "scene_integrated",
        "balanced_narrative",
        "low_intrusion",
    }
    assert "ip_presence_options" in frame_context


@pytest.mark.asyncio
async def test_composer_keeps_prompt_count_contract_when_ip_enabled(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**_kwargs):
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": {},
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="image prompt count must match storyboard frame count"):
        await ImagePromptComposer().compose(
            llm_service=object(),
            storyboard_plan=_plan(),
            image_config={},
            ip_enabled=True,
            ip_profile=_ip_profile(),
        )
```

扩展 `tests/test_prompt_plan_model.py`：

```python
def test_prompt_plan_can_store_ip_planning_metadata_without_polluting_projection():
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"generated_prompt": "正定古城画面"},
        final_prompt="正定古城画面，白色兔子自然站在城墙边。",
        metadata={
            "ip_presence_type": "scene_integrated",
            "image_text_plan": {
                "summary_text": "从长乐门出发",
                "visible_text_whitelist": ["从长乐门出发", "长乐门"],
            },
        },
    )

    projection = PromptProjection.from_prompt_plan(plan)

    assert plan.to_dict()["metadata"]["ip_presence_type"] == "scene_integrated"
    assert "image_text_plan" in plan.to_dict()["metadata"]
    assert "image_text_plan" not in projection.to_dict()
    assert "ip_adaptation" not in projection.to_dict()
```

- [ ] **Step 2: 运行测试，确认 RED**

运行：

```powershell
python -m pytest -q tests/test_image_prompt_composer.py tests/test_prompt_plan_model.py
```

预期：失败，因为 composer 还未接入 IP planner。

- [ ] **Step 3: 实现 composer 注入**

修改 `pixelle_video/services/image_prompt_composer.py`：

- `compose(...)` 新增可选参数：
  - `ip_profile`
  - `scene_casts_by_frame`
  - `ip_enabled`
- 在 `_build_prompt_contexts(...)` 前调用 `IPUsagePlanner.plan_batch(...)`
- 每帧 `frame_context` 增加：
  - `ip_adaptation`
  - `ip_presence_options`
  - `style_context`

修改 `pixelle_video/services/prompt_plan_service.py`：

- 将 IP 规划摘要写入：
  - `PromptPlan.metadata["ip_presence_type"]`
  - `PromptPlan.metadata["image_text_plan"]`
  - `PromptPlan.metadata["visible_text_whitelist"]`

要求：

- `PromptProjection` 仍保持轻量，不把完整结构化大对象暴露为投影主字段
- `PromptPlan.metadata` 中只存摘要，不存冗余整份 profile

- [ ] **Step 4: 运行测试，确认 GREEN**

运行：

```powershell
python -m pytest -q tests/test_image_prompt_composer.py tests/test_prompt_plan_model.py
```

预期：通过。

- [ ] **Step 5: 提交并推送**

```powershell
git add -- pixelle_video/services/image_prompt_composer.py pixelle_video/models/prompt_plan.py pixelle_video/services/prompt_plan_service.py tests/test_image_prompt_composer.py tests/test_prompt_plan_model.py
git commit -m "feat: 将IP规划注入提示词编排链路"
git push origin $(git branch --show-current)
```

## Task 4: 扩展 image_generation prompt，让 LLM 理解 IP 规划

**Files:**
- Modify: `pixelle_video/prompts/image_generation.py`
- Test: `tests/test_prompt_context_contract.py`
- Test: `tests/test_content_generators_structured_output.py`

- [ ] **Step 1: 写失败测试，锁定 prompt 文本要求**

扩展 `tests/test_prompt_context_contract.py`：

```python
def test_image_prompt_template_mentions_ip_adaptation_and_text_whitelist():
    prompt = build_image_prompt_prompt(
        narrations=["从长乐门出发。"],
        min_words=30,
        max_words=60,
        prompt_contexts=PromptContextEnvelope(
            plan_context={"plan_source_text": "从长乐门出发。"},
            frame_contexts=[
                {
                    "frame_source_text": "从长乐门出发。",
                    "ip_adaptation": {
                        "ip_presence_type": "scene_integrated",
                        "image_text_plan": {
                            "summary_text": "从长乐门出发",
                            "visible_text_whitelist": ["从长乐门出发", "长乐门"],
                        },
                    },
                }
            ],
        ),
        prompt_language="zh_CN",
    )

    assert "ip_adaptation" in prompt
    assert "summary_text" in prompt
    assert "scene_text" in prompt
    assert "visible_text_whitelist" in prompt
    assert "do not output field names" in prompt.lower() or "字段名" in prompt
```

扩展 `tests/test_content_generators_structured_output.py`：

```python
def test_image_prompt_generation_prompt_keeps_json_output_but_teaches_ip_rules():
    prompt = build_image_prompt_prompt(
        narrations=["从长乐门出发。"],
        min_words=30,
        max_words=60,
        prompt_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "ip_adaptation": {"ip_presence_type": "scene_integrated"},
            }
        ],
        prompt_language="zh_CN",
    )

    assert '"image_prompts"' in prompt
    assert "list[str]" not in prompt
    assert "Only output JSON" in prompt
    assert "ip_presence_type" in prompt
```

- [ ] **Step 2: 运行测试，确认 RED**

运行：

```powershell
python -m pytest -q tests/test_prompt_context_contract.py tests/test_content_generators_structured_output.py
```

预期：失败，因为模板尚未包含 IP 规则。

- [ ] **Step 3: 更新 prompt 模板**

修改 `pixelle_video/prompts/image_generation.py`：

- 在 `Frame-Aware Context Contract` 中增加：
  - `ip_adaptation` 是本帧 IP 规划真值来源
  - `ip_presence_type` 决定 IP 是否强出场、弱出场、符号化或不出场
  - `summary_text / scene_text / visible_text_whitelist` 决定允许出现的中文文字
- 在 `Output Requirements` 中增加：
  - 最终输出仍然是 `image_prompts: list[str]`
  - 每条字符串必须是纯视觉描述
  - 不得输出 JSON 字段名、色号、参数名、英文控制词说明
  - 若需要负向约束，要写成自然语言画面要求

- [ ] **Step 4: 运行测试，确认 GREEN**

运行：

```powershell
python -m pytest -q tests/test_prompt_context_contract.py tests/test_content_generators_structured_output.py
```

预期：通过。

- [ ] **Step 5: 提交并推送**

```powershell
git add -- pixelle_video/prompts/image_generation.py tests/test_prompt_context_contract.py tests/test_content_generators_structured_output.py
git commit -m "feat: 扩展图片提示词模板的IP规划约束"
git push origin $(git branch --show-current)
```

## Task 5: 改造最终 prompt 组装，满足 Z-Image 规则

**Files:**
- Modify: `pixelle_video/utils/prompt_helper.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Test: `tests/test_styled_image_prompt_batch.py`
- Test: `tests/test_content_generators_text_policy.py`

- [ ] **Step 1: 写失败测试，锁定 Z-Image 单段 prompt 规则**

扩展 `tests/test_styled_image_prompt_batch.py`：

```python
@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_merges_ip_negative_constraints_into_single_prompt_when_negative_prompt_unsupported(monkeypatch):
    async def fake_generate_image_prompts(**_kwargs):
        return ["正定长乐门晨光画面，白色兔子站在城墙边。"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": False})(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["从长乐门出发。"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        prompt_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "ip_adaptation": {
                    "ip_presence_type": "scene_integrated",
                    "negative_constraints": ["避免多余文字", "避免角色贴纸感"],
                },
            }
        ],
    )

    assert result.negative_prompt is None
    assert "避免多余文字" in result.prompts[0]
    assert "避免角色贴纸感" in result.prompts[0]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_never_leaks_hex_codes_or_field_names(monkeypatch):
    async def fake_generate_image_prompts(**_kwargs):
        return ["summary_text: 从长乐门出发，title_hex: #5A2A12，白色兔子。"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["从长乐门出发。"],
        image_config={},
        prompt_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "ip_adaptation": {
                    "identity_color_terms": ["纯白色身体", "鲜明宝蓝色领带"],
                    "image_text_plan": {
                        "summary_text": "从长乐门出发",
                        "visible_text_whitelist": ["从长乐门出发"],
                    },
                },
            }
        ],
    )

    assert "#5A2A12" not in result.prompts[0]
    assert "summary_text" not in result.prompts[0]
    assert "title_hex" not in result.prompts[0]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_uses_visible_text_whitelist_for_native_text(monkeypatch):
    async def fake_generate_image_prompts(**_kwargs):
        return ["长乐门城墙，白色兔子手持旅行手账。"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["从长乐门出发。"],
        image_config={},
        prompt_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "ip_adaptation": {
                    "image_text_plan": {
                        "summary_text": "从长乐门出发",
                        "scene_text": ["长乐门"],
                        "visible_text_whitelist": ["从长乐门出发", "长乐门"],
                    },
                },
            }
        ],
    )

    assert "从长乐门出发" in result.prompts[0]
    assert "长乐门" in result.prompts[0]
    assert "白名单" in result.prompts[0] or "only" in result.prompts[0].lower()
```

扩展 `tests/test_content_generators_text_policy.py`：

```python
def test_text_policy_prefers_whitelist_language_over_generic_no_text_when_ip_text_plan_enabled():
    clause = build_visible_text_whitelist_clause(["从长乐门出发", "长乐门"])

    assert "从长乐门出发" in clause
    assert "长乐门" in clause
    assert "no visible text" not in clause
```

- [ ] **Step 2: 运行测试，确认 RED**

运行：

```powershell
python -m pytest -q tests/test_styled_image_prompt_batch.py tests/test_content_generators_text_policy.py
```

预期：失败，因为现有 helper 还不知道 IP 文字/色彩规则。

- [ ] **Step 3: 实现 helper 与 content_generators 改造**

修改 `pixelle_video/utils/prompt_helper.py`：

- 增加 helper：
  - `sanitize_visual_prompt_text(...)`
  - `merge_z_image_constraints_into_prompt(...)`
  - `build_visible_text_whitelist_clause(...)`
- 规则：
  - 移除 `#RRGGBB`
  - 移除字段名样式片段：`summary_text:`、`scene_text:`、`title_hex:`、`ip_presence_type:`
  - 当 workflow 不支持 negative prompt 时，把 IP 和文字约束并入单段 prompt

修改 `pixelle_video/utils/content_generators.py`：

- 在 `generate_styled_image_prompt_batch(...)` 中读取 `ip_adaptation`
- 当 `native_text_allowed` 且存在 `image_text_plan` 时：
  - 不再走通用 `apply_no_text_policy`
  - 改为注入 whitelist 型中文文字约束
- 当 workflow `supports_negative_prompt=False` 时：
  - 把 `negative_constraints`、文字白名单规则、风格负向约束合并进最终 prompt

- [ ] **Step 4: 运行测试，确认 GREEN**

运行：

```powershell
python -m pytest -q tests/test_styled_image_prompt_batch.py tests/test_content_generators_text_policy.py
```

预期：通过。

- [ ] **Step 5: 提交并推送**

```powershell
git add -- pixelle_video/utils/prompt_helper.py pixelle_video/utils/content_generators.py tests/test_styled_image_prompt_batch.py tests/test_content_generators_text_policy.py
git commit -m "feat: 完善Z-Image的IP提示词融合规则"
git push origin $(git branch --show-current)
```

## Task 6: 把 IP 控制接入标准生成请求和流水线

**Files:**
- Modify: `pixelle_video/models/video_generation_contract.py`
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_video_api.py`
- Test: `tests/test_standard_pipeline_storyboard_generation.py`

- [ ] **Step 1: 写失败测试，锁定 API/流水线入口**

扩展 `tests/test_video_api.py`：

```python
def test_video_generate_request_accepts_ip_prompt_chain_controls():
    request = VideoGenerateRequest(
        text="demo",
        ip_asset_bible_id="bible_demo",
        ip_profile_id="ip_main",
        ip_enabled=True,
    )
    assert request.ip_enabled is True


def test_build_video_generation_params_copies_ip_prompt_chain_controls():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            ip_enabled=True,
            ip_asset_bible_id="bible_demo",
            ip_profile_id="ip_main",
        ),
        request_id="req_test",
    )

    assert params["ip_enabled"] is True
    assert params["ip_asset_bible_id"] == "bible_demo"
    assert params["ip_profile_id"] == "ip_main"
```

扩展 `tests/test_standard_pipeline_storyboard_generation.py`：

```python
@pytest.mark.asyncio
async def test_plan_visuals_passes_ip_controls_to_image_prompt_composer(monkeypatch):
    captured = {}

    async def fake_compose(self, **kwargs):
        captured.update(kwargs)
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="从长乐门出发。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-1"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(_DummyCore()).plan_visuals(ctx)

    assert captured["ip_enabled"] is True
    assert captured["ip_profile"].ip_profile_id == "ip_main"
```

- [ ] **Step 2: 运行测试，确认 RED**

运行：

```powershell
python -m pytest -q tests/test_video_api.py tests/test_standard_pipeline_storyboard_generation.py
```

预期：失败，因为 API 和流水线还没有 IP 参数。

- [ ] **Step 3: 实现最小请求契约**

在 `pixelle_video/models/video_generation_contract.py`、`api/schemas/video.py`、`api/routers/video.py` 中增加：

- `ip_enabled: bool = False`
- `ip_asset_bible_id: str | None`
- `ip_profile_id: str | None`

要求：

- 只接受 public resource id 形态
- 当 `ip_enabled=True` 且缺少必要 id 时，给出清晰 `422`

修改 `pixelle_video/pipelines/standard.py`：

- 在 `plan_visuals(...)` 前解析并加载：
  - `AssetBible`
  - `IPProfile`
  - 可选 `SceneCast`
- 调用 `ImagePromptComposer.compose(...)` 时透传：
  - `ip_enabled`
  - `ip_profile`
  - `scene_casts_by_frame`

- [ ] **Step 4: 运行测试，确认 GREEN**

运行：

```powershell
python -m pytest -q tests/test_video_api.py tests/test_standard_pipeline_storyboard_generation.py
```

预期：通过。

- [ ] **Step 5: 提交并推送**

```powershell
git add -- pixelle_video/models/video_generation_contract.py api/schemas/video.py api/routers/video.py pixelle_video/pipelines/standard.py tests/test_video_api.py tests/test_standard_pipeline_storyboard_generation.py
git commit -m "feat: 接入标准生成链路的IP控制参数"
git push origin $(git branch --show-current)
```

## Task 7: 前端最小入口接入

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/components/output_preview.py`
- Test: `tests/test_style_config_ip_controls.py`

- [ ] **Step 1: 写失败测试，锁定最小 UI 能力**

创建 `tests/test_style_config_ip_controls.py`：

```python
def test_style_config_renders_ip_enable_toggle_and_profile_selectors():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_ip_enabled"] = True
    fake_ui.session_state["style_ip_asset_bible_id"] = "bible_demo"
    fake_ui.session_state["style_ip_profile_id"] = "ip_main"

    payload = render_ip_prompt_chain_controls(
        ui=fake_ui,
        asset_bibles=[
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [{"ip_profile_id": "ip_main", "name": "正定向导兔"}],
            }
        ],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {
        "ip_enabled": True,
        "ip_asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
    }


def test_style_config_hides_ip_selectors_when_disabled():
    fake_ui = _FakeStyleConfigUI()

    payload = render_ip_prompt_chain_controls(
        ui=fake_ui,
        asset_bibles=[],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {"ip_enabled": False}
```

- [ ] **Step 2: 运行测试，确认 RED**

运行：

```powershell
python -m pytest -q tests/test_style_config_ip_controls.py
```

预期：失败，因为 UI 还没有 IP 控件。

- [ ] **Step 3: 实现最小控制项**

修改 `web/components/style_config.py`：

- 在风格/提示词相关区域增加一个简洁 section：
  - `启用 IP`
  - `AssetBible`
  - `IP Profile`
- 数据来源优先复用已有 `IPDesignClient` / `StoryboardIPWorkbenchClient` 的 list 能力，避免 UI 直接碰 HTTP helper
- 默认关闭，不改变现有用户流程

修改 `web/components/output_preview.py`：

- 保证生成时把 `ip_enabled / ip_asset_bible_id / ip_profile_id` 透传到 `video_params`

- [ ] **Step 4: 运行测试，确认 GREEN**

运行：

```powershell
python -m pytest -q tests/test_style_config_ip_controls.py
```

预期：通过。

- [ ] **Step 5: 提交并推送**

```powershell
git add -- web/components/style_config.py web/components/output_preview.py tests/test_style_config_ip_controls.py
git commit -m "feat: 增加标准生成流程的IP入口"
git push origin $(git branch --show-current)
```

## Task 8: 全链路回归

**Files:**
- No new files
- Verification only

- [ ] **Step 1: 跑后端主链路测试**

运行：

```powershell
python -m pytest -q tests/test_ip_prompt_planning_models.py tests/test_ip_usage_planner.py tests/test_asset_bible_models.py tests/test_prompt_context_contract.py tests/test_image_prompt_composer.py tests/test_prompt_plan_model.py tests/test_content_generators_structured_output.py tests/test_styled_image_prompt_batch.py tests/test_content_generators_text_policy.py tests/test_video_api.py tests/test_standard_pipeline_storyboard_generation.py tests/test_style_config_ip_controls.py
```

预期：全部通过。

- [ ] **Step 2: 跑现有 IP/UI 回归**

运行：

```powershell
python -m pytest -q tests/test_ip_design_client.py tests/test_ip_design_workbench_ui.py tests/test_ip_workbench_client.py tests/test_ip_workbench_panel_ui.py
```

预期：全部通过，证明没有破坏现有资产编辑和 apply 流程。

- [ ] **Step 3: 跑格式与差异检查**

运行：

```powershell
ruff check pixelle_video api web tests
git diff --check
```

预期：退出码 0。

- [ ] **Step 4: 收口状态检查**

```powershell
git status --short
```

预期：只剩本计划任务产生的已提交改动，或工作区干净。

如果回归中为了修复问题产生了新改动，必须只暂存相关文件并使用独立提交：

```powershell
git add -- <exact file paths changed by the regression fix>
git commit -m "fix: 修复IP提示词主链路回归问题"
git push origin $(git branch --show-current)
```

如果工作区混有本任务之外改动，必须按 AGENTS.md 做原子隔离，不得使用 `git add --all`。

## Self-Review Checklist

- 资产编辑能力：Task 1, Task 7
- 按帧 IP 使用规划：Task 2
- PromptContext 注入：Task 3
- LLM 提示模板扩展：Task 4
- Z-Image 最终 prompt 安全规则：Task 5
- API / StandardPipeline 参数透传：Task 6
- 前端最小入口：Task 7
- 全链路回归：Task 8

## Execution Notes

- 每个任务都先 RED 再 GREEN，再提交。
- 不要并行修改同一组核心文件：
  - `content_generators.py`
  - `prompt_helper.py`
  - `image_prompt_composer.py`
  - `video.py` / `standard.py`
- 如果执行时工作区仍有无关暂存改动，先做暂存隔离，再按任务原子提交。
