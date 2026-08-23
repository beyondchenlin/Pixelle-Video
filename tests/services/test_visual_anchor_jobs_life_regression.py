from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.storyboard import StoryboardConfig, StoryboardFrame
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_anchor_two_stage import (
    ContentStageModelOutput,
    ContentStageOutput,
    FusionStageOutput,
    ImageWorkflowExecutionContract,
    PreflightReviewOutput,
    TargetVisualStyle,
    VisibleTextPolicy,
    VisualAnchorIdentityProfile,
)
from pixelle_video.prompt_language import CHINESE_PROMPT_LANGUAGE
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.visual_anchor_two_stage_service import (
    VisualAnchorTwoStageError,
    VisualAnchorTwoStageService,
    _contains_required_prompt_fragment_contract,
    _materialize_content_stage_output,
)
from pixelle_video.services.visual_prompt_composer import (
    VisualPromptComposer,
    _positive_only_avoidance_fragments,
    _resolve_visual_anchor_style_batch,
    _target_visual_style_contract,
    _visible_text_policy,
)

_STYLE_POSITIVE = [
    "极简线稿",
    "二维表达",
    "单色或严格受控配色",
    "大面积留白",
    "简洁轮廓",
    "细微情绪",
    "禁止摄影写实",
    "禁止三维渲染",
    "禁止复杂彩色背景",
]
_STYLE_NEGATIVE = ["摄影写实", "三维渲染", "复杂彩色背景"]
_NO_TEXT_POSITIVE = "画面中禁止出现任何可见文字、标题、水印或乱码"
_NO_TEXT_NEGATIVE = "文字，水印，标题，乱码"


class _QueuedLLM:
    def __init__(self, responses):
        self.responses = {
            response_type: list(values)
            for response_type, values in responses.items()
        }
        self.calls = []

    async def __call__(self, *, prompt, response_type, **kwargs):
        self.calls.append(
            {
                "prompt": prompt,
                "response_type": response_type,
                "kwargs": kwargs,
            }
        )
        return self.responses[response_type].pop(0)


def _jobs_plan() -> StoryboardPlan:
    source_texts = (
        "乔布斯和沃兹尼亚克在车库组装苹果一号电脑，开启苹果公司的技术道路。",
        "乔布斯在发布会上展示麦金塔电脑，产品与图形界面成为关键技术事件。",
        "乔布斯回到苹果，带领团队推出iMac、iPod和iPhone，产品节点沿一条道路串联。",
        "一名年轻人站在起跑线上，望向由苹果产品和关键事件延伸出的未来道路。",
    )
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=" ".join(source_texts),
        frames=[
            StoryboardPlanFrame(
                index=index,
                frame_id=f"jobs-{index}",
                source_text=source_text,
                visual_goal=f"表达乔布斯人生第{index}段",
                prompt_intent=f"第{index}段人生画面",
            )
            for index, source_text in enumerate(source_texts, start=1)
        ],
    )


