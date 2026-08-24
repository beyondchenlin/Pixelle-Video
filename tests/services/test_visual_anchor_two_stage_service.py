import hashlib
import json

import pytest
from pydantic import ValidationError

from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_anchor_two_stage import (
    ContentStageInput,
    ContentStageModelOutput,
    ContentStageOutput,
    ContentSubject,
    FusionStageModelOutput,
    FusionStageOutput,
    IdentityReferenceCondition,
    ImageWorkflowExecutionContract,
    LegacyContentStageOutputV14,
    LegacyFusionStageOutputV12,
    VisualAnchorIdentityProfile,
    VisualAnchorImageGenerationRequest,
    VisualAnchorTwoStageFrameResult,
)
from pixelle_video.services import visual_anchor_regeneration
from pixelle_video.services.visual_anchor_two_stage_service import (
    VisualAnchorTwoStageError,
    VisualAnchorTwoStageService,
    identity_profile_from_snapshot,
    resolve_registered_random_seeds,
)

REMOVED_PROOF_FIELDS = {
    "source_evidence",
    "pure_content_prompt_evidence",
    "protected_facts",
    "protected_fact_checks",
    "primary_subject_preserved",
    "primary_subject_final_prompt_evidence",
    "visual_anchor_replaces_primary_subject",
    "identity_trait_checks",
    "target_visual_anchor_instance_count",
    "other_scene_elements_inherit_identity_features",
    "single_instance_prompt_evidence",
    "self_check",
    "self_check_failures",
    "required_single_instance_prompt_fragment",
}


class _QueuedLLM:
    def __init__(self, responses):
        self.responses = {
            response_type: list(items) for response_type, items in responses.items()
        }
        self.calls = []

    async def __call__(self, *, prompt, response_type, **kwargs):
        self.calls.append(
            {"prompt": prompt, "response_type": response_type, "kwargs": kwargs}
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


def _identity():
    return VisualAnchorIdentityProfile(
        profile_id="profile-pixelle",
        display_name="小皮",
        core_identity_traits=["圆形白色脸", "蓝色短耳"],
        supporting_identity_traits=["橙色围巾"],
        forbidden_traits=["改变脸型"],
        source_asset_ids=["reference-image:" + "a" * 64],
        identity_content_sha256="b" * 64,
        identity_resource_version="identity:profile-pixelle:" + "b" * 64,
    )


def _reference():
    return IdentityReferenceCondition(
        asset_sha256="a" * 64,
        workflow_asset_relative_path="reference_image/workflow.png",
        mime_type="image/png",
        width=512,
        height=512,
        byte_size=1024,
        resource_version="reference-image:" + "a" * 64,
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


def _execution():
    return ImageWorkflowExecutionContract(
        width=768,
        height=768,
        model_files=["z-image-turbo-Q8_0.gguf"],
        steps=5,
        cfg=1.0,
        sampler_name="euler",
        scheduler="simple",
        denoise=1.0,
    )


def _content(frame_id, source_text):
    return ContentStageModelOutput(
        core_claim=f"处理 {frame_id}",
        shot_purpose=f"让观众看懂 {frame_id} 的具体事件",
        renderable_story_beats=["工作台上的电脑部件正在被组装"],
        decisive_moment="两人的手同时停在正在连接的电脑部件上",
        primary_subject={
            "category": "person",
            "name": "由模型判断的主体",
            "identity": "模型自行给出的身份",
            "quantity": 1,
            "action": "",
        },
        secondary_subjects=[],
        content_subject_interaction="两人共同操作工作台上的电脑部件",
        composition_plan={
            "shot_scale_and_camera": "平视中景，工作台形成横向视觉轴",
            "foreground": "散开的电路板和工具",
            "midground": "两位创业者与正在组装的电脑",
            "background": "车库门和储物架",
            "visual_focus": "两人的手与电脑部件的连接处",
        },
        adjacent_shot_distinction="本镜以共同组装动作区别于相邻镜头",
        scene_facts=[{"category": "event", "statement": source_text}],
        adjustable_non_core_content=["背景"],
    )


def _fusion(frame_id, *, inherited=False, negative_prompt=""):
    return FusionStageModelOutput(
        selected_fusion_method="工作服胸前的布面刺绣",
        final_manifestation="小皮作为工作服胸前的单一布面刺绣形态",
        relative_scale_and_visual_weight="巴掌大小，低于人物面部和手部的视觉权重",
        support_carrier_and_material_relation="工作服胸前的布面刺绣，服从衣料褶皱",
        visual_identity_scene_interaction="随人物操作电脑时产生的衣物姿态变化参与场景",
        spatial_contact_and_lighting_relation="模型判断的空间和光照关系",
        inherited_existing_fusion_decision=inherited,
        continuity_change_reason="",
        scene_negative_prompt=negative_prompt,
    )


_DEFAULT_REFERENCE = object()


async def _run_service(
    plan,
    llm,
    *,
    stage_callback=None,
    identity_conditioning_mode="reference_image",
    identity_reference_condition=_DEFAULT_REFERENCE,
    random_seeds_by_frame=None,
):
    reference_condition = identity_reference_condition
    if reference_condition is _DEFAULT_REFERENCE:
        reference_condition = (
            _reference()
            if identity_conditioning_mode == "reference_image"
            else None
        )
    seeds = (
        random_seeds_by_frame
        if random_seeds_by_frame is not None
        else {
            frame.frame_id: 101 + index
            for index, frame in enumerate(plan.frames)
        }
    )
    return await VisualAnchorTwoStageService().run_batch(
        llm_service=llm,
        storyboard_plan=plan,
        identity_profile=_identity(),
        identity_reference_condition=reference_condition,
        identity_conditioning_mode=identity_conditioning_mode,
        workflow_identity_condition_summary=(
            "真实参考资源已绑定到首次工作流"
            if identity_conditioning_mode == "reference_image"
            else "工作流使用文字身份档案"
        ),
        target_visual_style="真实电影感",
        target_image_prompt_language="中文",
        task_id="task-two-stage",
        workflow_key="selfhost/image_z_image_turbo_gguf_reference.json",
        workflow_version_sha256="c" * 64,
        expected_execution=_execution(),
        random_seeds_by_frame=seeds,
        negative_prompt_supported=False,
        stage_callback=stage_callback,
    )


async def _run(
    plan,
    *,
    fusions=None,
    stage_callback=None,
    identity_conditioning_mode="reference_image",
):
    contents = [_content(frame.frame_id, frame.source_text) for frame in plan.frames]
    fusion_outputs = fusions or [
        _fusion(frame.frame_id, inherited=index > 0)
        for index, frame in enumerate(plan.frames)
    ]
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: contents,
            FusionStageModelOutput: fusion_outputs,
        }
    )
    result = await _run_service(
        plan,
        llm,
        identity_conditioning_mode=identity_conditioning_mode,
        stage_callback=stage_callback,
    )
    return result, llm


