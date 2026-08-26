from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.config.prompt_prefix_library import image_prompt_prefix_revision
from pixelle_video.models.series_visual_signature import (
    series_visual_signature_identity_content_sha256,
)
from pixelle_video.models.storyboard import StoryboardConfig, StoryboardFrame
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_anchor_two_stage import (
    ContentStageModelOutput,
    FinalizationStagePromptPassthrough,
    FusionStageModelOutput,
    ImageWorkflowExecutionContract,
    TargetVisualStyle,
    VisibleTextPolicy,
    VisualAnchorIdentityProfile,
)
from pixelle_video.prompt_language import CHINESE_PROMPT_LANGUAGE
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.visual_anchor_two_stage_service import (
    VisualAnchorTwoStageService,
)
from pixelle_video.services.visual_prompt_composer import (
    VisualPromptComposer,
    _resolve_visual_anchor_style_batch,
    _target_visual_style_contract,
    _uniform_style_fragments,
    _visible_text_policy,
)

_STYLE_POSITIVE = [
    "整幅画采用极简黑白二维线稿插画",
    "整幅画使用细而干净的黑色轮廓、大面积白色留白和少量平面浅灰",
    "人物、物体和环境使用协调的线稿语言",
    "人物面部只用少量轮廓线概括",
    "材质和光影采用二维平面线条以及黑、白、浅灰纯色块表现",
]
_STYLE_NEGATIVE = [
    "画面中的彩色元素",
    "画面中的照片纹理",
    "人物的真实皮肤明暗",
    "画面中的连续渐变",
    "画面中的体积光",
    "画面中的三维材质",
]
_NO_TEXT_POSITIVE = "画面中禁止出现任何可见文字、标题、水印或乱码"
_NO_TEXT_NEGATIVE = "文字，水印，标题，乱码"


