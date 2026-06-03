from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_expression import VisualExpressionMode
from pixelle_video.services.series_visual_signature_profile_builder import (
    SeriesVisualSignatureProfileBuilder,
)
from pixelle_video.services.visual_expression_classifier import VisualExpressionClassifier


def _profile(name: str, *, ip_type: str = "", visual_summary: str = "") -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id=name,
        workspace_id="ws",
        project_id="prj",
        name=name,
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        ip_type=ip_type,
        visual_summary=visual_summary or name,
        identity_anchors=(name,),
    )


def test_series_visual_signature_profile_builder_supports_human_host():
    profile = SeriesVisualSignatureProfileBuilder().build(_profile("人类主持人", ip_type="human"))
    assert "人类主持人" in profile.identity_kernel
    assert "固定主持人" in profile.primary_role_affordances


def test_series_visual_signature_profile_builder_supports_red_beaked_sparrow():
    profile = SeriesVisualSignatureProfileBuilder().build(_profile("红嘴麻雀", ip_type="animal"))
    assert "红嘴麻雀" in profile.identity_kernel
    assert "故事行动者" in profile.primary_role_affordances


def test_series_visual_signature_profile_builder_supports_airplane():
    profile = SeriesVisualSignatureProfileBuilder().build(_profile("飞机", ip_type="vehicle"))
    assert "飞机" in profile.identity_kernel
    assert "运动主体" in profile.primary_role_affordances


def test_series_visual_signature_profile_builder_supports_stone_object():
    profile = SeriesVisualSignatureProfileBuilder().build(_profile("石头", ip_type="object"))
    assert "石头" in profile.identity_kernel
    assert "隐喻主体" in profile.primary_role_affordances


def test_visual_expression_classifier_respects_user_selected_mode():
    brief = BaseVisualBrief(frame_id="f1", core_message="内容", visual_moment="普通画面")
    decision = VisualExpressionClassifier().classify_frame(
        frame_context={},
        base_visual_brief=brief,
        series_visual_signature_expression_mode="infographic_layout",
    )
    assert decision.expression_mode is VisualExpressionMode.INFOGRAPHIC_LAYOUT
    assert decision.source == "user"


def test_visual_expression_classifier_auto_detects_explanatory_diagram():
    brief = BaseVisualBrief(frame_id="f1", core_message="解释流程", visual_moment="展示机制和步骤")
    decision = VisualExpressionClassifier().classify_frame(frame_context={}, base_visual_brief=brief)
    assert decision.expression_mode is VisualExpressionMode.EXPLANATORY_DIAGRAM