def _content_outputs(plan: StoryboardPlan) -> list[ContentStageModelOutput]:
    subject_specs = (
        (
            "乔布斯和沃兹尼亚克",
            "乔布斯和沃兹尼亚克",
            2,
            "共同组装苹果一号电脑",
            "苹果一号电脑",
            "苹果一号电脑",
            "被两位创始人组装",
        ),
        (
            "乔布斯",
            "乔布斯",
            1,
            "在发布会上展示电脑",
            "麦金塔电脑",
            "麦金塔电脑",
            "被乔布斯展示",
        ),
        (
            "乔布斯和苹果团队",
            "乔布斯回到苹果，带领团队",
            1,
            "推出多代苹果产品",
            "iMac、iPod和iPhone",
            "iMac、iPod和iPhone",
            "作为道路上的关键产品节点",
        ),
        (
            "年轻人",
            "一名年轻人",
            1,
            "站在起跑线上望向未来",
            "苹果产品和关键事件形成的未来道路",
            "苹果产品和关键事件",
            "从起跑线前方延伸",
        ),
    )
    pure_prompts = (
        "乔布斯和沃兹尼亚克在车库工作台组装苹果一号电脑，苹果公司的技术道路由此开启。",
        "乔布斯在发布会上展示麦金塔电脑，产品与图形界面成为清晰相连的关键技术事件。",
        "乔布斯和苹果团队推出iMac、iPod和iPhone，产品节点沿一条道路串联。",
        "年轻人站在起跑线上，苹果产品和关键事件形成的未来道路向前延伸。",
    )
    event_specs = (
        (
            "开启苹果公司的技术道路",
            "苹果公司的技术道路",
            "spatial_relation",
        ),
        (
            "产品与图形界面成为关键技术事件",
            "产品与图形界面成为清晰相连的关键技术事件",
            "event",
        ),
        (
            "产品节点沿一条道路串联",
            "产品节点沿一条道路串联",
            "spatial_relation",
        ),
        (
            "站在起跑线上",
            "站在起跑线上",
            "spatial_relation",
        ),
    )
    outputs = []
    for _frame, spec, pure_prompt, event_spec in zip(
        plan.frames,
        subject_specs,
        pure_prompts,
        event_specs,
    ):
        (
            primary_name,
            primary_source,
            primary_quantity,
            primary_action,
            secondary_name,
            secondary_source,
            secondary_action,
        ) = spec
        event_source, event_prompt, event_category = event_spec
        outputs.append(
            ContentStageModelOutput(
                core_claim=pure_prompt,
                primary_subject={
                    "category": "person",
                    "name": primary_name,
                    "identity": "分镜原文中的真正叙事人物",
                    "quantity": primary_quantity,
                    "action": primary_action,
                    "source_evidence": primary_source,
                    "pure_content_prompt_evidence": primary_name,
                    "protected_facts": [
                        {
                            "category": "person",
                            "statement": primary_source,
                            "source_evidence": primary_source,
                            "pure_content_prompt_evidence": primary_name,
                        }
                    ],
                },
                secondary_subjects=[
                    {
                        "category": "product",
                        "name": secondary_name,
                        "identity": "分镜原文中的产品、技术或道路系统",
                        "quantity": 1,
                        "action": secondary_action,
                        "source_evidence": secondary_source,
                        "pure_content_prompt_evidence": secondary_name,
                        "protected_facts": [
                            {
                                "category": "product",
                                "statement": secondary_source,
                                "source_evidence": secondary_source,
                                "pure_content_prompt_evidence": secondary_name,
                            }
                        ],
                    }
                ],
                scene_facts=[
                    {
                        "category": event_category,
                        "statement": event_source,
                        "source_evidence": event_source,
                        "pure_content_prompt_evidence": event_prompt,
                    }
                ],
                adjustable_non_core_content=["非核心环境道具", "辅助光影层次"],
                pure_content_prompt=pure_prompt,
                self_check="pass",
                self_check_failures=[],
            )
        )
    return outputs


def test_selected_minimal_emotion_style_maps_to_complete_final_contract():
    batch = _resolve_visual_anchor_style_batch(
        image_config={
            "prompt_prefix_library": {
                "active_prefix_id": "builtin_line_art_emotion_minimal",
                "items": [
                    {
                        "id": "builtin_line_art_emotion_minimal",
                        "name": "Minimal Emotion Line Art",
                        "content": (
                            "minimal line art, elegant contour drawing, lots of "
                            "negative space, subtle emotional tone, clean "
                            "monochrome illustration"
                        ),
                        "style_category_id": "minimal_line_art",
                        "scene_category_id": "emotional_copywriting",
                        "note": "Simple symbolic visuals for reflective topics.",
                    }
                ],
            }
        },
        prompt_prefix=None,
        frame_count=4,
    )

    contract = _target_visual_style_contract(
        batch=batch,
        visual_profile_snapshot=None,
        prompt_language=CHINESE_PROMPT_LANGUAGE,
    )

    assert contract.required_final_prompt_fragments == _STYLE_POSITIVE
    assert contract.required_negative_prompt_fragments == _STYLE_NEGATIVE


