from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan


def test_creation_package_round_trips_empty_text_overlay_plan():
    package = CreationPackage(task_id="task-1")

    data = package.to_dict()
    restored = CreationPackage.from_dict(data)

    assert data["version"] == "creation_package.v1"
    assert data["text_overlay_plan"] is None
    assert restored.task_id == "task-1"
    assert restored.text_overlay_plan is None


def test_creation_package_round_trips_text_overlay_plan_and_freezes_maps():
    plan = TextOverlayPlan(
        candidates=(
            TextOverlayCandidate(
                id="candidate-1",
                text="标题",
                role="headline",
                suggested_slot="top_left",
                renderer_targets=("hyperframes",),
                source={"frame_index": 0},
            ),
        ),
        source_summary={"narration_count": 1},
    )
    package = CreationPackage(
        task_id="task-1",
        content_plan={"title": "demo"},
        text_overlay_plan=plan,
        render_plan={"template_id": "image_default"},
    )

    restored = CreationPackage.from_dict(package.to_dict())

    assert restored.content_plan["title"] == "demo"
    assert restored.text_overlay_plan.candidates[0].role == "headline"
    assert restored.render_plan["template_id"] == "image_default"
