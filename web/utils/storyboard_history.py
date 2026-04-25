from __future__ import annotations


def resolve_history_storyboard_scene_count(detail: dict):
    storyboard_generation = _extract_storyboard_generation_snapshot(detail)
    resolved_scene_count = storyboard_generation.get("resolved_scene_count")
    if resolved_scene_count is not None:
        return resolved_scene_count

    metadata = detail.get("metadata", {}) or {}
    input_params = metadata.get("input", {}) or {}
    if input_params.get("storyboard_scene_count") is not None:
        return input_params["storyboard_scene_count"]
    return input_params.get("n_scenes")


def _extract_storyboard_generation_snapshot(detail: dict) -> dict:
    storyboard = detail.get("storyboard")
    storyboard_snapshot = getattr(storyboard, "planning_snapshot", None)
    if isinstance(storyboard_snapshot, dict):
        generation = storyboard_snapshot.get("storyboard_generation")
        if isinstance(generation, dict):
            return generation

    metadata = detail.get("metadata", {}) or {}
    for section_name in ("result", "input"):
        section = metadata.get(section_name, {}) or {}
        snapshot = section.get("storyboard_planning_snapshot") or section.get("planning_snapshot")
        if isinstance(snapshot, dict):
            generation = snapshot.get("storyboard_generation")
            if isinstance(generation, dict):
                return generation
    return {}