def test_identity_profile_binds_real_reference_resource():
    snapshot = VisualSignatureProfileSnapshot(
        profile_id="profile-pixelle",
        display_name="小皮",
        core_identity_traits=("圆形白色脸",),
        source_asset_ids=(),
    )
    identity = identity_profile_from_snapshot(
        snapshot,
        identity_reference_resource_id="reference-image:" + "a" * 64,
    )
    assert identity.source_asset_ids == ["reference-image:" + "a" * 64]


def test_reference_contract_keeps_only_structural_wiring_validation():
    payload = _reference().model_dump(mode="json")
    payload["binding_path_node_ids"] = ["92", "94", "3"]
    with pytest.raises(ValidationError, match="at least 4 items"):
        IdentityReferenceCondition.model_validate(payload)


def test_model_schemas_do_not_request_proof_fields():
    schemas = (
        ContentStageModelOutput.model_json_schema(),
        FusionStageModelOutput.model_json_schema(),
        VisualAnchorImageGenerationRequest.model_json_schema(),
    )
    schema_text = str(schemas)
    for field_name in REMOVED_PROOF_FIELDS:
        assert field_name not in schema_text
    assert "pure_content_prompt" not in str(ContentStageModelOutput.model_json_schema())
    assert "identity_prompt_clause" not in str(FusionStageModelOutput.model_json_schema())
    assert "final_positive_prompt" not in str(FusionStageModelOutput.model_json_schema())
    assert "base_content_prompt" not in str(FusionStageModelOutput.model_json_schema())
    assert "final_scene_prompt_prefix" not in str(
        FusionStageModelOutput.model_json_schema()
    )
    assert "target_visual_style" not in str(ContentStageInput.model_json_schema())


