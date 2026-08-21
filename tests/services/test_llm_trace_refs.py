from types import SimpleNamespace

from pixelle_video.services.llm_trace_refs import (
    llm_trace_refs_for_accepted_attempts,
)


def _trace(
    trace_id: str,
    *,
    frame_id: str,
    attempt: int,
    stage: str = "final_visual_prompt_assembly",
    status: str = "success",
):
    return SimpleNamespace(
        trace_id=trace_id,
        status=status,
        context=SimpleNamespace(
            stage=stage,
            frame_id=frame_id,
            metadata={"attempt": attempt},
        ),
    )


def test_trace_refs_keep_only_final_accepted_assembly_attempts():
    records = [
        _trace("trace-rejected-repair", frame_id="frame-1", attempt=1),
        _trace("trace-accepted", frame_id="frame-1", attempt=2),
        _trace("trace-fallback-rejected", frame_id="frame-2", attempt=1),
        _trace(
            "trace-other-stage",
            frame_id="frame-1",
            attempt=2,
            stage="image_prompt_batch",
        ),
        _trace(
            "trace-error",
            frame_id="frame-1",
            attempt=2,
            status="error",
        ),
    ]

    refs = llm_trace_refs_for_accepted_attempts(
        records,
        stage="final_visual_prompt_assembly",
        accepted_attempts_by_frame={"frame-1": 2},
    )

    assert refs == [
        {
            "trace_id": "trace-accepted",
            "stage": "final_visual_prompt_assembly",
        }
    ]


def test_trace_refs_are_empty_when_every_frame_falls_back():
    refs = llm_trace_refs_for_accepted_attempts(
        [_trace("trace-rejected", frame_id="frame-1", attempt=1)],
        stage="final_visual_prompt_assembly",
        accepted_attempts_by_frame={},
    )

    assert refs == []
