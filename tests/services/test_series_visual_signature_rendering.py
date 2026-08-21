from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.services.series_visual_signature_rendering import (
    rendered_identity_clause,
    rendered_identity_terms,
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