class _QueuedLLM:
    def __init__(self, responses):
        self.responses = {
            response_type: list(values)
            for response_type, values in responses.items()
        }
        self.calls = []
        self.last_fusion_response = ""

    async def __call__(self, *, prompt, response_type, **kwargs):
        self.calls.append(
            {
                "prompt": prompt,
                "response_type": response_type,
                "kwargs": kwargs,
            }
        )
        queue_key = response_type
        if queue_key is None and queue_key not in self.responses:
            if "最终图片提示词审核与修复编辑" in prompt:
                queue_key = FinalizationStagePromptPassthrough
            elif "视觉融合导演" in prompt:
                queue_key = FusionStageModelOutput
            else:
                queue_key = ContentStageModelOutput
        if (
            queue_key is FinalizationStagePromptPassthrough
            and queue_key not in self.responses
        ):
            return self.last_fusion_response
        response = self.responses[queue_key].pop(0)
        if isinstance(response, str):
            rendered = response
        elif hasattr(response, "model_dump_json"):
            rendered = response.model_dump_json()
        else:
            rendered = json.dumps(response, ensure_ascii=False)
        if queue_key is FusionStageModelOutput:
            self.last_fusion_response = rendered
        return rendered


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
            4,
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
        "平视中景中，乔布斯和沃兹尼亚克在车库工作台两侧同时连接苹果一号电脑的电路板，前景散落焊锡和工具，中景双手与电路连接处成为视觉焦点，背景车库门和储物架建立创业环境。",
        "略低机位中景中，乔布斯在发布台上单手揭开麦金塔电脑，前景观众肩部形成框景，中景电脑屏幕与他的展示手势成为视觉焦点，背景舞台灯光建立发布事件。",
        "斜侧广角中，乔布斯和苹果团队把iMac、iPod和iPhone模型依次放上延伸的展示台，前景最新产品、中景正在放置产品的团队、背景较早产品形成清晰时间层次。",
        "低机位广角中，年轻人的前脚刚越过起跑线，手臂向前摆动，前景起跑线、中景迈步人物、背景由苹果产品和关键事件组成的道路共同指向前方。",
    )
    shot_purposes = (
        "让观众看清两位创始人通过共同组装电脑开启创业行动",
        "让观众看清乔布斯把新电脑正式展示给市场",
        "让观众看清团队用连续产品推动技术道路前进",
        "把乔布斯故事转化为普通人开始行动的具体瞬间",
    )
    frozen_moments = (
        "两人的手同时停在刚接通的苹果一号电路板两侧",
        "乔布斯掀开遮布后手掌指向已经亮起的麦金塔电脑",
        "团队成员正把三代产品分别放入展示台的连续节点",
        "年轻人的前脚刚越过起跑线，后脚仍压在线后",
    )
    subject_interactions = (
        "两位创始人共同操作工作台上的同一台苹果一号电脑",
        "乔布斯以展示手势把观众注意力引向麦金塔电脑",
        "乔布斯和团队共同摆放三代产品形成前后承接关系",
        "年轻人的脚步跨过起跑线并进入产品事件形成的道路",
    )
    composition_plans = (
        {
            "shot_scale_and_camera": "平视中景，工作台横向贯穿画面",
            "foreground": "散落的焊锡、螺丝和工具",
            "midground": "两位创始人与苹果一号电脑",
            "background": "车库门、储物架和暖色工作灯",
            "visual_focus": "两人的手与刚接通的电路板",
        },
        {
            "shot_scale_and_camera": "略低机位中景，发布台形成视觉中心",
            "foreground": "虚化的观众肩部轮廓",
            "midground": "乔布斯、展示手势和麦金塔电脑",
            "background": "简洁舞台与定向灯光",
            "visual_focus": "亮起的电脑屏幕与乔布斯手势",
        },
        {
            "shot_scale_and_camera": "斜侧广角，展示台向画面深处延伸",
            "foreground": "最新一代产品",
            "midground": "正在摆放产品的乔布斯和团队",
            "background": "较早产品和延伸的展示空间",
            "visual_focus": "团队手部与三个产品节点的连接关系",
        },
        {
            "shot_scale_and_camera": "贴近地面的低机位广角",
            "foreground": "被前脚跨过的起跑线",
            "midground": "开始迈步的年轻人",
            "background": "由产品和关键事件形成的未来道路",
            "visual_focus": "越过起跑线的前脚",
        },
    )
    adjacent_differences = (
        "以双人手部组装动作建立开端，区别于后一镜的单人公开展示",
        "以舞台揭幕和观众视角区别于前一镜的车库协作与后一镜的团队产品序列",
        "以多人共同摆放产品和纵深时间线区别于相邻镜头的单一事件",
        "从乔布斯本人切换为普通年轻人，并以跨线动作完成主题落点",
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
    for (
        _frame,
        spec,
        pure_prompt,
        event_spec,
        shot_purpose,
        frozen_moment,
        subject_interaction,
        composition_plan,
        adjacent_difference,
    ) in zip(
        plan.frames,
        subject_specs,
        pure_prompts,
        event_specs,
        shot_purposes,
        frozen_moments,
        subject_interactions,
        composition_plans,
        adjacent_differences,
    ):
        (
            primary_name,
            _primary_source,
            primary_quantity,
            primary_action,
            secondary_name,
            _secondary_source,
            secondary_action,
        ) = spec
        event_source, _event_prompt, event_category = event_spec
        outputs.append(
            ContentStageModelOutput(
                core_claim=pure_prompt,
                shot_purpose=shot_purpose,
                renderable_story_beats=[frozen_moment, subject_interaction],
                decisive_moment=frozen_moment,
                primary_subject={
                    "category": "person",
                    "name": primary_name,
                    "identity": "分镜原文中的真正叙事人物",
                    "quantity": primary_quantity,
                    "action": primary_action,
                },
                secondary_subjects=[
                    {
                        "category": "product",
                        "name": secondary_name,
                        "identity": "分镜原文中的产品、技术或道路系统",
                        "quantity": 1,
                        "action": secondary_action,
                    }
                ],
                content_subject_interaction=subject_interaction,
                composition_plan=composition_plan,
                adjacent_shot_distinction=adjacent_difference,
                scene_facts=[
                    {
                        "category": event_category,
                        "statement": event_source,
                    }
                ],
                adjustable_non_core_content=["非核心环境道具", "辅助光影层次"],
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
    serialized_contract = contract.model_dump_json()
    for out_of_scope_term in ("视觉身份", "频道标记", "承载对象", "纯内容"):
        assert out_of_scope_term not in serialized_contract


def test_requested_style_id_preserves_complete_contract_when_active_style_changes():
    batch = _resolve_visual_anchor_style_batch(
        image_config={
            "prompt_prefix_library": {
                "active_prefix_id": "builtin_childrens_storybook_warm",
                "items": [
                    {
                        "id": "builtin_childrens_storybook_warm",
                        "content": "warm children's storybook illustration",
                    },
                    {
                        "id": "builtin_line_art_emotion_minimal",
                        "content": "minimal line art, negative space, monochrome illustration",
                    },
                ],
            }
        },
        prompt_prefix=None,
        image_style_id="builtin_line_art_emotion_minimal",
        image_style_revision=image_prompt_prefix_revision(
            "minimal line art, negative space, monochrome illustration"
        ),
        frame_count=1,
    )

    contract = _target_visual_style_contract(
        batch=batch,
        visual_profile_snapshot=None,
        prompt_language=CHINESE_PROMPT_LANGUAGE,
    )

    assert batch.resolved_style is not None
    assert batch.resolved_style.source_identity == (
        "library:builtin_line_art_emotion_minimal"
    )
    assert contract.required_final_prompt_fragments == _STYLE_POSITIVE
    assert contract.required_negative_prompt_fragments == _STYLE_NEGATIVE


def test_z_image_style_contract_keeps_local_avoidance_rules_for_scoped_rewrite():
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
    )

    assert contract.required_final_prompt_fragments == _STYLE_POSITIVE
    assert contract.required_negative_prompt_fragments == _STYLE_NEGATIVE


def test_custom_style_is_uniform_before_entering_the_model_contract():
    assert _uniform_style_fragments(
        fragments=["克制的水墨插画"],
        prompt_language=CHINESE_PROMPT_LANGUAGE,
    ) == [
        "整幅画统一应用以下风格：克制的水墨插画"
    ]


def test_custom_style_is_uniform_in_english():
    assert _uniform_style_fragments(
        fragments=["restrained ink-wash illustration"],
        prompt_language="English",
    ) == [
        "apply the following style uniformly to the whole image: "
        "restrained ink-wash illustration"
    ]


def test_fusion_template_allows_required_style_and_text_prohibitions():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_fusion_stage.md"
    ).read_text(encoding="utf-8")

    assert "target_visual_style 是整幅画的统一风格" in template
    assert "visible_text_policy" in template
    assert "只输出完整融合提示词草稿原文" in template
    assert "不输出标题、分析、解释、候选、字段" in template


def test_content_template_requests_no_proof_or_self_check_fields():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_content_stage.md"
    ).read_text(encoding="utf-8")

    assert "输出一段完整的当前分镜图片提示词原文" in template
    for removed_field in (
        "shot_purpose",
        "renderable_story_beats",
        "decisive_moment",
        "content_subject_interaction",
        "composition_plan",
        "source_evidence",
        "pure_content_prompt_evidence",
        "protected_facts",
        "self_check",
        "self_check_failures",
    ):
        assert removed_field not in template


