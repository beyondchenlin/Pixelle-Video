from __future__ import annotations

from pixelle_video.services.visual_story_context_budget import compact_visual_anchor_contexts, compact_visual_story_frame_context


def test_visual_story_context_budget_removes_unbounded_fields():
    context = {
        "frame_id": "frame-1",
        "frame_index": 0,
        "source_text": "x" * 5000,
        "base_prompt": "do not include" * 500,
        "selected_visual_route": {
            "route_id": "philosophical_metaphor",
            "route_name": "哲学隐喻",
            "visual_premise": "y" * 3000,
            "huge_blob": {"x": "z" * 3000},
        },
        "visual_story_frame_plan": {"frame_id": "frame-1", "visual_task": "a" * 3000},
        "visual_story_ip_fusion_plan": {"frame_id": "frame-1", "scene_function": "b" * 3000},
    }
    compact = compact_visual_story_frame_context(context)
    assert "base_prompt" not in compact
    assert compact["selected_visual_route"]["route_id"] == "philosophical_metaphor"
    payload = compact_visual_anchor_contexts(frame_contexts=[context] * 8, max_total_chars=9000)
    assert len(str(payload)) <= 11000
    assert payload["selected_visual_route"]["route_id"] == "philosophical_metaphor"
