import asyncio

from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_anchor_integration import (
    VisualAnchorIntegrationCandidateResponse,
    VisualAnchorIntegrationPlanResponse,
    VisualAnchorIntegrationResponse,
)
from pixelle_video.models.visual_anchor_planning import AnchorProminence
from pixelle_video.services.visual_anchor_integration_planner import VisualAnchorIntegrationPlanner


class FakeLLM:
    async def __call__(self, **kwargs):
        return VisualAnchorIntegrationResponse(
            visual_anchor_integration_plans=[
                VisualAnchorIntegrationPlanResponse(
                    frame_id="f1",
                    candidates=[
                        VisualAnchorIntegrationCandidateResponse(
                            carrier_type="embedded_mark",
                            anchor_function="embedded_mark",
                            prominence="embedded_mark",
                            style_relation="blended",
                            placement="书页右下角",
                            support_anchor="打开的书页纸面",
                            contact_relation="贴合纸张",
                            interaction_target="书页",
                            occlusion_relation="不遮挡正文",
                            visual_weight_clause="低对比、低存在感，作为纸面材质细节",
                            image_prompt_clause="书页右下角印着一个极小的蓝领结白兔轮廓浅压印纹章，像出版社小徽记，贴合纸张纹理，不影响主体画面。",
                            scene_coherence_score=10,
                            disruption_risk=1,
                            identity_preservation_score=9,
                            reason="low disruption",
                        )
                    ],
                    selected_index=0,
                )
            ]
        )


def test_visual_anchor_integration_planner_uses_llm_candidate():
    profile = IPProfile(
        ip_profile_id="rabbit",
        workspace_id="ws",
        project_id="prj",
        name="科技兔子",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="一只白色科技兔子，蓝色领结，长耳朵，圆润脸型",
    )
    brief = BaseVisualBrief(
        frame_id="f1",
        core_message="书籍介绍",
        visual_moment="一本打开的书页展示家族故事。",
        main_subjects=("《百年孤独》书页",),
        base_image_prompt="一本打开的书页展示家族故事。",
    )
    plans = asyncio.run(
        VisualAnchorIntegrationPlanner(llm_service=FakeLLM()).plan_batch(
            base_visual_briefs=(brief,),
            anchor_profile=profile,
        )
    )
    assert plans[0].anchor_prominence is AnchorProminence.EMBEDDED_MARK
    assert "蓝领结白兔" in plans[0].image_prompt_clause
    assert "浅压印纹章" in plans[0].image_prompt_clause
    assert "角标" not in plans[0].image_prompt_clause
    assert "水印" not in plans[0].image_prompt_clause
    assert "视觉锚点" not in plans[0].image_prompt_clause