def test_content_template_enforces_general_renderability_and_source_fidelity():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_content_stage.md"
    ).read_text(encoding="utf-8")

    for required_rule in (
        "original_storyboard_text 是当前画面的事实依据",
        "article_context 用于确认身份、指代、因果和必要背景",
        "唯一需要观众看懂的核心信息",
        "视觉表现力最强的静止瞬间",
        "把抽象内容转化成能够直接看到的动作、物证、人物关系、空间状态、尺度对比或结果瞬间",
        "围绕一个视觉中心设计主体、动作、环境、景别、视角",
        "相邻镜头通过动作阶段、物证、景别、视角、构图或视觉焦点形成清楚区别",
        "target_visual_style 从画面构思开始统一作用",
        "输出前静默确认画面事实、静止瞬间、视觉中心、空间关系、目标风格和相邻镜头区别完整一致",
    ):
        assert required_rule in template
    for out_of_scope_or_negative_rule in (
        "纯内容",
        "视觉身份",
        "频道标记",
        "记忆符号",
        "承载对象",
        "禁止",
        "不得",
        "不要",
        "不使用",
        "不输出",
        "不包含",
        "不依靠",
        "不虚构",
        "不照抄",
        "不覆盖",
    ):
        assert out_of_scope_or_negative_rule not in template


