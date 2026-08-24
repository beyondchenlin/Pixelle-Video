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
        prompt_scope="ordinary_content_only",
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


def test_ordinary_image_prompt_projects_world_article_route_and_reference_into_allowed_sections():
    prompt = build_image_prompt_prompt(
        narrations=["原因推动结果发生变化。"],
        min_words=30,
        max_words=60,
        prompt_contexts=PromptContextEnvelope(
            plan_context={
                "plan_source_text": "不允许携带整篇文章。",
                "generation_world_profile": {
                    "summary": "古城清晨的因果讲解",
                    "visual_environment": "城门前的石板路",
                    "story_constraints": "长乐门必须保留",
                },
                "reference_image": {
                    "subject_summary": "白色短毛小狗",
                    "identity_anchors": ["左耳有棕色斑点"],
                    "composition_summary": "主体位于画面中央",
                    "style_summary": "参考图水彩风格不得进入内容阶段",
                },
            },
            frame_contexts=[
                {
                    "frame_source_text": "原因推动结果发生变化。",
                    "primary_subject": "齿轮装置",
                    "selected_visual_route": {
                        "visual_premise": "展示一个原因驱动一个结果",
                        "frame_storytelling_logic": "从左向右阅读",
                        "style_family": "不得进入内容阶段的风格族",
                    },
                    "article_concretization_plan": {
                        "anchor": {
                            "anchor_claim": "原因驱动结果",
                            "main_entities": ["原因齿轮", "结果齿轮"],
                        },
                        "diagram": {
                            "grammar": "process_flow",
                            "visual_metaphor": "啮合齿轮",
                            "composition_rules": ["左右因果布局"],
                            "visible_text": {
                                "effective_policy": "approved_labels_only",
                                "allowed_visible_text": ["原因", "结果"],
                            },
                        },
                    },
                }
            ],
        ),
        prompt_language="zh_CN",
        prompt_scope="ordinary_content_only",
    )

    for expected in (
        "白色短毛小狗",
        "左耳有棕色斑点",
        "原因驱动结果",
        "展示一个原因驱动一个结果",
        "古城清晨的因果讲解",
        "长乐门必须保留",
        "process_flow",
        "左右因果布局",
        "主体位于画面中央",
    ):
        assert expected in prompt
    assert "不允许携带整篇文章" not in prompt
    assert "参考图水彩风格不得进入内容阶段" not in prompt
    assert "不得进入内容阶段的风格族" not in prompt
    assert "generation_world_profile" not in prompt
    assert "article_concretization_plan" not in prompt


def test_full_context_scope_preserves_existing_direct_call_contract():
    prompt = build_image_prompt_prompt(
        narrations=["一只小狗越过水坑。"],
        min_words=30,
        max_words=60,
        style_profile={"consistency_anchor": "LEGACY_STYLE_MARKER"},
        prompt_contexts=PromptContextEnvelope(
            plan_context={"plan_source_text": "完整上下文仍应保留"},
            frame_contexts=[{"frame_source_text": "一只小狗越过水坑。"}],
        ),
    )

    assert "LEGACY_STYLE_MARKER" in prompt
    assert "完整上下文仍应保留" in prompt
    assert "ordinary_image_generation" not in prompt