def test_current_model_output_bounds_prevent_prompt_and_list_amplification():
    content_payload = _content("frame-a", "原文").model_dump(mode="json")
    content_payload["renderable_story_beats"] = [f"画面证据-{index}" for index in range(7)]
    with pytest.raises(ValidationError, match="at most 6 items"):
        ContentStageModelOutput.model_validate(content_payload)

    fusion_payload = _fusion("frame-a").model_dump(mode="json")
    fusion_payload["relative_scale_and_visual_weight"] = "长" * 1201
    with pytest.raises(ValidationError, match="at most 1200 characters"):
        FusionStageModelOutput.model_validate(fusion_payload)


def test_legacy_proof_fields_are_dropped_at_parse_boundary():
    content_payload = _content("frame-a", "原文").model_dump(mode="json")
    content_payload.update({"self_check": "fail", "self_check_failures": ["旧字段"]})
    content_payload["primary_subject"].update(
        {
            "source_evidence": "旧证据",
            "pure_content_prompt_evidence": "旧证据",
            "protected_facts": [{"statement": "旧事实"}],
        }
    )
    content = ContentStageModelOutput.model_validate(content_payload)
    assert REMOVED_PROOF_FIELDS.isdisjoint(content.model_dump(mode="json"))

    fusion_payload = _fusion("frame-a").model_dump(mode="json")
    fusion_payload.update(
        {
            "self_check": "fail",
            "protected_fact_checks": [],
            "identity_trait_checks": [],
            "single_instance_prompt_evidence": "旧证据",
        }
    )
    fusion = FusionStageModelOutput.model_validate(fusion_payload)
    assert REMOVED_PROOF_FIELDS.isdisjoint(fusion.model_dump(mode="json"))


def test_unknown_model_output_fields_are_rejected_instead_of_silently_dropped():
    content_payload = _content("frame-a", "原文").model_dump(mode="json")
    content_payload["unexpected_contract_field"] = "不得静默忽略"
    with pytest.raises(ValidationError, match="unexpected_contract_field"):
        ContentStageModelOutput.model_validate(content_payload)

    fusion_payload = _fusion("frame-a").model_dump(mode="json")
    fusion_payload["unexpected_contract_field"] = "不得静默忽略"
    with pytest.raises(ValidationError, match="unexpected_contract_field"):
        FusionStageModelOutput.model_validate(fusion_payload)


@pytest.mark.asyncio
async def test_content_output_preserves_model_fields_without_server_owned_subject_ids():
    result, _ = await _run(_plan())
    output = result.frames[0].content_stage_output
    assert isinstance(output, ContentStageOutput)
    assert output.primary_subject.name == "由模型判断的主体"
    assert output.scene_facts[0].statement == _plan().frames[0].source_text
    assert "subject_id" not in output.primary_subject.model_dump(mode="json")


def test_legacy_content_subject_import_drops_removed_server_fields():
    subject = ContentSubject.model_validate(
        {
            "subject_id": "legacy-subject",
            "role": "primary",
            "category": "person",
            "name": "旧主体",
            "identity": "旧身份",
            "quantity": 1,
            "action": "",
        }
    )

    assert subject.name == "旧主体"
    assert "subject_id" not in subject.model_dump(mode="json")


@pytest.mark.asyncio
async def test_server_assembled_model_output_flows_directly_to_generation():
    result, llm = await _run(_plan())
    frame = result.frames[0]
    assert isinstance(frame.fusion_stage_output, FusionStageOutput)
    assert (
        frame.fusion_stage_output.identity_prompt_clause
        in frame.generation_request.final_positive_prompt
    )
    for required_fragment in (
        frame.fusion_stage_output.final_manifestation,
        *frame.fusion_stage_input.identity_profile.core_identity_traits,
        frame.fusion_stage_output.relative_scale_and_visual_weight,
        frame.fusion_stage_output.support_carrier_and_material_relation,
        frame.fusion_stage_output.visual_identity_scene_interaction,
        frame.fusion_stage_output.spatial_contact_and_lighting_relation,
    ):
        assert required_fragment in frame.fusion_stage_output.identity_prompt_clause
    assert frame.generation_request.prompt_assembly_trace is not None
    assert (
        frame.fusion_stage_output.base_content_prompt
        == frame.content_stage_output.pure_content_prompt
    )
    assert frame.generation_request.final_positive_prompt.startswith(
        frame.content_stage_output.pure_content_prompt
    )
    assert frame.generation_request.final_negative_prompt == ""
    assert len(llm.calls) == 2
    assert all(call["kwargs"]["temperature"] == 0.0 for call in llm.calls)
    assert all(call["kwargs"]["max_tokens"] == 4096 for call in llm.calls)
    assert all(call["kwargs"]["single_request"] is True for call in llm.calls)