def test_fusion_template_requests_only_raw_draft_text():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_fusion_stage.md"
    ).read_text(encoding="utf-8")

    assert "根据当前画面重新创作一段完整的融合提示词" in template
    assert "只输出完整融合提示词草稿原文" in template
    for removed_field in (
        "selected_fusion_method",
        "final_manifestation",
        "protected_fact_checks",
        "identity_trait_checks",
        "single_instance_prompt_evidence",
        "self_check",
    ):
        assert removed_field not in template


def test_fusion_template_keeps_facts_fixed_and_restores_whole_scene_recomposition():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_fusion_stage.md"
    ).read_text(encoding="utf-8")

    for required_rule in (
        "original_storyboard_text 是画面主旨和事实边界",
        "content_stage_output.raw_prompt 是已经按照 target_visual_style 创作的纯内容画面",
        "整幅画只出现一个可识别的视觉身份实例",
        "不得概括、省略或改写",
        "视觉身份的主要作用是形成系列视觉记忆",
        "不默认成为剧情主体",
        "全部固定身份特征和固定配色各写一次",
        "其他句子不得重复",
        "不得另写容易再次触发身份形象的否定句",
        "最终只选择一种最自然的表现方式",
        "不要预设表现类型、固定位置、固定尺寸或固定景深",
        "不得在纯内容画面末尾机械追加视觉身份",
        "使视觉身份像从一开始就属于该场景",
        "不得补充只为承载视觉身份而存在的物体",
        "采用实体角色或物体时",
        "采用画内图形时",
        "target_visual_style 是整幅画的统一风格",
        "一致作用于人物、物体、环境、场景载体和视觉身份",
        "独立场景只根据当前画面选择，不参考其他独立镜头",
        "target_visual_style 中的排除要求必须改写成唯一允许的正向画面状态",
        "最终不得同时出现允许和禁止同一属性的文字",
    ):
        assert required_rule in template

    assert "最终提示词必须把 identity_profile.display_name 的实际值代入" not in template


def test_fusion_template_does_not_limit_carriers_with_examples():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_fusion_stage.md"
    ).read_text(encoding="utf-8")

    for forbidden_example in (
        "服装印刷",
        "刺绣",
        "压印",
        "材质图形",
        "产品图形",
        "道具徽记",
        "标识化摆件",
        "雕刻",
        "环境局部标识",
        "屏保或无文字界面图形",
    ):
        assert forbidden_example not in template
    assert "例如" not in template


def test_fusion_template_restores_v11_open_scene_choice_without_v15_biases():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_fusion_stage.md"
    ).read_text(encoding="utf-8")

    for required_rule in (
        "整幅画只出现一个可识别的视觉身份实例",
        "最终只选择一种最自然的表现方式",
        "不要预设表现类型、固定位置、固定尺寸或固定景深",
        "不得在纯内容画面末尾机械追加视觉身份",
    ):
        assert required_rule in template
    for removed_bias in (
        "最容易被当前图片工作流一次生成正确",
        "画面中仅出现一个〈身份名称〉",
        "连续纹样、镜像复制、背景复制",
        "满版印花、散点纹样和多处复制",
        "所有禁止项，都必须转换成正向提示词末尾的直接排除句",
    ):
        assert removed_bias not in template
    for removed_fusion_field in (
        "identity_prompt_clause",
        "relative_scale_and_visual_weight",
        "support_carrier_and_material_relation",
        "visual_identity_scene_interaction",
    ):
        assert removed_fusion_field not in template
    assert "服务端会按" not in template


