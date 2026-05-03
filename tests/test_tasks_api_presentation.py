from types import SimpleNamespace


def test_present_task_derives_video_url_from_current_request_without_mutating_result():
    from api.routers.tasks import present_task
    from api.tasks.models import TaskStatus, TaskType

    task = SimpleNamespace(
        task_id="task-video-1",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.COMPLETED,
        progress=None,
        result={"storage_key": "task-video-1/final.mp4", "duration": 2.5, "file_size": 5},
        error=None,
    )
    request = SimpleNamespace(base_url="https://pixelle.example/")

    response = present_task(task, request=request)

    assert response.result["video_url"] == (
        "https://pixelle.example/api/files/task-video-1/final.mp4"
    )
    assert "video_url" not in task.result


def test_async_video_router_does_not_define_per_request_execution_closure():
    from pathlib import Path

    source = Path("api/routers/video.py").read_text(encoding="utf-8")
    async_route_source = source.split('async def generate_video_async(', 1)[1]

    assert "execute_video_generation" not in async_route_source
    assert "execute_task(" not in async_route_source
    assert "path_to_url(request" not in async_route_source
