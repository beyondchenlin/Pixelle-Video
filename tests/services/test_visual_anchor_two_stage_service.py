import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pixelle_video.models.series_visual_signature import (
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.storyboard import StoryboardFrame
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_anchor_two_stage import (
    CONTENT_STAGE_PROMPT_VERSION,
    FUSION_STAGE_PROMPT_VERSION,
    PREFLIGHT_REVIEW_PROMPT_VERSION,
    ContentStageOutput,
    FusionStageInput,
    FusionStageOutput,
    IdentityReferenceCondition,
    ImageWorkflowExecutionContract,
    PreflightReviewOutput,
    VisualAnchorIdentityProfile,
    VisualAnchorImageGenerationRequest,
)
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.visual_anchor_generation_binding import (
    validate_visual_anchor_first_generation_binding,
)
from pixelle_video.services.visual_anchor_reference_condition import (
    inspect_identity_reference_workflow,
)
from pixelle_video.services.visual_anchor_reference_workflow import (
    resolve_visual_anchor_reference_workflow_key,
)
from pixelle_video.services.visual_anchor_two_stage_service import (
    VisualAnchorTwoStageError,
    VisualAnchorTwoStageService,
    _validate_content_stage_output,
    identity_profile_from_snapshot,
    resolve_registered_random_seeds,
)
from pixelle_video.services.visual_prompt_composer import (
    _content_only_visual_story_context,
)


class _QueuedLLM:
    def __init__(self, responses):
        self.responses = {
            response_type: list(items) for response_type, items in responses.items()
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


def _plan(*, continuous=False):
    frames = [
        StoryboardPlanFrame(
            index=1,
            frame_id="frame-a",
            source_text="乔布斯和沃兹尼亚克在车库组装一台电脑。",
            visual_goal="表现两人在车库创业",
            prompt_intent="车库工作台场景",
            continuity_anchors=("同一车库",) if continuous else (),
        )
    ]
    if continuous:
        frames.append(
            StoryboardPlanFrame(
                index=2,
                frame_id="frame-b",
                source_text="两人继续在同一车库测试这台电脑。",
                visual_goal="延续测试动作",
                prompt_intent="同一车库连续镜头",
                continuity_anchors=("同一车库",),
            )
        )
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=" ".join(frame.source_text for frame in frames),
        frames=frames,
    )


def test_identity_profile_binds_the_real_reference_when_profile_has_no_asset_ids():
    snapshot = VisualSignatureProfileSnapshot(
        profile_id="profile-pixelle",
        display_name="小皮",
        core_identity_traits=("圆形白色脸", "蓝色短耳"),
        supporting_identity_traits=("橙色围巾",),
        forbidden_traits=("改变脸型",),
        source_asset_ids=(),
    )

    identity = identity_profile_from_snapshot(
        snapshot,
        identity_reference_resource_id="reference-image:" + "a" * 64,
    )

    assert identity.source_asset_ids == ["reference-image:" + "a" * 64]
    with pytest.raises(VisualAnchorTwoStageError, match="no source assets"):
        identity_profile_from_snapshot(snapshot)


def _identity():
    return VisualAnchorIdentityProfile(
        profile_id="profile-pixelle",
        display_name="小皮",
        core_identity_traits=["圆形白色脸", "蓝色短耳"],
        supporting_identity_traits=["橙色围巾"],
        forbidden_traits=["改变脸型"],
        source_asset_ids=[
            "asset-pixelle-reference",
            "reference-image:" + "a" * 64,
        ],
        identity_content_sha256="b" * 64,
        identity_resource_version="identity:profile-pixelle:" + "b" * 64,
    )


def _reference(*, asset_sha256="a" * 64):
    return IdentityReferenceCondition(
        asset_sha256=asset_sha256,
        workflow_asset_relative_path="reference_image/workflow.png",
        mime_type="image/png",
        width=512,
        height=512,
        byte_size=1024,
        resource_version="reference-image:" + asset_sha256,
        workflow_parameter="reference_image",
        workflow_node_id="92",
        workflow_node_class_type="LoadImage",
        workflow_node_input_field="image",
        conditioning_node_id="94",
        conditioning_node_class_type="TextEncodeZImageOmni",
        sampler_node_id="3",
        sampler_node_class_type="KSampler",
        binding_path_node_ids=["92", "93", "94", "3"],
    )


def _execution(*, width=768, height=768):
    return ImageWorkflowExecutionContract(
        width=width,
        height=height,
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


def test_identity_reference_contract_requires_exact_first_sampling_path():
    payload = _reference().model_dump(mode="json")
    payload["binding_path_node_ids"] = ["92", "94", "3"]

    with pytest.raises(ValidationError, match="at least 4 items"):
        IdentityReferenceCondition.model_validate(payload)


def _content(frame_id, source_text):
    return ContentStageOutput(
        core_claim="两位创作者在车库制作电脑",
        protected_facts=[
            {
                "fact_id": f"{frame_id}-fact-1",
                "category": "event",
                "statement": source_text,
                "source_evidence": source_text,
                "pure_content_prompt_evidence": "车库内，两位创作者围绕工作台制作电脑",
            }
        ],
        adjustable_non_core_content=["工作台非核心工具", "局部照明"],
        pure_content_prompt="车库内，两位创作者围绕工作台制作电脑，暖色灯光和真实材质。",
        self_check="pass",
        self_check_failures=[],
    )


def _fusion(
    frame_id,
    *,
    inherited=False,
    positive=None,
    fact_ids=None,
    fact_evidence="乔布斯和沃兹尼亚克在工作台组装电脑",
    identity_evidence=("圆形白色脸", "蓝色短耳"),
    single_instance_evidence="画面中只有一只小皮",
):
    ids = fact_ids or [f"{frame_id}-fact-1"]
    return FusionStageOutput(
        selected_fusion_method="让小皮作为参与工作台场景的唯一实体，与两人共享现场光照",
        unselected_candidate_summaries=[
            {
                "manifestation": "墙面图形",
                "audit_summary": "实体形态更符合工作台空间关系",
            }
        ],
        content_stage_deviations=[],
        non_core_reconstruction_summary=["重新组织工作台工具和人物间距"],
        protected_fact_checks=[
            {
                "fact_id": fact_id,
                "preserved": True,
                "final_image_evidence": fact_evidence,
            }
            for fact_id in ids
        ],
        identity_trait_checks=[
            {
                "trait": trait,
                "preserved": True,
                "final_prompt_evidence": evidence,
            }
            for trait, evidence in zip(
                _identity().core_identity_traits,
                identity_evidence,
            )
        ],
        final_manifestation="小皮的单一实体形态",
        target_visual_anchor_instance_count=1,
        other_scene_elements_inherit_identity_features=False,
        single_instance_prompt_evidence=single_instance_evidence,
        spatial_contact_and_lighting_relation="站在工作台旁地面，接触关系、透视和暖色光影一致",
        inherited_existing_fusion_decision=inherited,
        continuity_change_reason=(
            "继承同一连续场景决定，无形态变化"
            if inherited
            else "当前是连续场景首镜"
        ),
        final_positive_prompt=positive
        or "车库内，乔布斯和沃兹尼亚克在工作台组装电脑。画面中只有一只小皮，它拥有圆形白色脸和蓝色短耳，以单一实体站在工作台旁，所有人物共享真实透视、暖色光照与自然接触阴影。",
        final_negative_prompt="重复的小皮，副本，镜像，倒影，悬浮，贴纸边缘，穿模，严重遮挡",
        self_check="pass",
        self_check_failures=[],
    )


def _review(fusion, *, negative_supported=False):
    return PreflightReviewOutput(
        decision="pass",
        failures=[],
        allowed_final_positive_prompt=fusion.final_positive_prompt,
        allowed_final_negative_prompt=(
            fusion.final_negative_prompt if negative_supported else ""
        ),
    )


async def _run(
    plan,
    *,
    content_outputs=None,
    fusion_outputs=None,
    review_outputs=None,
    target_visual_style="真实电影感",
):
    contents = content_outputs or [
        _content(frame.frame_id, frame.source_text) for frame in plan.frames
    ]
    fusions = fusion_outputs or [
        _fusion(frame.frame_id, inherited=index > 0)
        for index, frame in enumerate(plan.frames)
    ]
    reviews = review_outputs or [_review(fusion) for fusion in fusions]
    llm = _QueuedLLM(
        {
            ContentStageOutput: contents,
            FusionStageOutput: fusions,
            PreflightReviewOutput: reviews,
        }
    )
    result = await VisualAnchorTwoStageService().run_batch(
        llm_service=llm,
        storyboard_plan=plan,
        identity_profile=_identity(),
        identity_reference_condition=_reference(),
        target_visual_style=target_visual_style,
        target_image_prompt_language="中文",
        task_id="task-two-stage",
        workflow_key="selfhost/image_z_image_turbo_gguf_reference.json",
        workflow_version_sha256="c" * 64,
        expected_execution=_execution(),
        random_seeds_by_frame={frame.frame_id: 101 + i for i, frame in enumerate(plan.frames)},
        negative_prompt_supported=False,
    )
    return result, llm


@pytest.mark.asyncio
async def test_content_stage_call_has_no_identity_or_reference_inputs():
    result, llm = await _run(_plan())

    first_call = llm.calls[0]
    assert first_call["response_type"] is ContentStageOutput
    assert "小皮" not in first_call["prompt"]
    assert "圆形白色脸" not in first_call["prompt"]
    assert "a" * 64 not in first_call["prompt"]
    assert "identity_profile" not in first_call["prompt"]
    assert result.frames[0].content_stage_input.model_dump().keys() == {
        "frame_id",
        "original_storyboard_text",
        "article_context",
        "previous_frame_summary",
        "next_frame_summary",
        "target_visual_style",
        "target_image_prompt_language",
        "prompt_version",
    }
    assert tuple(inspect.signature(_validate_content_stage_output).parameters) == (
        "stage_input",
        "output",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_visual_style",
    [
        "真实电影感，圆形白色脸和蓝色短耳",
        "真实电影感，为视觉锚点预留角落",
    ],
)
async def test_content_stage_rejects_identity_bearing_style_before_any_model_call(
    target_visual_style,
):
    plan = _plan()
    llm = _QueuedLLM(
        {
            ContentStageOutput: [_content("frame-a", plan.frames[0].source_text)],
            FusionStageOutput: [_fusion("frame-a")],
            PreflightReviewOutput: [_review(_fusion("frame-a"))],
        }
    )

    with pytest.raises(
        VisualAnchorTwoStageError,
        match="content-stage visual style contains",
    ):
        await VisualAnchorTwoStageService().run_batch(
            llm_service=llm,
            storyboard_plan=plan,
            identity_profile=_identity(),
            identity_reference_condition=_reference(),
            target_visual_style=target_visual_style,
            target_image_prompt_language="中文",
            task_id="task-two-stage",
            workflow_key="selfhost/image_z_image_turbo_gguf_reference.json",
            workflow_version_sha256="c" * 64,
            expected_execution=_execution(),
            random_seeds_by_frame={"frame-a": 101},
            negative_prompt_supported=False,
        )

    assert llm.calls == []


@pytest.mark.asyncio
async def test_content_stage_retries_its_own_invalid_fact_contract_without_identity_input():
    plan = _plan()
    invalid = _content("frame-a", plan.frames[0].source_text)
    invalid = ContentStageOutput(
        **{
            **invalid.model_dump(),
            "protected_facts": [
                {
                    "fact_id": "frame-a-fact-1",
                    "category": "event",
                    "statement": plan.frames[0].source_text,
                    "source_evidence": "原文中不存在的证据",
                    "pure_content_prompt_evidence": "车库内",
                }
            ],
        }
    )

    result, llm = await _run(
        plan,
        content_outputs=[invalid, _content("frame-a", plan.frames[0].source_text)],
    )

    content_calls = [
        call for call in llm.calls if call["response_type"] is ContentStageOutput
    ]
    assert len(content_calls) == 2
    assert result.frames[0].content_stage_output.protected_facts[0].source_evidence == (
        plan.frames[0].source_text
    )


@pytest.mark.asyncio
async def test_content_stage_cannot_omit_a_protected_fact_from_the_pure_prompt():
    plan = _plan()
    invalid = _content("frame-a", plan.frames[0].source_text)
    invalid = ContentStageOutput.model_validate(
        {
            **invalid.model_dump(mode="json"),
            "protected_facts": [
                {
                    **invalid.protected_facts[0].model_dump(mode="json"),
                    "pure_content_prompt_evidence": "纯内容提示词中不存在的证据",
                }
            ],
        }
    )

    with pytest.raises(VisualAnchorTwoStageError, match="pure content prompt"):
        await _run(
            plan,
            content_outputs=[invalid, invalid],
        )


@pytest.mark.asyncio
async def test_fusion_stage_receives_every_required_input():
    result, llm = await _run(_plan())

    fusion_call = next(call for call in llm.calls if call["response_type"] is FusionStageOutput)
    for field_name in (
        "original_storyboard_text",
        "content_stage_output",
        "identity_profile",
        "identity_reference_condition",
        "continuous_scene_context",
    ):
        assert f'"{field_name}"' in fusion_call["prompt"]
    fusion_input = result.frames[0].fusion_stage_input
    assert fusion_input.identity_reference_condition.asset_sha256 == "a" * 64
    assert fusion_input.content_stage_output.protected_facts


@pytest.mark.asyncio
async def test_fusion_must_preserve_every_protected_fact():
    plan = _plan()
    content = _content("frame-a", plan.frames[0].source_text)
    content = ContentStageOutput(
        **{
            **content.model_dump(),
            "protected_facts": [
                *[fact.model_dump() for fact in content.protected_facts],
                {
                    "fact_id": "frame-a-fact-2",
                    "category": "place",
                    "statement": "地点是车库",
                    "source_evidence": "车库",
                    "pure_content_prompt_evidence": "车库内",
                },
            ],
        }
    )
    with pytest.raises(VisualAnchorTwoStageError, match="exactly cover"):
        await _run(
            plan,
            content_outputs=[content],
            fusion_outputs=[_fusion("frame-a"), _fusion("frame-a")],
        )


@pytest.mark.asyncio
async def test_final_prompt_rejects_candidate_language():
    candidate_positive = (
        _fusion("frame-a").final_positive_prompt
        + " 或者也可以让小皮出现在墙面图案中。"
    )
    with pytest.raises(VisualAnchorTwoStageError, match="candidate"):
        await _run(
            _plan(),
            fusion_outputs=[
                _fusion(
                    "frame-a",
                    positive=candidate_positive,
                ),
                _fusion(
                    "frame-a",
                    positive=candidate_positive,
                ),
            ],
        )


@pytest.mark.asyncio
async def test_fusion_reexecutes_before_preflight_when_identity_semantics_are_missing():
    incomplete = _fusion(
        "frame-a",
        positive="车库内，乔布斯和沃兹尼亚克在工作台组装电脑，一只小鸟自然站在工作台旁。",
    )
    complete = _fusion("frame-a")

    result, llm = await _run(
        _plan(),
        fusion_outputs=[incomplete, complete],
        review_outputs=[_review(complete)],
    )

    fusion_calls = [
        call for call in llm.calls if call["response_type"] is FusionStageOutput
    ]
    assert len(fusion_calls) == 2
    review_calls = [
        call for call in llm.calls if call["response_type"] is PreflightReviewOutput
    ]
    assert len(review_calls) == 1
    assert "identity trait evidence" in fusion_calls[1]["prompt"]
    assert result.frames[0].generation_request.final_positive_prompt == (
        complete.final_positive_prompt
    )


@pytest.mark.asyncio
async def test_preflight_allows_semantically_equivalent_identity_wording():
    fusion = _fusion(
        "frame-a",
        positive=(
            "车库内，乔布斯和沃兹尼亚克在工作台组装电脑。画面中只有一只名叫小皮的小动物，"
            "它拥有雪白圆脸与湛蓝短耳，自然站在工作台旁并共享暖色光影。"
        ),
        identity_evidence=("雪白圆脸", "湛蓝短耳"),
        single_instance_evidence="画面中只有一只名叫小皮的小动物",
    )
    result, _ = await _run(_plan(), fusion_outputs=[fusion])

    assert "雪白圆脸" in result.frames[0].generation_request.final_positive_prompt


@pytest.mark.asyncio
async def test_generation_request_contains_only_one_instance_and_clean_prompt():
    result, _ = await _run(_plan())
    request = result.frames[0].generation_request

    assert request.target_visual_anchor_instance_count == 1
    assert request.generation_attempt == 1
    assert request.preflight_review_decision == "pass"
    assert request.selected_fusion_method
    assert "non_core_reconstruction_summary" not in request.model_dump()
    assert "unselected_candidate_summaries" not in request.model_dump()
    assert request.single_instance_prompt_evidence in request.final_positive_prompt
    assert "或者" not in request.final_positive_prompt

    with pytest.raises(ValidationError, match="candidate or planning"):
        VisualAnchorImageGenerationRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "final_negative_prompt": "另一种形式也可以",
            }
        )