def test_finalization_template_repairs_current_facts_without_copying_history():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_finalization_stage.md"
    ).read_text(encoding="utf-8")

    for required_rule in (
        "original_storyboard_text 是当前画面的事实边界",
        "article_context 只用于核对身份、指代、因果和必要背景",
        "第二次输出是加入视觉身份后的融合候选稿",
        "不得默认 fusion_stage_output.raw_prompt 正确",
        "不得只做润色、缩句或调整顺序",
        "不得因为原文未逐项描述就一律删除",
        "series_final_prompt_history 只用于了解最近三个最终提示词中的表现形态和融合关系",
        "不得为了制造差异而改变自然的融合方案或额外添加物体",
        "连续场景优先保持表现形态、空间关系和画面连续性",
    ):
        assert required_rule in template


def test_finalization_template_unifies_scene_and_signature_styles():
    template = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates/visual_anchor_finalization_stage.md"
    ).read_text(encoding="utf-8")

    for required_rule in (
        "统一作用于内容主体、环境、承载对象和视觉身份",
        "不得概括、省略或改写",
        "视觉身份的主要作用是形成系列视觉记忆",
        "不预设它必须采用实体角色或表面图形",
        "全部固定身份特征和固定配色各写一次",
        "其他句子不得重复",
        "不得另写容易再次触发身份形象的否定句",
        "符合当前场景的年代和用途",
        "采用实体角色或物体时必须有合理支撑和接触关系",
        "采用画内图形时必须自然附着",
        "删除仅为安置视觉身份而出现",
        "你的原始输出将直接作为图片正向提示词",
        "只输出最终图片提示词原文",
        "不得照抄禁止项清单",
        "最终文本不得同时允许和禁止同一属性",
        "事实审核",
        "风格审核",
        "视觉身份审核",
        "空间审核",
        "文字审核",
        "任一审核项不通过，都必须在本次输出中直接修复",
        "不能照抄融合候选稿",
    ):
        assert required_rule in template
    assert "visual_signature_style" not in template
    assert "视觉身份独立风格" not in template
    for forbidden_output in (
        "输出通过结论",
        "输出失败结论",
        "服务端会检查",
    ):
        assert forbidden_output not in template


def test_fusion_and_finalization_keep_visual_signature_secondary_without_ratios():
    template_root = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates"
    )
    templates = (
        (template_root / "visual_anchor_fusion_stage.md").read_text(
            encoding="utf-8"
        ),
        (template_root / "visual_anchor_finalization_stage.md").read_text(
            encoding="utf-8"
        ),
    )

    for template in templates:
        for required_rule in (
            "次级系列视觉记忆点",
            "不默认成为剧情主体",
            "主体始终先被看见",
            "清楚可辨但不抢夺主旨",
        ):
            assert required_rule in template
        for forbidden_ratio in ("2%", "5%", "8%", "百分比"):
            assert forbidden_ratio not in template


def test_fusion_and_finalization_use_relative_emphasis_without_numeric_examples():
    template_root = (
        Path(__file__).resolve().parents[2]
        / "pixelle_video/prompts/templates"
    )
    templates = (
        (template_root / "visual_anchor_fusion_stage.md").read_text(
            encoding="utf-8"
        ),
        (template_root / "visual_anchor_finalization_stage.md").read_text(
            encoding="utf-8"
        ),
    )

    for template in templates:
        for required_rule in (
            "visual_signature_emphasis",
            "只控制视觉身份相对主体的识别强弱",
            "主体始终先被看见",
        ):
            assert required_rule in template
        assert "例如" not in template


