from pixelle_video.services.visual_story_execution_planner import VisualStoryExecutionPlanner


class Frame:
    def __init__(self, index):
        self.frame_id = f"frame-{index + 1}"
        self.index = index
        self.source_text = f"source {index + 1}"
        self.visual_goal = f"goal {index + 1}"
        self.prompt_intent = f"intent {index + 1}"


class Storyboard:
    frames = [Frame(i) for i in range(9)]


def test_execution_planner_batches_frames_locally():
    plan = VisualStoryExecutionPlanner().plan(source_text="百年孤独", storyboard_plan=Storyboard(), selected_visual_route={"route_id": "philosophical_loop"}, batch_size=4, max_context_chars=9000)
    assert plan.frame_count == 9
    assert len(plan.batches) == 3
    assert plan.batches[0].frame_ids == ("frame-1", "frame-2", "frame-3", "frame-4")
    assert plan.batches[1].requires_previous_continuity_digest is True
    assert plan.selected_route_id == "philosophical_loop"
