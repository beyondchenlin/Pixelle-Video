from pixelle_video.models.content_bound_ip import IPParticipationMechanism
from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.services.series_visual_signature_rendering import (
    rendered_identity_clause,
    rendered_identity_terms,
    rendered_provider_action_verb,
    rendered_provider_participation_text,
)


def test_rendered_identity_removes_only_standalone_ascii_display_name() -> None:
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dog",
        core_identity_traits=("hotdog-shaped tag", "Dog with black spots"),
    )

    assert rendered_identity_terms(profile) == (
        "Dog",
        "hotdog-shaped tag",
        "with black spots",
    )
    assert "hotdog-shaped tag" in rendered_identity_clause(profile)


def test_rendered_identity_drops_traits_subsumed_by_more_specific_traits() -> None:
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="斑点狗",
        core_identity_traits=("黑色墨镜", "墨镜", "红色项圈"),
    )

    assert rendered_identity_terms(profile) == ("斑点狗", "黑色墨镜", "红色项圈")


def test_provider_participation_text_rewrites_only_internal_anchor_reference() -> None:
    rendered = rendered_provider_participation_text(
        "导航锚点经过锚点参与后变得清楚；锚点必须通过连接导航锚点完成说明"
    )

    assert rendered == (
        "导航锚点经过指定角色参与后变得清楚；"
        "指定角色必须通过连接导航锚点完成说明"
    )


def test_provider_action_verb_makes_default_conflict_action_single_actor() -> None:
    assert rendered_provider_action_verb(
        "拉住并权衡",
        participation_mechanism=IPParticipationMechanism.CONFLICT_PARTICIPANT,
    ) == "用同一个身体的一只前爪指向对比图中央的分界线并权衡"
    assert rendered_provider_action_verb(
        "指向",
        participation_mechanism=IPParticipationMechanism.CONFLICT_PARTICIPANT,
    ) == "指向"


def test_provider_action_verb_collapses_legacy_timeline_action_to_one_position() -> None:
    rendered = rendered_provider_action_verb(
        "承受并整理",
        participation_mechanism=IPParticipationMechanism.READER_PROXY,
        interaction_target="不同年代的苹果产品和乔布斯职业生涯的不同阶段插图",
        physical_metaphor="从Mac到iPhone的横向时间轴",
    )

    assert rendered == (
        "在整条时间线左下方的单一位置，"
        "用一只前爪指向贯穿全部阶段的同一条总线"
    )


def test_provider_action_verb_separates_one_facilitator_from_group_members() -> None:
    rendered = rendered_provider_action_verb(
        "连接",
        participation_mechanism=IPParticipationMechanism.SYSTEM_COMPONENT,
        interaction_target="设计团队, 讨论, 修改设计方案, 最终定稿",
        physical_metaphor="设计团队围绕讨论桌修改方案",
    )

    assert rendered == (
        "固定站在讨论桌旁的地面上，"
        "用一只前爪指向桌面中央同一份定稿方案"
    )
    assert rendered_provider_action_verb(
        "连接",
        participation_mechanism=IPParticipationMechanism.SYSTEM_COMPONENT,
        interaction_target="设计团队围绕讨论桌",
        user_overrode_action=True,
    ) == "连接"
    assert rendered_provider_action_verb(
        "连接",
        participation_mechanism=IPParticipationMechanism.SYSTEM_COMPONENT,
        interaction_target="技术团队",
        physical_metaphor="团队在会议室讨论服务器架构",
    ) == "连接"
