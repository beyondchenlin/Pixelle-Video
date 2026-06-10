from pixelle_video.services.visual_story_context_contract import (
    VisualStoryContextContractBuilder,
    compact_visual_anchor_contexts,
    compact_visual_story_frame_context,
)


def test_visual_story_contract_has_hard_budget_and_no_route_duplication():
    context = {
        "frame_id": "frame-1",
        "frame_index": 0,
        "base_prompt": "x" * 12000,
        "selected_visual_route": {
            "route_id": "philosophical_metaphor",
            "route_name": "哲学隐喻",
            "visual_premise": "y" * 3000,
            "why_it_fits_article": "r" * 3000,
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
    assert all("selected_visual_route" not in frame for frame in payload["frame_contexts"])
    assert "context_contract" in payload


def test_visual_story_contract_degrades_without_exceeding_budget():
    frames = [
        {
            "frame_id": f"frame-{index}",
            "frame_index": index,
            "source_text": "正文" * 500,
            "visual_story_frame_plan": {"frame_id": f"frame-{index}", "visual_task": "任务" * 500},
            "visual_story_ip_fusion_plan": {"frame_id": f"frame-{index}", "scene_function": "作用" * 500},
            "selected_visual_route": {"route_id": "route", "visual_premise": "路线" * 500},
        }
        for index in range(40)
    ]

    contract = VisualStoryContextContractBuilder().build_for_visual_anchor(frame_contexts=frames)
    assert len(str(contract.payload)) <= 11000
    assert contract.payload["context_contract"]["degradation_level"] in {
        "compact",
        "tight",
        "minimal",
        "hard_budget",
        "frame_ids_only",
        "summary_only",
    }