def test_z_image_style_contract_moves_avoidance_rules_into_positive_prompt():
    batch = _resolve_visual_anchor_style_batch(
        image_config={
            "prompt_prefix_library": {
                "active_prefix_id": "builtin_line_art_emotion_minimal",
                "items": [
                    {
                        "id": "builtin_line_art_emotion_minimal",
                        "name": "Minimal Emotion Line Art",
                        "content": (
                            "minimal line art, elegant contour drawing, lots of "
                            "negative space, subtle emotional tone, clean "
                            "monochrome illustration"
                        ),
                        "style_category_id": "minimal_line_art",
                        "scene_category_id": "emotional_copywriting",
                    }
                ],
            }
        },
        prompt_prefix=None,
        frame_count=1,
    )

    contract = _target_visual_style_contract(
        batch=batch,
        visual_profile_snapshot=None,
        prompt_language=CHINESE_PROMPT_LANGUAGE,
        negative_prompt_supported=False,
    )

    assert contract.required_final_prompt_fragments == _STYLE_POSITIVE
    assert contract.required_negative_prompt_fragments == []


def test_z_image_converts_custom_negative_style_rules_to_explicit_positive_avoidance():
    assert _positive_only_avoidance_fragments(
        positive_fragments=["克制的水墨插画"],
        negative_fragments=["低质量", "禁止模糊"],
        prompt_language=CHINESE_PROMPT_LANGUAGE,
    ) == ["禁止出现低质量", "禁止模糊"]


def test_fusion_template_allows_required_style_and_text_prohibitions():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_fusion_stage.md"
    ).read_text(encoding="utf-8")

    assert '“必须”“禁止”' not in template
    assert "明确要求的“禁止”类画面约束属于最终提示词内容，必须逐字保留" in template


def test_content_template_requires_exact_shortest_prompt_evidence():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_content_stage.md"
    ).read_text(encoding="utf-8")

    assert "先完成 pure_content_prompt，再填写所有 pure_content_prompt_evidence" in template
    assert "主体证据优先只复制 pure_content_prompt 中的主体名称" in template
    assert "甲的证据应为“甲”" in template


def test_fusion_template_requires_exact_single_instance_and_trait_evidence():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_fusion_stage.md"
    ).read_text(encoding="utf-8")

    assert "必须先完成 final_positive_prompt" in template
    assert "required_single_instance_prompt_fragment" in template
    assert "不能写不存在的“一只斑点狗”" in template
    assert "protected_facts[].pure_content_prompt_evidence 原样放入" in template
    assert "不要先改写事实再尝试回填一个不存在的证据句" in template
    assert "不可翻译、不可改写的字面量" in template
    assert "例如片段是英文时必须保留英文" in template


def test_preflight_template_keeps_primary_subject_and_visual_anchor_roles_distinct():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_preflight_review.md"
    ).read_text(encoding="utf-8")

    assert "允许共存且职责不同的两个主体" in template
    assert "不得拿来与 primary_subject 的身份或外观比较" in template
    assert "不得仅因视觉锚点也被具体描述，就推断它替代了主要主体" in template
    assert "系列视觉锚点出现在严肃题材中不自动构成戏谑" in template
    assert "作为唯一外部主体加入画面" in template
    assert "未被原文提及" in template
    assert "均不得记为失败项" in template


def test_disabled_image_text_maps_to_title_watermark_and_garbled_text_guards():
    policy = _visible_text_policy(
        {"image_text": {"suppress_embedded_text": True}},
        prompt_language=CHINESE_PROMPT_LANGUAGE,
    )

    assert policy.suppress_visible_text is True
    assert policy.required_positive_prompt_fragment == _NO_TEXT_POSITIVE
    assert policy.required_negative_prompt_fragment == _NO_TEXT_NEGATIVE


def test_visible_text_negative_contract_accepts_equivalent_list_punctuation():
    assert _contains_required_prompt_fragment_contract(
        "摄影写实, 文字, 水印, 标题, 乱码",
        _NO_TEXT_NEGATIVE,
    )
    assert not _contains_required_prompt_fragment_contract(
        "摄影写实, 文字, 水印, 标题",
        _NO_TEXT_NEGATIVE,
    )