@pytest.mark.asyncio
async def test_final_prompt_evidence_must_be_real_distinct_prompt_text():
    invalid_fusions = [
        _fusion(
            "frame-a",
            fact_evidence="最终正向提示词中不存在的事实证据",
        ),
        _fusion(
            "frame-a",
            identity_evidence=("圆形白色脸", "圆形白色脸"),
        ),
        _fusion(
            "frame-a",
            identity_evidence=("小皮", "蓝色短耳"),
        ),
    ]
    for invalid in invalid_fusions:
        with pytest.raises(VisualAnchorTwoStageError):
            await _run(
                _plan(),
                fusion_outputs=[invalid, invalid],
            )


@pytest.mark.asyncio
async def test_unselected_candidate_summary_cannot_leak_into_negative_prompt():
    base = _fusion("frame-a")
    leaked = FusionStageOutput.model_validate(
        {
            **base.model_dump(mode="json"),
            "final_negative_prompt": (
                base.final_negative_prompt
                + "，墙面图形"
            ),
        }
    )

    with pytest.raises(VisualAnchorTwoStageError, match="unselected candidate"):
        await _run(
            _plan(),
            fusion_outputs=[leaked, leaked],
        )


def test_unselected_candidate_cannot_equal_selected_manifestation():
    base = _fusion("frame-a")
    with pytest.raises(ValidationError, match="cannot equal"):
        FusionStageOutput.model_validate(
            {
                **base.model_dump(mode="json"),
                "unselected_candidate_summaries": [
                    {
                        "manifestation": base.final_manifestation,
                        "audit_summary": "错误地把已选结果标成未选",
                    }
                ],
            }
        )