@pytest.mark.asyncio
async def test_content_prompt_is_assembled_from_structured_visual_decisions():
    result, llm = await _run(_plan())
    content = result.frames[0].content_stage_output
    assert isinstance(content, ContentStageOutput)
    for required_fragment in (
        content.primary_subject.name,
        content.primary_subject.identity,
        content.composition_plan.shot_scale_and_camera,
        content.decisive_moment,
        content.content_subject_interaction,
        *content.renderable_story_beats,
        *(fact.statement for fact in content.scene_facts),
        content.composition_plan.visual_focus,
    ):
        assert required_fragment in content.pure_content_prompt
    assert "真实电影感" not in content.pure_content_prompt
    assert "真实电影感" not in llm.calls[0]["prompt"]
    assert "真实电影感" in llm.calls[1]["prompt"]


@pytest.mark.asyncio
async def test_content_prompt_preserves_explicit_subject_quantity():
    plan = _plan()
    content_payload = _content("frame-a", plan.frames[0].source_text).model_dump(
        mode="json"
    )
    content_payload["primary_subject"]["quantity"] = 2
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: [content_payload],
            FusionStageModelOutput: [_fusion("frame-a")],
        }
    )

    result = await _run_service(plan, llm)

    assert "2× 由模型判断的主体" in (
        result.frames[0].content_stage_output.pure_content_prompt
    )


@pytest.mark.asyncio
async def test_article_context_is_bounded_around_the_current_source_span():
    prefix = "前文背景。" * 1000
    frame_text = "关键人物把完成的电路板安装进电脑机箱。"
    suffix = "后文背景。" * 1000
    source_text = prefix + frame_text + suffix
    plan = StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=source_text,
        frames=[
            StoryboardPlanFrame(
                index=1,
                frame_id="frame-a",
                source_text=frame_text,
                visual_goal="表现安装完成",
                prompt_intent="车库电脑组装",
                source_start=len(prefix),
                source_end=len(prefix) + len(frame_text),
            )
        ],
    )

    result, _ = await _run(plan)

    article_context = result.frames[0].content_stage_input.article_context
    assert len(article_context) == 6000
    assert frame_text in article_context


@pytest.mark.asyncio
async def test_oversized_frame_fails_before_any_model_call():
    source_text = "过长分镜内容" * 1001
    plan = StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=source_text,
        frames=[
            StoryboardPlanFrame(
                index=1,
                frame_id="frame-a",
                source_text=source_text,
                visual_goal="不应进入模型",
                prompt_intent="不应进入模型",
            )
        ],
    )
    llm = _QueuedLLM({ContentStageModelOutput: [], FusionStageModelOutput: []})

    with pytest.raises(VisualAnchorTwoStageError, match="exceeds 6000 characters"):
        await _run_service(plan, llm)

    assert llm.calls == []


@pytest.mark.asyncio
async def test_composition_does_not_invent_missing_depth_layers():
    plan = _plan()
    flat_content = _content("frame-a", plan.frames[0].source_text).model_dump(mode="json")
    flat_content["composition_plan"].update(
        {"foreground": "", "midground": "", "background": "单色平面背景"}
    )
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: [flat_content],
            FusionStageModelOutput: [_fusion("frame-a")],
        }
    )

    result = await _run_service(plan, llm)

    assert result.frames[0].content_stage_output.composition_plan.foreground == ""
    assert result.frames[0].content_stage_output.composition_plan.midground == ""
    assert "单色平面背景" in result.frames[0].content_stage_output.pure_content_prompt