def _fusion_outputs(
    contents: list[ContentStageOutput],
) -> list[FusionStageOutput]:
    style_positive = "，".join(_STYLE_POSITIVE)
    outputs = []
    for content in contents:
        fact_checks = [
            {
                "fact_id": fact.fact_id,
                "preserved": True,
                "final_image_evidence": fact.pure_content_prompt_evidence,
            }
            for fact in content.protected_facts
        ]
        positive = (
            f"{content.pure_content_prompt} {style_positive}。"
            "画面中只有一只斑点狗，斑点狗特征与黑色墨镜清晰可辨，"
            "它根据当前叙事自然融入空间，不继承主要人物的动作或职责，"
            "并服从整张图的透视、光照、材质和空间关系。"
            f"{_NO_TEXT_POSITIVE}。"
        )
        outputs.append(
            FusionStageOutput(
                selected_fusion_method="让视觉锚点根据当前内容关系自然参与",
                unselected_candidate_summaries=[
                    {
                        "manifestation": "墙面徽记",
                        "audit_summary": "没有采用非实体装饰表现",
                    }
                ],
                content_stage_deviations=[],
                non_core_reconstruction_summary=["重组非核心道具以保持空间自然"],
                protected_fact_checks=fact_checks,
                primary_subject_preserved=True,
                primary_subject_final_prompt_evidence=(
                    content.primary_subject.pure_content_prompt_evidence
                ),
                visual_anchor_replaces_primary_subject=False,
                identity_trait_checks=[
                    {
                        "trait": "斑点狗",
                        "preserved": True,
                        "final_prompt_evidence": "斑点狗",
                    },
                    {
                        "trait": "黑色墨镜",
                        "preserved": True,
                        "final_prompt_evidence": "黑色墨镜",
                    },
                ],
                final_manifestation="服从当前场景关系的斑点狗单一实体",
                target_visual_anchor_instance_count=1,
                other_scene_elements_inherit_identity_features=False,
                single_instance_prompt_evidence="画面中只有一只斑点狗",
                spatial_contact_and_lighting_relation=(
                    "根据当前画面的透视、光照、材质、支撑和遮挡关系自然融合"
                ),
                inherited_existing_fusion_decision=False,
                continuity_change_reason="独立镜头没有既有融合决定",
                final_positive_prompt=positive,
                final_negative_prompt="",
                self_check="pass",
                self_check_failures=[],
            )
        )
    return outputs


def _identity() -> VisualAnchorIdentityProfile:
    return VisualAnchorIdentityProfile(
        profile_id="dog-anchor",
        display_name="斑点狗",
        core_identity_traits=["斑点狗", "黑色墨镜"],
        supporting_identity_traits=["温和神态"],
        forbidden_traits=["变成人类", "继承主要人物身份"],
        source_asset_ids=[],
        identity_content_sha256="b" * 64,
        identity_resource_version="identity:dog-anchor:" + "b" * 64,
    )


def _style() -> TargetVisualStyle:
    return TargetVisualStyle(
        description="极简线稿／情感文案",
        required_final_prompt_fragments=list(_STYLE_POSITIVE),
        required_negative_prompt_fragments=list(_STYLE_NEGATIVE),
    )


def _text_policy() -> VisibleTextPolicy:
    return VisibleTextPolicy(
        suppress_visible_text=True,
        required_positive_prompt_fragment=_NO_TEXT_POSITIVE,
        required_negative_prompt_fragment=_NO_TEXT_NEGATIVE,
    )


def _execution() -> ImageWorkflowExecutionContract:
    return ImageWorkflowExecutionContract(
        width=768,
        height=768,
        model_files=[
            "Qwen3-4B-Q8_0.gguf",
            "ae.safetensors",
            "z-image-turbo-Q8_0.gguf",
        ],
        steps=5,
        cfg=1.0,
        sampler_name="euler",
        scheduler="simple",
        denoise=1.0,
    )