@pytest.mark.asyncio
async def test_failed_preflight_reexecutes_complete_fusion_once():
    first_fusion = _fusion("frame-a")
    second_fusion = _fusion(
        "frame-a",
        positive="车库内，乔布斯和沃兹尼亚克在工作台组装电脑。画面中只有一只小皮，它拥有圆形白色脸和蓝色短耳，以单一实体自然站在工作台旁，地面接触、透视和暖色阴影完整。",
    )
    failed_review = PreflightReviewOutput(
        decision="fail",
        failures=["空间接触关系证据不足"],
        allowed_final_positive_prompt="",
        allowed_final_negative_prompt="",
    )
    result, llm = await _run(
        _plan(),
        fusion_outputs=[first_fusion, second_fusion],
        review_outputs=[failed_review, _review(second_fusion)],
    )

    assert result.frames[0].fusion_attempt_count == 2
    fusion_calls = [
        call for call in llm.calls if call["response_type"] is FusionStageOutput
    ]
    assert len(fusion_calls) == 2
    assert "空间接触关系证据不足" in fusion_calls[1]["prompt"]
    assert result.frames[0].generation_request.final_positive_prompt == (
        second_fusion.final_positive_prompt
    )


def test_missing_reference_condition_fails_before_fusion():
    plan = _plan()
    with pytest.raises(ValidationError):
        FusionStageInput.model_validate(
            {
                "frame_id": "frame-a",
                "original_storyboard_text": plan.frames[0].source_text,
                "content_stage_output": _content(
                    "frame-a", plan.frames[0].source_text
                ).model_dump(),
                "identity_profile": _identity().model_dump(),
                "continuous_scene_context": {
                    "scene_id": "scene-a",
                    "previous_frame_summary": "首镜，无前一镜",
                    "next_frame_summary": "末镜，无后一镜",
                    "continuity_anchors": [],
                    "existing_fusion_decision": "无既有融合决策",
                },
                "target_visual_style": "真实电影感",
                "target_image_prompt_language": "中文",
            }
        )