@pytest.mark.asyncio
async def test_tampered_server_assembled_prompt_is_rejected():
    result, _ = await _run(_plan())
    payload = result.frames[0].model_dump(mode="json")
    tampered = payload["fusion_stage_output"]["final_positive_prompt"] + "；额外对象"
    payload["fusion_stage_output"]["final_positive_prompt"] = tampered
    payload["generation_request"]["final_positive_prompt"] = tampered

    with pytest.raises(ValidationError, match="positive prompt differs from its assembly trace"):
        VisualAnchorTwoStageFrameResult.model_validate(payload)


@pytest.mark.asyncio
async def test_generation_request_rejects_a_forged_prompt_assembly_trace_on_its_own():
    result, _ = await _run(_plan())
    payload = result.frames[0].generation_request.model_dump(mode="json")
    payload["prompt_assembly_trace"]["relative_scale_and_visual_weight"] = (
        "伪造的超大视觉权重"
    )

    with pytest.raises(ValidationError, match="identity clause differs from its assembly trace"):
        VisualAnchorImageGenerationRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_fusion_cannot_replace_the_server_owned_content_prompt():
    result, _ = await _run(_plan())
    payload = result.frames[0].model_dump(mode="json")
    original = payload["fusion_stage_output"]["base_content_prompt"]
    forged = "伪造的场景正文"
    tampered_prompt = payload["fusion_stage_output"]["final_positive_prompt"].replace(
        original,
        forged,
        1,
    )
    payload["fusion_stage_output"]["base_content_prompt"] = forged
    payload["fusion_stage_output"]["final_positive_prompt"] = tampered_prompt
    payload["generation_request"]["prompt_assembly_trace"][
        "base_content_prompt"
    ] = forged
    payload["generation_request"]["final_positive_prompt"] = tampered_prompt

    with pytest.raises(ValidationError, match="preserve the exact assembled content prompt"):
        VisualAnchorTwoStageFrameResult.model_validate(payload)


@pytest.mark.asyncio
async def test_negative_prompt_for_unsupported_workflow_fails_without_retry():
    plan = _plan()
    invalid_fusion = _fusion("frame-a").model_dump(mode="json")
    invalid_fusion["scene_negative_prompt"] = "模型不应输出的反向提示词"
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: [_content("frame-a", plan.frames[0].source_text)],
            FusionStageModelOutput: [invalid_fusion, _fusion("frame-a")],
        }
    )
    events = []

    with pytest.raises(VisualAnchorTwoStageError, match="scene_negative_prompt"):
        await _run_service(plan, llm, stage_callback=events.append)

    assert len(llm.calls) == 2
    assert [
        (event["stage"], event["event"], event.get("llm_call_count"))
        for event in events
    ] == [
        ("visual_anchor_content_stage", "start", None),
        ("visual_anchor_content_stage", "end", 1),
        ("visual_anchor_fusion_stage", "start", None),
        ("visual_anchor_fusion_stage", "fail", 1),
    ]


@pytest.mark.asyncio
async def test_generation_request_contains_no_proof_fields():
    result, _ = await _run(_plan())
    payload = result.frames[0].generation_request.model_dump(mode="json")
    assert REMOVED_PROOF_FIELDS.isdisjoint(payload)


@pytest.mark.asyncio
async def test_each_stage_emits_one_start_and_one_end_event():
    events = []
    await _run(_plan(), stage_callback=events.append)
    stage_events = [
        (event["stage"], event["event"], event.get("llm_call_count"))
        for event in events
        if event["stage"].startswith("visual_anchor_")
    ]
    assert stage_events == [
        ("visual_anchor_content_stage", "start", None),
        ("visual_anchor_content_stage", "end", 1),
        ("visual_anchor_fusion_stage", "start", None),
        ("visual_anchor_fusion_stage", "end", 1),
    ]


@pytest.mark.asyncio
async def test_invalid_reference_configuration_fails_before_any_model_call():
    plan = _plan()
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: [_content("frame-a", plan.frames[0].source_text)],
            FusionStageModelOutput: [_fusion("frame-a")],
        }
    )

    with pytest.raises(VisualAnchorTwoStageError, match="requires a real reference"):
        await _run_service(
            plan,
            llm,
            identity_conditioning_mode="reference_image",
            identity_reference_condition=None,
        )

    assert llm.calls == []


@pytest.mark.asyncio
async def test_invalid_seed_fails_before_any_model_call():
    plan = _plan()
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: [_content("frame-a", plan.frames[0].source_text)],
            FusionStageModelOutput: [_fusion("frame-a")],
        }
    )

    with pytest.raises(VisualAnchorTwoStageError, match="between 1 and"):
        await _run_service(
            plan,
            llm,
            random_seeds_by_frame={"frame-a": 0},
        )

    assert llm.calls == []


