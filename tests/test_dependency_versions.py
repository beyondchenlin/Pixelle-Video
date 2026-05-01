from pixelle_video.models.artifact import ArtifactVersion, ArtifactVersionStatus
from pixelle_video.models.asset_bible import AssetBible, CharacterProfile, IPProfile
from pixelle_video.models.prompt_plan import ImagePromptDraft, PromptPlan, PromptPlanBundle
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.dependency_versions import DependencyVersionService


def test_asset_bible_version_is_stable_for_same_public_payload():
    service = DependencyVersionService()
    first = AssetBible(
        asset_bible_id="bible_demo",
        workspace_id="workspace_1",
        project_id="project_1",
        ip_profiles=(
            IPProfile(
                ip_profile_id="ip_main",
                workspace_id="workspace_1",
                project_id="project_1",
                name="Pixelle Demo",
                metadata={"last_saved_by": "user_1"},
            ),
        ),
        character_profiles=(
            CharacterProfile(
                character_id="char_luna",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Luna",
            ),
        ),
        metadata={"updated_at": "2026-05-01T10:00:00Z"},
    )
    second = AssetBible.from_dict({
        **first.to_dict(),
        "metadata": {"updated_at": "2026-05-01T11:00:00Z"},
        "ip_profiles": [
            {
                **first.to_dict()["ip_profiles"][0],
                "metadata": {"last_saved_by": "user_2"},
            }
        ],
    })

    assert service.version_for_asset_bible(first) == service.version_for_asset_bible(second)
    assert service.version_for_asset_bible(first).startswith("asset_bible_rev_")
    assert "\\" not in service.version_for_asset_bible(first)
    assert "/" not in service.version_for_asset_bible(first)
    assert "://" not in service.version_for_asset_bible(first)


def test_scene_cast_version_changes_when_business_payload_changes():
    service = DependencyVersionService()
    first = SceneCast(
        scene_cast_id="cast_frame_0001",
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        asset_bible_id="bible_demo",
        character_ids=("char_luna",),
        continuity_notes=("Keep goggles visible.",),
    )
    second = SceneCast.from_dict({
        **first.to_dict(),
        "continuity_notes": ["Use the red jacket."],
    })

    assert service.version_for_scene_cast(first) != service.version_for_scene_cast(second)
    assert service.version_for_scene_cast(first).startswith("scene_cast_rev_")


def test_prompt_plan_bundle_versions_are_public_and_deterministic():
    service = DependencyVersionService()
    draft = ImagePromptDraft(
        image_prompt_draft_id="draft_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        prompt_text="Show Luna in the lab.",
    )
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_1",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
        metadata={"scene_cast_id": "cast_frame_0001"},
    )
    bundle = PromptPlanBundle(
        storyboard_plan_id="storyboard_plan_1",
        image_prompt_drafts=(draft,),
        prompt_plans=(plan,),
    )

    first = service.version_for_prompt_plan(bundle.prompt_plans[0])
    second = service.version_for_prompt_plan(PromptPlan.from_dict(bundle.prompt_plans[0].to_dict()))

    assert first == second
    assert first.startswith("prompt_plan_rev_")


def test_artifact_version_token_uses_public_artifact_identity_not_storage_key():
    service = DependencyVersionService()
    version = ArtifactVersion(
        version_id="artifact_version_1",
        artifact_id="artifact_frame_0001_image",
        workspace_id="workspace_1",
        frame_id="frame_0001",
        source_prompt_plan_id="prompt_plan_1",
        storage_key="artifacts/workspace_1/frame_0001/artifact_version_1.png",
        status=ArtifactVersionStatus.SUCCEEDED,
        provider="comfyui",
    )

    token = service.version_for_artifact_version(version)

    assert token.startswith("image_artifact_rev_")
    assert "artifacts" not in token
    assert "/" not in token
    assert "\\" not in token