async def _run_jobs_sample():
    plan = _jobs_plan()
    model_contents = _content_outputs(plan)
    contents = [
        _materialize_content_stage_output(
            frame_id=frame.frame_id,
            model_output=model_output,
        )
        for frame, model_output in zip(plan.frames, model_contents)
    ]
    fusions = _fusion_outputs(contents)
    reviews = [
        PreflightReviewOutput(
            decision="pass",
            failures=[],
            allowed_final_positive_prompt=fusion.final_positive_prompt,
            allowed_final_negative_prompt="",
        )
        for fusion in fusions
    ]
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: model_contents,
            FusionStageOutput: fusions,
            PreflightReviewOutput: reviews,
        }
    )
    result = await VisualAnchorTwoStageService().run_batch(
        llm_service=llm,
        storyboard_plan=plan,
        identity_profile=_identity(),
        identity_reference_condition=None,
        identity_conditioning_mode="text_profile",
        workflow_identity_condition_summary=(
            "默认Z-Image文生图工作流仅使用文字身份档案，不注入参考图"
        ),
        target_visual_style=_style(),
        visible_text_policy=_text_policy(),
        target_image_prompt_language="中文",
        task_id="task-jobs-life",
        workflow_key="selfhost/image_z_image_turbo_gguf.json",
        workflow_version_sha256="c" * 64,
        expected_execution=_execution(),
        random_seeds_by_frame={
            frame.frame_id: 100 + index
            for index, frame in enumerate(plan.frames, start=1)
        },
        negative_prompt_supported=False,
    )
    return plan, result, llm


@pytest.mark.asyncio
async def test_jobs_life_two_stage_contract_preserves_subjects_style_and_text_policy():
    plan, result, llm = await _run_jobs_sample()

    assert len(llm.calls) == len(plan.frames) * 3
    content_calls = [
        call
        for call in llm.calls
        if call["response_type"] is ContentStageModelOutput
    ]
    fusion_calls = [
        call for call in llm.calls if call["response_type"] is FusionStageOutput
    ]
    assert len(content_calls) == len(fusion_calls) == len(plan.frames)
    for call in content_calls:
        assert "斑点狗" not in call["prompt"]
        assert "黑色墨镜" not in call["prompt"]
        assert "identity_profile" not in call["prompt"]
    for call in fusion_calls:
        assert '"content_stage_output"' in call["prompt"]
        assert '"identity_profile"' in call["prompt"]
        assert '"continuous_scene_context"' in call["prompt"]
        assert '"target_visual_style"' in call["prompt"]
        assert '"identity_conditioning_mode": "text_profile"' in call["prompt"]
        assert '"negative_prompt_supported": false' in call["prompt"]

    expected_primary_subjects = (
        "乔布斯和沃兹尼亚克",
        "乔布斯",
        "乔布斯和苹果团队",
        "年轻人",
    )
    for frame_result, expected_primary in zip(
        result.frames,
        expected_primary_subjects,
    ):
        content = frame_result.content_stage_output
        request = frame_result.generation_request
        assert content.primary_subject.name == expected_primary
        assert content.protected_facts
        assert "表达乔布斯人生第" not in content.primary_subject.name
        assert request.primary_subject_name == expected_primary
        assert request.primary_subject_preserved is True
        assert request.visual_anchor_replaces_primary_subject is False
        assert expected_primary in request.final_positive_prompt
        assert request.identity_conditioning_mode == "text_profile"
        assert request.identity_reference_condition is None
        assert request.target_visual_anchor_instance_count == 1
        assert "画面中只有一只斑点狗" in request.final_positive_prompt
        assert _NO_TEXT_POSITIVE in request.final_positive_prompt
        assert request.final_negative_prompt == ""
        for fragment in _STYLE_POSITIVE:
            assert fragment in request.final_positive_prompt
        for forbidden_fixed_rule in (
            "大尺寸",
            "居中",
            "前景",
            "固定位置",
            "画面占比",
            "左上角",
            "右下角",
        ):
            assert forbidden_fixed_rule not in request.final_positive_prompt
        assert frame_result.preflight_review_output.decision == "pass"

    composer_source = inspect.getsource(VisualPromptComposer.compose)
    assert "base_image_prompt" not in composer_source