@pytest.mark.parametrize("decision", ["unknown", "skipped", "timeout"])
def test_unknown_skipped_or_timeout_review_state_cannot_pass(decision):
    with pytest.raises(ValidationError):
        PreflightReviewOutput.model_validate(
            {
                "decision": decision,
                "failures": [],
                "allowed_final_positive_prompt": "小皮在场景中",
                "allowed_final_negative_prompt": "",
            }
        )


@pytest.mark.asyncio
async def test_continuous_scene_inherits_previous_fusion_decision():
    result, llm = await _run(_plan(continuous=True))

    second = result.frames[1]
    assert second.fusion_stage_input.continuous_scene_context.scene_id == (
        result.frames[0].fusion_stage_input.continuous_scene_context.scene_id
    )
    assert "最终表现形态" in (
        second.fusion_stage_input.continuous_scene_context.existing_fusion_decision
    )
    second_fusion_call = [
        call for call in llm.calls if call["response_type"] is FusionStageOutput
    ][1]
    assert "小皮的单一实体形态" in second_fusion_call["prompt"]


@pytest.mark.asyncio
async def test_visual_anchor_frame_disallows_generation_retries():
    result, _ = await _run(_plan())
    request = result.frames[0].generation_request
    frame = StoryboardFrame(
        index=0,
        frame_id="frame-a",
        narration="旁白",
        image_prompt=request.final_positive_prompt,
        generation_seed=request.random_seed,
        visual_anchor_generation_request=request.model_dump(mode="json"),
    )
    with pytest.raises(ValueError, match="exactly one"):
        await FrameProcessor(SimpleNamespace())._step_generate_media_with_validation(
            frame,
            SimpleNamespace(),
            max_attempts=2,
        )