@pytest.mark.asyncio
async def test_structural_model_failure_stops_after_one_call_without_retry():
    plan = _plan()
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: [
                {"core_claim": "缺少必填结构"},
                _content("frame-a", plan.frames[0].source_text),
            ],
            FusionStageModelOutput: [_fusion("frame-a")],
        }
    )
    events = []

    with pytest.raises(ValidationError):
        await _run_service(plan, llm, stage_callback=events.append)

    assert len(llm.calls) == 1
    assert [
        (event["event"], event.get("llm_call_count"), event.get("retry_count"))
        for event in events
    ] == [("start", None, None), ("fail", 1, 0)]


@pytest.mark.asyncio
async def test_continuous_scene_carries_and_validates_the_complete_decision():
    fusions = [_fusion("frame-a"), _fusion("frame-b", inherited=True)]
    result, _ = await _run(_plan(continuous=True), fusions=fusions)
    second_input = result.frames[1].fusion_stage_input.continuous_scene_context
    assert second_input.existing_selected_fusion_method == fusions[0].selected_fusion_method
    assert second_input.existing_relative_scale_and_visual_weight == (
        fusions[0].relative_scale_and_visual_weight
    )
    assert second_input.existing_support_carrier_and_material_relation == (
        fusions[0].support_carrier_and_material_relation
    )
    assert second_input.existing_visual_identity_scene_interaction == (
        fusions[0].visual_identity_scene_interaction
    )
    assert second_input.existing_fusion_decision == "已有融合决策见下列结构化字段"
    assert result.frames[1].fusion_stage_output.inherited_existing_fusion_decision


@pytest.mark.asyncio
async def test_continuous_scene_rejects_false_inheritance_without_retry():
    plan = _plan(continuous=True)
    changed_second = _fusion("frame-b", inherited=True).model_dump(mode="json")
    changed_second["relative_scale_and_visual_weight"] = "改成占据画面中心的大尺寸"
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: [
                _content(frame.frame_id, frame.source_text) for frame in plan.frames
            ],
            FusionStageModelOutput: [_fusion("frame-a"), changed_second],
        }
    )

    with pytest.raises(ValidationError, match="must match every previous field"):
        await _run_service(plan, llm)

    assert len(llm.calls) == 4


def test_seed_registration_is_complete_and_deterministic():
    plan = _plan(continuous=True)
    first = resolve_registered_random_seeds(
        storyboard_plan=plan,
        task_id="task-seed",
    )
    second = resolve_registered_random_seeds(
        storyboard_plan=plan,
        task_id="task-seed",
    )
    assert first == second
    assert set(first) == {"frame-a", "frame-b"}
    assert all(seed > 0 for seed in first.values())
    expected = int.from_bytes(
        hashlib.sha256(b"task-seed:frame-a").digest()[:8], "big"
    )
    assert first["frame-a"] == max(1, expected)


def _contract_digest(payload):
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _prompt_plan(frame_payload, *, contract_digest=None):
    request = frame_payload["generation_request"]
    return PromptPlan(
        prompt_plan_id="prompt-plan-a",
        storyboard_plan_id="storyboard-plan-a",
        frame_id=frame_payload["frame_id"],
        image_prompt_draft_id="draft-a",
        prompt_sections={"scene": request["final_positive_prompt"]},
        final_prompt=request["final_positive_prompt"],
        final_negative_prompt=request["final_negative_prompt"] or None,
        identity_content_sha256=request["identity_content_sha256"],
        contract_content_sha256=contract_digest or _contract_digest(frame_payload),
        contract_version=request["request_version"],
        metadata={"visual_anchor_two_stage": frame_payload},
    )


