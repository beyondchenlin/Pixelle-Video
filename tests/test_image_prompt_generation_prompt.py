from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.prompts.image_generation import build_image_prompt_prompt


def test_image_prompt_prompt_explains_generation_world_profile_contract():
    world_profile = ContentWorldProfile(
        summary="正定古城清晨漫游",
        story_constraints="不能替代长乐门",
        ip_integration_guidance="IP 作为陪伴式向导",
    )
    prompt_contexts = PromptContextEnvelope(
        plan_context={
            "plan_source_text": "从长乐门出发，在正定古城清晨漫游。",
            "generation_world_profile": world_profile.to_dict(),
        },
        frame_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "visual_goal": "表现清晨古城入口和陪伴式向导。",
                "ip_scene_description": "白色卡通兔子站在古城门前",
            }
        ],
    )

    prompt = build_image_prompt_prompt(
        narrations=["从长乐门出发。"],
        min_words=30,
        max_words=60,
        prompt_contexts=prompt_contexts,
        prompt_language="zh_CN",
        visual_anchor_preparation_enabled=True,
    )

    assert "generation_world_profile" in prompt
    assert "正定古城清晨漫游" in prompt
    assert "不能替代长乐门" in prompt
    assert "IP 作为陪伴式向导" in prompt
    assert "use generation_world_profile as the script world profile" in prompt
    assert "refines world_preset" in prompt
    assert "protected original source subject" in prompt
    assert "story_constraints" in prompt
    assert "ip_integration_guidance" in prompt
    assert "ip_scene_description" in prompt
    assert "must not copy internal keys or JSON labels" in prompt


def test_ordinary_image_prompt_keeps_only_frame_subject_action_composition_and_language():
    prompt = build_image_prompt_prompt(
        narrations=["一只小狗越过水坑。"],
        min_words=30,
        max_words=60,
        style_profile={"consistency_anchor": "STYLE_MARKER_MUST_NOT_REPEAT"},
        prompt_contexts=PromptContextEnvelope(
            plan_context={"plan_source_text": "不应进入普通图片提示词的全文"},
            frame_contexts=[
                {
                    "frame_source_text": "一只小狗越过水坑。",
                    "primary_subject": "小狗",
                    "secondary_subjects": ["水坑"],
                    "visual_goal": "表现小狗腾空跳跃",
                    "shot_type": "medium_shot",
                    "generation_world_profile": "不应进入普通图片提示词",
                }
            ],
        ),
        prompt_language="zh_CN",
    )

    assert "一只小狗越过水坑" in prompt
    assert "小狗" in prompt
    assert "表现小狗腾空跳跃" in prompt
    assert "medium_shot" in prompt
    assert "必须使用中文" in prompt
    assert "STYLE_MARKER_MUST_NOT_REPEAT" not in prompt
    assert "plan_source_text" not in prompt
    assert "generation_world_profile" not in prompt
    assert "ip_scene_description" not in prompt
