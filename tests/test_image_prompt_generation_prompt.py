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