def _as_legacy_v4_payload(frame_payload):
    payload = json.loads(json.dumps(frame_payload, ensure_ascii=False))
    payload["content_stage_input"]["target_visual_style"] = payload[
        "fusion_stage_input"
    ]["target_visual_style"]
    payload["content_stage_input"]["prompt_version"] = (
        "visual_anchor_content_stage.v12"
    )
    payload["fusion_stage_input"]["prompt_version"] = (
        "visual_anchor_fusion_stage.v9"
    )
    request = payload["generation_request"]
    request["request_version"] = "visual_anchor_generation_request.v4"
    request["content_stage_prompt_version"] = "visual_anchor_content_stage.v12"
    request["fusion_stage_prompt_version"] = "visual_anchor_fusion_stage.v9"
    request.pop("prompt_assembly_trace", None)
    request.update(
        {
            "protected_fact_checks": [],
            "primary_subject_name": "旧主体",
            "primary_subject_preserved": False,
            "identity_trait_checks": [],
            "single_instance_prompt_evidence": "旧证明",
        }
    )

    content_payload = payload["content_stage_output"]
    for current_field in (
        "prompt_assembly_version",
        "shot_purpose",
        "renderable_story_beats",
        "decisive_moment",
        "content_subject_interaction",
        "composition_plan",
        "adjacent_shot_distinction",
    ):
        content_payload.pop(current_field, None)
    legacy_facts = []
    for index, fact in enumerate(content_payload.pop("scene_facts"), start=1):
        legacy_facts.append(
            {
                **fact,
                "fact_id": f"fact-{index}",
                "subject_ids": ["subject-primary"],
                "source_evidence": "旧来源证明",
                "pure_content_prompt_evidence": "旧提示词证明",
            }
        )
    content_payload["protected_facts"] = legacy_facts
    content_payload.update({"self_check": "fail", "self_check_failures": ["旧字段"]})
    content_payload["primary_subject"].update(
        {
            "subject_id": "subject-primary",
            "role": "primary",
            "source_evidence": "旧来源证明",
            "pure_content_prompt_evidence": "旧提示词证明",
        }
    )
    payload["fusion_stage_input"]["content_stage_output"] = json.loads(
        json.dumps(content_payload, ensure_ascii=False)
    )
    payload["fusion_stage_input"].update(
        {
            "review_feedback": ["旧反馈"],
            "required_single_instance_prompt_fragment": "旧约束",
        }
    )
    payload["fusion_stage_output"].update(
        {
            "unselected_candidate_summaries": [],
            "content_stage_deviations": [],
            "non_core_reconstruction_summary": [],
            "protected_fact_checks": [],
            "primary_subject_preserved": False,
            "primary_subject_final_prompt_evidence": "旧证明",
            "visual_anchor_replaces_primary_subject": True,
            "identity_trait_checks": [],
            "target_visual_anchor_instance_count": 2,
            "other_scene_elements_inherit_identity_features": True,
            "single_instance_prompt_evidence": "旧证明",
            "self_check": "fail",
            "self_check_failures": ["旧字段"],
        }
    )
    for current_field in (
        "prompt_assembly_version",
        "base_content_prompt",
        "identity_prompt_clause",
        "relative_scale_and_visual_weight",
        "support_carrier_and_material_relation",
        "visual_identity_scene_interaction",
        "final_scene_prompt_prefix",
        "final_scene_prompt_suffix",
        "scene_negative_prompt",
    ):
        payload["fusion_stage_output"].pop(current_field, None)
    payload.update(
        {
            "content_attempt_count": 2,
            "content_retry_validation_codes": ["旧代码"],
            "fusion_attempt_count": 2,
        }
    )
    return payload