def test_actual_workflow_reference_input_reaches_first_image_sampler():
    project_root = Path(__file__).resolve().parents[2]
    workflow_path = (
        project_root
        / "workflows/selfhost/image_z_image_turbo_gguf_reference.json"
    )
    inspection = inspect_identity_reference_workflow(
        workflow_info={
            "source": "selfhost",
            "path": str(workflow_path),
            "key": "selfhost/image_z_image_turbo_gguf_reference.json",
        },
        reference_asset_trace={
            "sha256": "a" * 64,
            "workflow_asset_relative_path": "reference_image/workflow.png",
            "mime_type": "image/png",
            "width": 512,
            "height": 512,
            "byte_size": 1024,
        },
        project_root=project_root,
    )

    assert inspection.condition.workflow_parameter == "reference_image"
    assert inspection.condition.binding_path_node_ids == ["92", "93", "94", "3"]
    assert inspection.condition.conditioning_node_class_type == (
        "TextEncodeZImageOmni"
    )
    assert inspection.condition.sampler_node_class_type == "KSampler"


@pytest.mark.parametrize(
    ("node_id", "input_name", "value"),
    [
        ("93", "width", 64),
        ("94", "auto_resize_images", True),
        ("94", "image2", ["92", 0]),
        ("94", "image1", ["92", 0]),
    ],
)
def test_workflow_reference_condition_rejects_unregistered_node_wiring(
    tmp_path,
    node_id,
    input_name,
    value,
):
    project_root = Path(__file__).resolve().parents[2]
    source_path = (
        project_root
        / "workflows/selfhost/image_z_image_turbo_gguf_reference.json"
    )
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    payload[node_id]["inputs"][input_name] = value
    workflow_path = tmp_path / "workflows/selfhost/invalid_reference.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        inspect_identity_reference_workflow(
            workflow_info={
                "source": "selfhost",
                "path": str(workflow_path),
                "key": "selfhost/invalid_reference.json",
            },
            reference_asset_trace={
                "sha256": "a" * 64,
                "workflow_asset_relative_path": "reference_image/workflow.png",
                "mime_type": "image/png",
                "width": 512,
                "height": 512,
                "byte_size": 1024,
            },
            project_root=tmp_path,
        )


