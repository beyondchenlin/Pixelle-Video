"""Persist human delivery decisions; never inspect or regenerate creative content."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pixelle_video.services.visual_anchor_manual_acceptance import (
    VisualAnchorManualAcceptanceRecord,
    manual_acceptance_artifact_relative_path,
)

VIDEO_ACCEPTANCE_PATH = "video_manual_acceptance.json"
VIDEO_ACCEPTANCE_CHECKS = {
    "content_fidelity": "内容事实与人物数量正确",
    "identity_and_style": "身份可辨、唯一，画风一致",
    "continuity": "镜头与场景承接连贯",
    "information_progression": "每镜推进信息，没有无意义重复",
    "pacing": "已完整观看，镜头停留与节奏合适",
    "captions": "字幕内容、位置和可读性合格",
    "audio": "已听音，配音与背景音乐合格",
    "synchronization": "音画与字幕时序一致",
}


class VideoManualAcceptanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["video_manual_acceptance.v1"] = "video_manual_acceptance.v1"
    task_id: str
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    storyboard_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frame_reviews_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["passed", "failed"]
    checks: dict[str, bool]
    reviewer: str
    reason: str = ""
    recorded_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("task_id", "reviewer")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("任务与验收人不能为空")
        return value.strip()

    @model_validator(mode="after")
    def consistent_decision(self):
        if set(self.checks) != set(VIDEO_ACCEPTANCE_CHECKS):
            raise ValueError("必须逐项记录完整的成片验收检查")
        if self.status == "passed" and (not all(self.checks.values()) or self.reason.strip()):
            raise ValueError("通过验收必须全部勾选，且不能填写失败原因")
        if self.status == "failed" and (all(self.checks.values()) or not self.reason.strip()):
            raise ValueError("不通过必须包含未通过项及具体原因")
        return self


def _task_file(root: Path, name: str | Path) -> Path:
    candidate = Path(name)
    result = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not result.is_relative_to(root) or not result.is_file():
        raise ValueError("验收文件必须存在且位于当前任务目录")
    return result


def _digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def video_review_snapshot(*, task_dir: str | Path, video_path: str | Path) -> dict:
    root = Path(task_dir).resolve()
    video = _task_file(root, video_path)
    storyboard = _task_file(root, "storyboard.json")
    data = json.loads(storyboard.read_text(encoding="utf-8"))
    frames = data.get("frames") or []
    anchored = bool((data.get("planning_snapshot") or {}).get("visual_anchor_two_stage"))
    reviews: dict[str, str] = {}
    frame_status = "not_required"
    if anchored:
        frame_status = "passed" if frames else "pending"
        for frame in frames:
            frame_id = str(frame.get("frame_id") or "")
            if not frame_id or frame_id in reviews:
                raise ValueError("分镜编号缺失或重复，无法核对逐图验收")
            reviews[frame_id] = "pending"
            relative_path = manual_acceptance_artifact_relative_path(frame_id)
            if not (root / relative_path).is_file():
                if frame_status != "failed":
                    frame_status = "pending"
                continue
            review_file = _task_file(root, relative_path)
            review = VisualAnchorManualAcceptanceRecord.model_validate_json(
                review_file.read_text(encoding="utf-8")
            )
            reviews[frame_id] = _digest(review_file)
            image = _task_file(root, frame.get("image_path") or "")
            if review.task_id != root.name or review.frame_id != frame_id or review.image_sha256 != _digest(image):
                raise ValueError("逐图验收记录与当前任务原图不一致")
            if review.status == "failed":
                frame_status = "failed"
    reviews_digest = hashlib.sha256(
        json.dumps(reviews, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "task_id": root.name,
        "video_sha256": _digest(video),
        "storyboard_sha256": _digest(storyboard),
        "frame_reviews_sha256": reviews_digest,
        "frame_status": frame_status,
    }


def read_video_manual_acceptance(*, task_dir, video_path) -> tuple[str, dict]:
    root = Path(task_dir).resolve()
    snapshot = video_review_snapshot(task_dir=root, video_path=video_path)
    if not (root / VIDEO_ACCEPTANCE_PATH).exists():
        return "pending", snapshot
    path = _task_file(root, VIDEO_ACCEPTANCE_PATH)
    record = VideoManualAcceptanceRecord.model_validate_json(path.read_text(encoding="utf-8"))
    if any(getattr(record, key) != snapshot[key] for key in (
        "task_id", "video_sha256", "storyboard_sha256", "frame_reviews_sha256"
    )):
        return "stale", snapshot
    if record.status == "passed" and snapshot["frame_status"] not in {"passed", "not_required"}:
        return "stale", snapshot
    return record.status, snapshot


def record_video_manual_acceptance(*, task_dir, video_path, record: VideoManualAcceptanceRecord):
    root = Path(task_dir).resolve()
    snapshot = video_review_snapshot(task_dir=root, video_path=video_path)
    for key in ("task_id", "video_sha256", "storyboard_sha256", "frame_reviews_sha256"):
        if getattr(record, key) != snapshot[key]:
            raise ValueError("验收期间产物发生变化，请重新查看")
    if record.status == "passed" and snapshot["frame_status"] not in {"passed", "not_required"}:
        raise ValueError("必须先完成所有分镜原图的人工验收且全部通过")
    destination = root / VIDEO_ACCEPTANCE_PATH
    temporary = root / f".video-acceptance-{uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(record.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        # Publish atomically without overwriting another human decision.
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise ValueError("验收记录已锁定；修改后请主动创建新任务") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return record