def test_disabled_image_text_maps_to_title_watermark_and_garbled_text_guards():
    policy = _visible_text_policy(
        {"image_text": {"suppress_embedded_text": True}},
        prompt_language=CHINESE_PROMPT_LANGUAGE,
    )

    assert policy.suppress_visible_text is True
    assert policy.required_positive_prompt_fragment == _NO_TEXT_POSITIVE
    assert policy.required_negative_prompt_fragment == _NO_TEXT_NEGATIVE


def test_visible_text_policy_keeps_prompt_fragments_as_model_input():
    policy = _text_policy()
    assert policy.required_positive_prompt_fragment == _NO_TEXT_POSITIVE
    assert policy.required_negative_prompt_fragment == _NO_TEXT_NEGATIVE


def _fusion_outputs(
    contents: list[ContentStageModelOutput],
) -> list[FusionStageModelOutput]:
    fusion_specs = (
        (
            "服装刺绣",
            "沃兹尼亚克工作衬衫胸袋上的斑点狗刺绣",
            "巴掌大小，视觉权重低于两位创始人的手部和苹果一号电脑",
            "棉质衬衫胸袋上的黑白线迹刺绣，随布料褶皱弯曲",
            "刺绣随沃兹尼亚克俯身组装电脑的姿态产生自然形变",
            "一枚巴掌大小的斑点狗头像以黑白线迹刺绣在沃兹尼亚克工作衬衫胸袋上，黑色墨镜清晰可辨，刺绣随棉质布料褶皱自然弯曲，只出现这一处",
        ),
        (
            "讲台金属压印",
            "发布台侧面板上的斑点狗浅浮雕压印",
            "手掌大小，作为低权重舞台细节，不与麦金塔电脑争夺焦点",
            "拉丝金属发布台侧面板上的浅浮雕压印，边缘反射舞台侧光",
            "压印固定在乔布斯展示手势下方的发布台表面",
            "发布台侧面板上有一枚手掌大小的斑点狗浅浮雕压印，斑点轮廓和黑色墨镜清晰，压印服从拉丝金属透视并反射舞台侧光，只出现这一处",
        ),
        (
            "产品展示摆件",
            "产品展示台上的斑点狗小型摆件",
            "约为iPod高度的一半，视觉权重低于三代产品和团队动作",
            "哑光陶瓷摆件由展示台支撑，底部形成短小接触阴影",
            "摆件位于产品节点之间，朝向团队正在放置的最新产品",
            "展示台上放着一只约为iPod高度一半的哑光陶瓷斑点狗摆件，黑色墨镜和斑点特征清晰，底部有短小接触阴影，朝向团队正在放置的最新产品，只出现这一只",
        ),
        (
            "背包织物贴章",
            "年轻人背包肩带上的斑点狗织物贴章",
            "两指宽，作为随人物行动的低权重身份细节",
            "织物贴章缝在背包肩带外侧，随肩带弧度弯曲并承接晨光",
            "贴章随年轻人跨过起跑线时摆动的肩带一起向前倾斜",
            "年轻人背包肩带外侧缝着一枚两指宽的斑点狗织物贴章，斑点和黑色墨镜清晰，贴章随肩带弧度与迈步摆动自然弯曲，只出现这一处",
        ),
    )
    outputs = []
    for content, fusion_spec in zip(contents, fusion_specs):
        (
            method,
            manifestation,
            scale_and_weight,
            carrier_and_material,
            interaction,
            _identity_clause_example,
        ) = fusion_spec
        outputs.append(
            FusionStageModelOutput(
                selected_fusion_method=method,
                final_manifestation=manifestation,
                relative_scale_and_visual_weight=scale_and_weight,
                support_carrier_and_material_relation=carrier_and_material,
                visual_identity_scene_interaction=interaction,
                spatial_contact_and_lighting_relation=(
                    "根据当前画面的透视、光照、材质、支撑和遮挡关系自然融合"
                ),
                inherited_existing_fusion_decision=False,
                continuity_change_reason="",
                scene_negative_prompt="",
            )
        )
    return outputs


