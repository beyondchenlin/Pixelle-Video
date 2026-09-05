import hashlib
import json

import pytest

from pixelle_video.services.video_manual_acceptance import (
    VIDEO_ACCEPTANCE_CHECKS,
    VideoManualAcceptanceRecord,
    read_video_manual_acceptance,
    record_video_manual_acceptance,
    video_review_snapshot,
)
from pixelle_video.services.visual_anchor_manual_acceptance import (
    VisualAnchorManualAcceptanceChecks,
    VisualAnchorManualAcceptanceRecord,
    manual_acceptance_artifact_relative_path,
)


def _task(tmp_path, anchored=False):
    root = tmp_path / "task-1"
    root.mkdir()
    (root / "final.mp4").write_bytes(b"fixture-video")
    (root / "image.png").write_bytes(b"fixture-image")
    (root / "storyboard.json").write_text(json.dumps({
        "frames": [{"frame_id": "frame-a", "image_path": "image.png"}],
        "planning_snapshot": {"visual_anchor_two_stage": {"frames": [1]}} if anchored else {},
    }), encoding="utf-8")
    return root


def _record(root, passed=True):
    snapshot = video_review_snapshot(task_dir=root, video_path="final.mp4")
    return VideoManualAcceptanceRecord(
        **{key: value for key, value in snapshot.items() if key != "frame_status"},
        checks={key: passed for key in VIDEO_ACCEPTANCE_CHECKS},
        status="passed" if passed else "failed", reviewer="人工审核员",
        reason="" if passed else "字幕时序不正确",
    )


def _approve_frame(root):
    path = root / manual_acceptance_artifact_relative_path("frame-a")
    path.parent.mkdir(parents=True)
    path.write_text(VisualAnchorManualAcceptanceRecord(
        task_id=root.name, acceptance_batch_id="batch", acceptance_round=1,
        sample_id="sample", frame_id="frame-a", random_seed=1,
        image_sha256=hashlib.sha256((root / "image.png").read_bytes()).hexdigest(),
        rendered_audit_sha256="a" * 64, first_request_binding_sha256="b" * 64,
        status="passed", reviewer="人工审核员",
        checks=VisualAnchorManualAcceptanceChecks(**{
            key: True for key in VisualAnchorManualAcceptanceChecks.model_fields
        }),
    ).model_dump_json(), encoding="utf-8")


def test_generated_video_starts_pending_and_failed_review_is_preserved(tmp_path):
    root = _task(tmp_path)
    assert read_video_manual_acceptance(task_dir=root, video_path="final.mp4")[0] == "pending"
    record_video_manual_acceptance(task_dir=root, video_path="final.mp4", record=_record(root, False))
    assert read_video_manual_acceptance(task_dir=root, video_path="final.mp4")[0] == "failed"
    with pytest.raises(ValueError, match="已锁定"):
        record_video_manual_acceptance(task_dir=root, video_path="final.mp4", record=_record(root))
    assert (root / "final.mp4").read_bytes() == b"fixture-video"


def test_delivery_requires_all_original_frame_reviews_and_binds_current_video(tmp_path):
    root = _task(tmp_path, anchored=True)
    with pytest.raises(ValueError, match="所有分镜"):
        record_video_manual_acceptance(task_dir=root, video_path="final.mp4", record=_record(root))
    _approve_frame(root)
    record_video_manual_acceptance(task_dir=root, video_path="final.mp4", record=_record(root))
    assert read_video_manual_acceptance(task_dir=root, video_path="final.mp4")[0] == "passed"
    (root / "final.mp4").write_bytes(b"changed-video")
    assert read_video_manual_acceptance(task_dir=root, video_path="final.mp4")[0] == "stale"


def test_changed_original_image_invalidates_frame_review(tmp_path):
    root = _task(tmp_path, anchored=True)
    _approve_frame(root)
    (root / "image.png").write_bytes(b"changed-image")
    with pytest.raises(ValueError, match="原图不一致"):
        video_review_snapshot(task_dir=root, video_path="final.mp4")


def test_review_cannot_bind_a_file_outside_task(tmp_path):
    root = _task(tmp_path)
    outside = tmp_path / "other.mp4"
    outside.write_bytes(b"other")
    with pytest.raises(ValueError, match="当前任务目录"):
        video_review_snapshot(task_dir=root, video_path=outside)


def test_empty_or_partial_human_checks_cannot_pass(tmp_path):
    root = _task(tmp_path)
    data = _record(root).model_dump()
    data["checks"].pop("audio")
    with pytest.raises(ValueError, match="逐项记录"):
        VideoManualAcceptanceRecord.model_validate(data)