@pytest.mark.asyncio
async def test_jobs_life_passed_preflight_generates_each_frame_exactly_once(
    monkeypatch,
    tmp_path,
):
    plan, result, llm = await _run_jobs_sample()
    media_calls = []

    class _Media:
        async def __call__(self, **kwargs):
            media_calls.append(dict(kwargs))
            return SimpleNamespace(
                media_type="image",
                is_image=True,
                is_video=False,
                url="https://example.com/generated.png",
                duration=None,
            )

    processor = FrameProcessor(SimpleNamespace(media=_Media()))

    async def fake_download_media(_url, index, _task_id, *, media_type):
        assert media_type == "image"
        return str(tmp_path / f"frame-{index}.png")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)
    model_calls_before_images = len(llm.calls)
    for index, frame_result in enumerate(result.frames):
        request = frame_result.generation_request
        frame = StoryboardFrame(
            index=index,
            frame_id=request.frame_id,
            narration=plan.frames[index].source_text,
            image_prompt=request.final_positive_prompt,
            negative_prompt=request.final_negative_prompt,
            generation_seed=request.random_seed,
            visual_anchor_generation_request=request.model_dump(mode="json"),
        )
        await processor._step_generate_media_with_validation(
            frame,
            StoryboardConfig(
                task_id=request.task_id,
                media_width=request.expected_execution.width,
                media_height=request.expected_execution.height,
                media_workflow=request.workflow_key,
                frame_template="1080x1920/image_default.html",
                reference_image_workflow_injection_mode="off",
            ),
            max_attempts=1,
        )

    assert len(media_calls) == len(plan.frames)
    assert len(llm.calls) == model_calls_before_images
    assert [call["seed"] for call in media_calls] == [
        frame.generation_request.random_seed for frame in result.frames
    ]
    assert all(
        "reference_image_workflow_injection_mode" not in call
        for call in media_calls
    )
    assert all("negative_prompt" not in call for call in media_calls)
    assert all(
        call["_visual_anchor_generation_request"]["generation_attempt"] == 1
        for call in media_calls
    )


@pytest.mark.asyncio
async def test_rejected_preflight_exposes_no_image_generation_request():
    plan = _jobs_plan()
    model_content = _content_outputs(plan)[0]
    content = _materialize_content_stage_output(
        frame_id=plan.frames[0].frame_id,
        model_output=model_content,
    )
    fusion = _fusion_outputs([content])[0]
    failed_review = PreflightReviewOutput(
        decision="fail",
        failures=["主要主体未通过首次出图前审查"],
        allowed_final_positive_prompt="",
        allowed_final_negative_prompt="",
    )
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: [model_content],
            FusionStageOutput: [fusion],
            PreflightReviewOutput: [failed_review],
        }
    )
    image_generation_calls = []

    with pytest.raises(VisualAnchorTwoStageError, match="preflight review rejected"):
        await VisualAnchorTwoStageService().run_batch(
            llm_service=llm,
            storyboard_plan=StoryboardPlan.build(
                mode="sentence",
                count_mode="auto",
                requested_scene_count=None,
                source_text=plan.frames[0].source_text,
                frames=[plan.frames[0]],
            ),
            identity_profile=_identity(),
            identity_reference_condition=None,
            identity_conditioning_mode="text_profile",
            workflow_identity_condition_summary="文生图工作流使用文字身份档案",
            target_visual_style=_style(),
            visible_text_policy=_text_policy(),
            target_image_prompt_language="中文",
            task_id="task-rejected-preflight",
            workflow_key="selfhost/image_z_image_turbo_gguf.json",
            workflow_version_sha256="c" * 64,
            expected_execution=_execution(),
            random_seeds_by_frame={"jobs-1": 101},
            negative_prompt_supported=False,
        )

    assert image_generation_calls == []
    assert [call["response_type"] for call in llm.calls] == [
        ContentStageModelOutput,
        FusionStageOutput,
        PreflightReviewOutput,
    ]
