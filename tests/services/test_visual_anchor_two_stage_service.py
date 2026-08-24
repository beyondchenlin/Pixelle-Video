import hashlib

import pytest
from pydantic import ValidationError

from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_anchor_two_stage import (
    ContentStageModelOutput,
    FusionStageOutput,
    IdentityReferenceCondition,
    ImageWorkflowExecutionContract,
    VisualAnchorIdentityProfile,
    VisualAnchorImageGenerationRequest,
)
from pixelle_video.services.visual_anchor_two_stage_service import (
    VisualAnchorTwoStageService,
    _materialize_content_stage_output,
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
        primary_subject={
            "category": "person",
            "name": "由模型判断的主体",
            "identity": "模型自行给出的身份",
            "quantity": 1,
            "action": "",
        },
        secondary_subjects=[],
        scene_facts=[{"category": "event", "statement": source_text}],
        adjustable_non_core_content=["背景"],
        pure_content_prompt="由模型直接生成的纯内容画面",
    )


def _fusion(frame_id, *, inherited=False, negative_prompt=""):
    return FusionStageOutput(
        selected_fusion_method=f"模型选择的融合方式 {frame_id}",
        final_manifestation=f"模型选择的表现形态 {frame_id}",
        spatial_contact_and_lighting_relation="模型判断的空间和光照关系",
        inherited_existing_fusion_decision=inherited,
        continuity_change_reason="",
        final_positive_prompt="模型直接给出的最终图片提示词",
        final_negative_prompt=negative_prompt,
    )


async def _run(plan, *, fusions=None, stage_callback=None):
    contents = [_content(frame.frame_id, frame.source_text) for frame in plan.frames]
    fusion_outputs = fusions or [
        _fusion(frame.frame_id, inherited=index > 0)
        for index, frame in enumerate(plan.frames)
    ]
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: contents,
            FusionStageOutput: fusion_outputs,
        }
    )
    result = await VisualAnchorTwoStageService().run_batch(
        llm_service=llm,
        storyboard_plan=plan,
        identity_profile=_identity(),
        identity_reference_condition=_reference(),
        target_visual_style="真实电影感",
        target_image_prompt_language="中文",
        task_id="task-two-stage",
        workflow_key="selfhost/image_z_image_turbo_gguf_reference.json",
        workflow_version_sha256="c" * 64,
        expected_execution=_execution(),
        random_seeds_by_frame={
            frame.frame_id: 101 + index for index, frame in enumerate(plan.frames)
        },
        negative_prompt_supported=False,
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
        FusionStageOutput.model_json_schema(),
        VisualAnchorImageGenerationRequest.model_json_schema(),
    )
    schema_text = str(schemas)
    for field_name in REMOVED_PROOF_FIELDS:
        assert field_name not in schema_text


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
    fusion = FusionStageOutput.model_validate(fusion_payload)
    assert REMOVED_PROOF_FIELDS.isdisjoint(fusion.model_dump(mode="json"))


def test_content_materialization_assigns_ids_without_semantic_judgment():
    output = _materialize_content_stage_output(
        frame_id="frame-a",
        model_output=_content("frame-a", "与输出主体完全无关的原文"),
    )
    assert output.primary_subject.subject_id == "frame-a-subject-primary"
    assert output.primary_subject.name == "由模型判断的主体"
    assert output.scene_facts[0].statement == "与输出主体完全无关的原文"


@pytest.mark.asyncio
async def test_model_output_flows_directly_to_generation_without_semantic_validation():
    result, llm = await _run(
        _plan(),
        fusions=[_fusion("frame-a", negative_prompt="模型仍然输出了反向提示词")],
    )
    frame = result.frames[0]
    assert frame.generation_request.final_positive_prompt == "模型直接给出的最终图片提示词"
    assert frame.generation_request.final_negative_prompt == "模型仍然输出了反向提示词"
    assert len(llm.calls) == 2
    assert all(call["kwargs"]["temperature"] == 0.0 for call in llm.calls)
    assert all(call["kwargs"]["single_request"] is True for call in llm.calls)


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
async def test_continuous_scene_decisions_are_inputs_but_not_locally_judged():
    fusions = [_fusion("frame-a"), _fusion("frame-b", inherited=False)]
    result, _ = await _run(_plan(continuous=True), fusions=fusions)
    second_input = result.frames[1].fusion_stage_input.continuous_scene_context
    assert second_input.existing_selected_fusion_method == fusions[0].selected_fusion_method
    assert result.frames[1].fusion_stage_output == fusions[1]


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
