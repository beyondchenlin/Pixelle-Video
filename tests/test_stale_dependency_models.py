from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.stale_dependency import (
    DependencyEdge,
    StaleMark,
    StalePropagationSummary,
    UpstreamChangeEvent,
)


def test_dependency_edge_round_trips_with_public_ids_only():
    edge = DependencyEdge(
        edge_id="dep_edge_001",
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="asset_bible",
        upstream_id="bible_demo",
        upstream_version="asset_bible_rev_3",
        downstream_type="scene_cast",
        downstream_id="cast_frame_0001",
        relation="scene_cast.references_asset_bible",
        metadata={"storyboard_plan_id": "storyboard_plan_1", "frame_id": "frame_0001"},
    )

    payload = edge.to_dict()

    assert DependencyEdge.from_dict(payload) == edge
    assert payload["upstream_id"] == "bible_demo"
    assert payload["downstream_id"] == "cast_frame_0001"
    assert "D:\\" not in str(payload)
    assert "workflows/" not in str(payload)
    assert "https://" not in str(payload)
    with pytest.raises(FrozenInstanceError):
        edge.downstream_id = "changed"
    with pytest.raises(TypeError):
        edge.metadata["frame_id"] = "changed"


def test_dependency_edge_metadata_is_deeply_immutable():
    edge = DependencyEdge(
        edge_id="dep_edge_001",
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="asset_bible",
        upstream_id="bible_demo",
        upstream_version="asset_bible_rev_3",
        downstream_type="scene_cast",
        downstream_id="cast_frame_0001",
        relation="scene_cast.references_asset_bible",
        metadata={
            "audit": {"frame_id": "frame_0001"},
            "source_ids": ["character_1", "prop_1"],
        },
    )

    with pytest.raises(TypeError):
        edge.metadata["audit"]["frame_id"] = "changed"
    with pytest.raises(TypeError):
        edge.metadata["source_ids"][0] = "changed"
    assert edge.to_dict()["metadata"] == {
        "audit": {"frame_id": "frame_0001"},
        "source_ids": ["character_1", "prop_1"],
    }


def test_stale_mark_records_reason_upstream_version_and_timestamp():
    mark = StaleMark(
        stale_id="stale_001",
        workspace_id="workspace_1",
        project_id="project_1",
        target_type="prompt_plan",
        target_id="prompt_plan_001",
        reason_code="scene_cast_changed",
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_4",
        marked_at="2026-05-01T10:03:00Z",
        metadata={"lock_policy": "locked_prompt"},
    )

    payload = mark.to_dict()

    assert StaleMark.from_dict(payload) == mark
    assert payload["project_id"] == "project_1"
    assert payload["reason_code"] == "scene_cast_changed"
    assert payload["upstream_version"] == "scene_cast_rev_4"
    assert payload["marked_at"] == "2026-05-01T10:03:00Z"
    assert payload["metadata"] == {"lock_policy": "locked_prompt"}


def test_upstream_change_event_rejects_non_public_identity_values():
    with pytest.raises(ValueError, match="public ID"):
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="asset_bible",
            upstream_id=r"D:\demo1\Pixelle\bible.json",
            upstream_version="asset_bible_rev_4",
            reason_code="asset_bible_changed",
        )

    with pytest.raises(ValueError, match="public ID"):
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="https://provider.example/jobs/123",
            reason_code="prompt_plan_changed",
        )


def test_dependency_edge_rejects_workflow_path_as_public_contract():
    with pytest.raises(ValueError, match="public ID"):
        DependencyEdge(
            edge_id="dep_edge_bad",
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_1",
            downstream_type="image_artifact",
            downstream_id="workflows/selfhost/storyboard.json",
            relation="image_artifact.generated_from_prompt_plan",
        )


def test_dependency_edge_rejects_relative_path_as_public_contract():
    with pytest.raises(ValueError, match="public ID"):
        DependencyEdge(
            edge_id="dep_edge_bad",
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_1",
            downstream_type="image_artifact",
            downstream_id="output/frame_0001.png",
            relation="image_artifact.generated_from_prompt_plan",
        )


def test_summary_counts_are_non_negative_and_round_trip():
    summary = StalePropagationSummary(
        workspace_id="workspace_1",
        upstream_type="asset_bible",
        upstream_id="bible_demo",
        upstream_version="asset_bible_rev_4",
        visited_edge_count=3,
        stale_created_count=2,
        stale_existing_count=1,
        marked_target_ids=("cast_frame_0001", "prompt_plan_001"),
    )

    assert StalePropagationSummary.from_dict(summary.to_dict()) == summary

    with pytest.raises(ValueError, match="non-negative"):
        StalePropagationSummary(
            workspace_id="workspace_1",
            upstream_type="asset_bible",
            upstream_id="bible_demo",
            upstream_version="asset_bible_rev_4",
            visited_edge_count=-1,
            stale_created_count=0,
            stale_existing_count=0,
        )