def _identity() -> VisualAnchorIdentityProfile:
    digest = series_visual_signature_identity_content_sha256(
        display_name="斑点狗",
        core_identity_traits=["斑点狗", "黑色墨镜"],
        supporting_identity_traits=["温和神态"],
        forbidden_traits=["变成人类", "继承主要人物身份"],
    )
    return VisualAnchorIdentityProfile(
        profile_id="dog-anchor",
        display_name="斑点狗",
        core_identity_traits=["斑点狗", "黑色墨镜"],
        supporting_identity_traits=["温和神态"],
        forbidden_traits=["变成人类", "继承主要人物身份"],
        source_asset_ids=[],
        identity_content_sha256=digest,
        identity_resource_version=f"identity:dog-anchor:{digest}",
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
    fusions = _fusion_outputs(model_contents)
    llm = _QueuedLLM(
        {
            ContentStageModelOutput: model_contents,
            FusionStageModelOutput: fusions,
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
async def test_jobs_life_three_stage_contract_preserves_subjects_style_and_text_policy():
    plan, result, llm = await _run_jobs_sample()

    assert len(llm.calls) == len(plan.frames) * 3
    content_calls = [
        call
        for call in llm.calls
        if "你是一名分镜导演" in call["prompt"]
    ]
    fusion_calls = [
        call for call in llm.calls if "你是一名视觉融合导演" in call["prompt"]
    ]
    finalization_calls = [
        call
        for call in llm.calls
        if "你是一名最终图片提示词审核与修复编辑" in call["prompt"]
    ]
    assert (
        len(content_calls)
        == len(fusion_calls)
        == len(finalization_calls)
        == len(plan.frames)
    )
    assert all(call["response_type"] is None for call in llm.calls)
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
        assert '"series_fusion_history": []' in call["prompt"]
        assert '"visual_signature_style"' not in call["prompt"]
    assert sum(
        '"visual_signature_emphasis": "enhanced"' in call["prompt"]
        for call in fusion_calls
    ) == 1
    assert sum(
        '"visual_signature_emphasis": "standard"' in call["prompt"]
        for call in fusion_calls
    ) == len(plan.frames) - 1
    for call in finalization_calls:
        assert '"content_stage_input"' in call["prompt"]
        assert '"article_context"' in call["prompt"]
        assert '"previous_frame_summary"' in call["prompt"]
        assert '"next_frame_summary"' in call["prompt"]
        assert '"fusion_stage_input"' in call["prompt"]
        assert '"fusion_stage_output"' in call["prompt"]
        assert '"series_final_prompt_history"' in call["prompt"]
        assert '"visual_signature_style"' not in call["prompt"]
    assert sum(
        '"visual_signature_emphasis": "enhanced"' in call["prompt"]
        for call in finalization_calls
    ) == 1

    expected_contents = _content_outputs(plan)
    expected_fusions = _fusion_outputs(expected_contents)
    for frame_result, expected_content, expected_fusion in zip(
        result.frames,
        expected_contents,
        expected_fusions,
    ):
        content = frame_result.content_stage_output
        request = frame_result.generation_request
        assert content.pure_content_prompt == expected_content.model_dump_json()
        assert (
            frame_result.fusion_stage_output.final_positive_prompt
            == expected_fusion.model_dump_json()
        )
        assert request.final_positive_prompt == expected_fusion.model_dump_json()
        assert request.identity_conditioning_mode == "text_profile"
        assert request.identity_reference_condition is None
        assert request.final_negative_prompt == ""
        assert request.prompt_assembly_trace is None

    composer_source = inspect.getsource(VisualPromptComposer.compose)
    assert "base_image_prompt" not in composer_source


@pytest.mark.asyncio
async def test_jobs_life_model_fusion_generates_each_frame_exactly_once(
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