def test_default_z_image_workflow_resolves_same_model_reference_variant():
    project_root = Path(__file__).resolve().parents[2]
    workflow_by_key = {
        "selfhost/image_z_image_turbo_gguf.json": (
            project_root / "workflows/selfhost/image_z_image_turbo_gguf.json"
        ),
        "selfhost/image_z_image_turbo_gguf_reference.json": (
            project_root
            / "workflows/selfhost/image_z_image_turbo_gguf_reference.json"
        ),
    }

    class _MediaService:
        def _resolve_workflow(self, *, workflow=None, workflow_domain=None):
            assert workflow_domain == "image"
            key = workflow or "selfhost/image_z_image_turbo_gguf.json"
            return {
                "source": "selfhost",
                "path": str(workflow_by_key[key]),
                "key": key,
            }

    assert resolve_visual_anchor_reference_workflow_key(
        media_service=_MediaService(),
        workflow=None,
    ) == "selfhost/image_z_image_turbo_gguf_reference.json"


@pytest.mark.parametrize("mutation", ["sampler", "extra_node"])
def test_reference_variant_cannot_change_dev_generation_configuration(
    tmp_path,
    mutation,
):
    project_root = Path(__file__).resolve().parents[2]
    base_payload = json.loads(
        (
            project_root / "workflows/selfhost/image_z_image_turbo_gguf.json"
        ).read_text(encoding="utf-8")
    )
    variant_payload = json.loads(
        (
            project_root
            / "workflows/selfhost/image_z_image_turbo_gguf_reference.json"
        ).read_text(encoding="utf-8")
    )
    if mutation == "sampler":
        variant_payload["3"]["inputs"]["steps"] = 6
    else:
        variant_payload["999"] = {
            "inputs": {"value": 1},
            "class_type": "PrimitiveInt",
            "_meta": {"title": "unregistered extra node"},
        }
    base_path = tmp_path / "image_z_image_turbo_gguf.json"
    variant_path = tmp_path / "image_z_image_turbo_gguf_reference.json"
    base_path.write_text(
        json.dumps(base_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    variant_path.write_text(
        json.dumps(variant_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths = {
        "selfhost/image_z_image_turbo_gguf.json": base_path,
        "selfhost/image_z_image_turbo_gguf_reference.json": variant_path,
    }

    class _MediaService:
        def _resolve_workflow(self, *, workflow=None, workflow_domain=None):
            key = workflow or "selfhost/image_z_image_turbo_gguf.json"
            return {"source": "selfhost", "path": str(paths[key]), "key": key}

    with pytest.raises(ValueError, match="preserve|may add only"):
        resolve_visual_anchor_reference_workflow_key(
            media_service=_MediaService(),
            workflow=None,
        )


def test_first_generation_binding_validates_actual_task_local_reference(tmp_path):
    reference_path = tmp_path / "reference_image/workflow.png"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"identity-reference")
    reference_sha256 = hashlib.sha256(b"identity-reference").hexdigest()
    request = VisualAnchorImageGenerationRequest(
        task_id="task-two-stage",
        frame_id="frame-a",
        random_seed=101,
        selected_fusion_method="小皮作为工作台旁的唯一实体",
        final_manifestation="小皮的单一实体形态",
        protected_fact_checks=[
            {
                "fact_id": "frame-a-fact-1",
                "preserved": True,
                "final_image_evidence": "车库工作台",
            }
        ],
        identity_trait_checks=[
            {
                "trait": "圆形白色脸",
                "preserved": True,
                "final_prompt_evidence": "圆形白色脸",
            },
            {
                "trait": "蓝色短耳",
                "preserved": True,
                "final_prompt_evidence": "蓝色短耳",
            },
        ],
        single_instance_prompt_evidence="画面中只有一只小皮",
        final_positive_prompt=(
            "车库工作台旁，画面中只有一只小皮，拥有圆形白色脸和蓝色短耳。"
        ),
        final_negative_prompt="",
        identity_profile_id="profile-pixelle",
        identity_display_name="小皮",
        identity_core_traits=["圆形白色脸", "蓝色短耳"],
        identity_resource_version="identity-v1",
        identity_content_sha256="b" * 64,
        identity_reference_condition=_reference(asset_sha256=reference_sha256),
        content_stage_prompt_version=CONTENT_STAGE_PROMPT_VERSION,
        fusion_stage_prompt_version=FUSION_STAGE_PROMPT_VERSION,
        preflight_review_prompt_version=PREFLIGHT_REVIEW_PROMPT_VERSION,
        preflight_review_decision="pass",
        workflow_key="selfhost/image_z_image_turbo_gguf_reference.json",
        workflow_version_sha256="c" * 64,
        expected_execution=_execution(),
    )
    binding = {
        "status": "injected",
        "injection_mode": "required",
        "summary": {
            "param_names": ["reference_image"],
            "asset": {
                "sha256": "d" * 64,
                "workflow_sha256": reference_sha256,
                "workflow_asset_relative_path": "reference_image/workflow.png",
            },
        },
    }
    audit = validate_visual_anchor_first_generation_binding(
        request_payload=request.model_dump(mode="json"),
        prompt=request.final_positive_prompt,
        negative_prompt=None,
        seed=101,
        media_type="image",
        trace_context={
            "task_id": "task-two-stage",
            "frame_id": "frame-a",
            "task_root": str(tmp_path),
        },
        workflow_info={"key": request.workflow_key, "source": "selfhost"},
        workflow_file_trace={"workflow_file_sha256": "c" * 64},
        reference_binding_trace=binding,
        workflow_params={
            "reference_image": str(reference_path),
            "width": 768,
            "height": 768,
        },
    )

    assert audit["status"] == "ready_to_submit"
    assert audit["request_version"] == request.request_version
    assert audit["actual_binding"]["asset_sha256"] == reference_sha256
    from pixelle_video.services.visual_anchor_generation_binding import (
        visual_anchor_first_request_binding_artifact_relative_path,
    )

    assert (
        tmp_path
        / visual_anchor_first_request_binding_artifact_relative_path("frame-a")
    ).is_file()


def test_reference_context_is_removed_only_from_identity_enabled_content_boundary():
    source = {
        "reference_image": {"enabled": True, "asset_sha256": "a" * 64},
        "selected_visual_route": {"route_id": "route-a", "route_name": "纪实"},
    }

    isolated = _content_only_visual_story_context(
        source,
        identity_isolation_enabled=True,
    )
    ordinary = _content_only_visual_story_context(
        source,
        identity_isolation_enabled=False,
    )

    assert "reference_image" not in isolated
    assert ordinary["reference_image"]["asset_sha256"] == "a" * 64


def test_seed_registration_is_complete_and_deterministic():
    plan = _plan(continuous=True)
    first = resolve_registered_random_seeds(
        storyboard_plan=plan,
        task_id="task-two-stage",
    )
    second = resolve_registered_random_seeds(
        storyboard_plan=plan,
        task_id="task-two-stage",
    )

    assert first == second
    assert set(first) == {"frame-a", "frame-b"}
    with pytest.raises(VisualAnchorTwoStageError, match="every frame"):
        resolve_registered_random_seeds(
            storyboard_plan=plan,
            task_id="task-two-stage",
            media_seed_by_frame={"frame-a": 1},
        )