def _as_legacy_v14_v12_payload(frame_payload):
    payload = json.loads(json.dumps(frame_payload, ensure_ascii=False))
    payload["content_stage_input"]["target_visual_style"] = payload[
        "fusion_stage_input"
    ]["target_visual_style"]
    payload["content_stage_input"]["prompt_version"] = (
        "visual_anchor_content_stage.v14"
    )
    payload["fusion_stage_input"]["prompt_version"] = (
        "visual_anchor_fusion_stage.v12"
    )

    content_payload = payload["content_stage_output"]
    content_payload.pop("prompt_assembly_version")
    content_payload["visual_evidence"] = content_payload.pop(
        "renderable_story_beats"
    )
    content_payload["frozen_moment"] = content_payload.pop("decisive_moment")
    content_payload["subject_interaction"] = content_payload.pop(
        "content_subject_interaction"
    )
    content_payload["adjacent_frame_difference"] = content_payload.pop(
        "adjacent_shot_distinction"
    )
    content_payload["secondary_subjects"] = [
        {
            "category": "person",
            "name": f"历史次要主体-{index}",
            "identity": "历史契约允许保存",
            "quantity": 1,
            "action": "在背景中工作",
        }
        for index in range(9)
    ]
    payload["fusion_stage_input"]["content_stage_output"] = json.loads(
        json.dumps(content_payload, ensure_ascii=False)
    )

    fusion_payload = payload["fusion_stage_output"]
    fusion_payload.pop("prompt_assembly_version")
    fusion_payload.pop("base_content_prompt")
    fusion_payload.pop("scene_negative_prompt")
    fusion_payload["carrier_and_material_relation"] = fusion_payload.pop(
        "support_carrier_and_material_relation"
    )
    fusion_payload["scene_interaction"] = fusion_payload.pop(
        "visual_identity_scene_interaction"
    )

    request = payload["generation_request"]
    request["request_version"] = "visual_anchor_generation_request.v5"
    request["content_stage_prompt_version"] = "visual_anchor_content_stage.v14"
    request["fusion_stage_prompt_version"] = "visual_anchor_fusion_stage.v12"
    request.pop("prompt_assembly_trace")
    request.pop("identity_forbidden_traits")
    request.pop("target_image_prompt_language")
    return payload


@pytest.mark.asyncio
async def test_real_v14_v12_payload_remains_historical_without_fabricated_fields():
    batch, _ = await _run(_plan())
    payload = _as_legacy_v14_v12_payload(
        batch.frames[0].model_dump(mode="json")
    )

    frame = VisualAnchorTwoStageFrameResult.model_validate(payload)

    assert isinstance(frame.content_stage_output, LegacyContentStageOutputV14)
    assert len(frame.content_stage_output.secondary_subjects) == 9
    assert isinstance(frame.fusion_stage_output, LegacyFusionStageOutputV12)
    assert frame.generation_request.request_version == (
        "visual_anchor_generation_request.v6"
    )
    assert "renderable_story_beats" not in frame.content_stage_output.model_dump()
    assert "base_content_prompt" not in frame.fusion_stage_output.model_dump()


@pytest.mark.asyncio
async def test_regeneration_verifies_legacy_contract_before_upgrading_it(
    monkeypatch,
    tmp_path,
):
    batch, _ = await _run(
        _plan(),
        identity_conditioning_mode="text_profile",
    )
    legacy_payload = _as_legacy_v4_payload(
        batch.frames[0].model_dump(mode="json")
    )
    prompt_plan = _prompt_plan(legacy_payload)
    monkeypatch.setattr(
        visual_anchor_regeneration,
        "get_task_path",
        lambda task_id: str(tmp_path / task_id),
    )

    context = visual_anchor_regeneration.prepare_visual_anchor_regeneration(
        prompt_plan=prompt_plan,
        task_id="regenerated-task",
    )

    assert context is not None
    assert context.generation_request.task_id == "regenerated-task"
    assert (
        context.generation_request.request_version
        == "visual_anchor_generation_request.v6"
    )
    restored_payload = context.frame_result.model_dump(mode="json")
    assert "renderable_story_beats" not in restored_payload["content_stage_output"]
    assert "identity_prompt_clause" not in restored_payload["fusion_stage_output"]
    assert context.generation_request.identity_reference_condition is None
    assert not (context.task_root / "reference_image").exists()


@pytest.mark.asyncio
async def test_regeneration_rejects_tampered_raw_contract_before_normalization(
    monkeypatch,
    tmp_path,
):
    batch, _ = await _run(
        _plan(),
        identity_conditioning_mode="text_profile",
    )
    original_payload = _as_legacy_v4_payload(
        batch.frames[0].model_dump(mode="json")
    )
    original_digest = _contract_digest(original_payload)
    tampered_payload = json.loads(json.dumps(original_payload, ensure_ascii=False))
    tampered_payload["fusion_stage_output"]["self_check_failures"] = ["已篡改"]
    prompt_plan = _prompt_plan(
        tampered_payload,
        contract_digest=original_digest,
    )
    monkeypatch.setattr(
        visual_anchor_regeneration,
        "get_task_path",
        lambda task_id: str(tmp_path / task_id),
    )

    with pytest.raises(ValueError, match="contract digest differs"):
        visual_anchor_regeneration.prepare_visual_anchor_regeneration(
            prompt_plan=prompt_plan,
            task_id="regenerated-task",
        )
