from __future__ import annotations

from dataclasses import dataclass

from pixelle_video.models.stale_dependency import (
    DependencyEdge,
    StaleMark,
    StalePropagationSummary,
    UpstreamChangeEvent,
)
from pixelle_video.repositories.stale_dependencies import (
    DependencyEdgeRepository,
    StaleMarkRepository,
)


class StaleDependencyPropagationError(ValueError):
    pass


class StaleDependencyRepositoryNotConfiguredError(StaleDependencyPropagationError):
    pass


@dataclass(frozen=True)
class StaleDependencyPropagationService:
    edge_repository: DependencyEdgeRepository | None
    stale_repository: StaleMarkRepository | None

    def __post_init__(self) -> None:
        if self.edge_repository is None:
            raise StaleDependencyRepositoryNotConfiguredError("dependency edge repository is not configured")
        if self.stale_repository is None:
            raise StaleDependencyRepositoryNotConfiguredError("stale mark repository is not configured")

    async def propagate_upstream_change(self, event: UpstreamChangeEvent) -> StalePropagationSummary:
        visited_edge_keys: set[tuple[str, str, str, str, str, str, str]] = set()
        marked_target_ids: list[str] = []
        created_count = 0
        existing_count = 0
        queue: list[tuple[str, str, str]] = [
            (event.upstream_type, event.upstream_id, event.reason_code)
        ]

        while queue:
            upstream_type, upstream_id, reason_code = queue.pop(0)
            is_direct_event_upstream = upstream_type == event.upstream_type and upstream_id == event.upstream_id
            edges = await self.edge_repository.list_downstream_edges(
                event.workspace_id,
                upstream_type,
                upstream_id,
            )
            for payload in edges:
                edge = DependencyEdge.from_dict(payload)
                edge_key = (
                    edge.workspace_id,
                    edge.project_id,
                    edge.edge_id,
                    edge.upstream_type,
                    edge.upstream_id,
                    edge.downstream_type,
                    edge.downstream_id,
                )
                if edge_key in visited_edge_keys:
                    continue
                if is_direct_event_upstream and edge.upstream_version == event.upstream_version:
                    continue
                visited_edge_keys.add(edge_key)
                reason = _reason_for(
                    downstream_type=edge.downstream_type,
                    incoming_reason=reason_code,
                    relation=edge.relation,
                )
                mark = StaleMark(
                    stale_id=(
                        f"stale_{edge.downstream_type}_{edge.downstream_id}_"
                        f"{event.upstream_type}_{event.upstream_id}_{event.upstream_version}"
                    ),
                    workspace_id=event.workspace_id,
                    target_type=edge.downstream_type,
                    target_id=edge.downstream_id,
                    reason_code=reason,
                    upstream_type=event.upstream_type,
                    upstream_id=event.upstream_id,
                    upstream_version=event.upstream_version,
                    metadata={
                        "source_edge_id": edge.edge_id,
                        "source_edge_version": edge.upstream_version,
                        "via_relation": edge.relation,
                        "is_direct_event_upstream": is_direct_event_upstream,
                    },
                )
                _, created = await self.stale_repository.mark_stale(event.workspace_id, mark.to_dict())
                if created:
                    created_count += 1
                else:
                    existing_count += 1
                marked_target_ids.append(edge.downstream_id)
                queue.append((edge.downstream_type, edge.downstream_id, mark.reason_code))

        return StalePropagationSummary(
            workspace_id=event.workspace_id,
            upstream_type=event.upstream_type,
            upstream_id=event.upstream_id,
            upstream_version=event.upstream_version,
            visited_edge_count=len(visited_edge_keys),
            stale_created_count=created_count,
            stale_existing_count=existing_count,
            marked_target_ids=tuple(dict.fromkeys(marked_target_ids)),
        )


def _reason_for(*, downstream_type: str, incoming_reason: str, relation: str) -> str:
    if incoming_reason == "asset_bible_changed" and relation == "prompt_plan.references_asset_bible":
        return "asset_bible_changed"
    mapping = {
        ("scene_cast", "asset_bible_changed"): "asset_bible_changed",
        ("prompt_plan", "asset_bible_changed"): "asset_bible_changed_via_scene_cast",
        ("image_artifact", "asset_bible_changed_via_scene_cast"): "asset_bible_changed_via_prompt_plan",
        ("prompt_plan", "scene_cast_changed"): "scene_cast_changed",
        ("image_artifact", "scene_cast_changed"): "scene_cast_changed_via_prompt_plan",
        ("image_artifact", "prompt_plan_changed"): "prompt_plan_changed",
        ("video_segment", "prompt_plan_changed"): "prompt_plan_changed_via_image_artifact",
        ("video_segment", "prompt_plan_changed_via_image_artifact"): "prompt_plan_changed_via_image_artifact",
        ("final_video", "prompt_plan_changed_via_image_artifact"): "prompt_plan_changed_via_video_segment",
    }
    return mapping.get((downstream_type, incoming_reason), incoming_reason)
