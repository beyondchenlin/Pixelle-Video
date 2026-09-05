from __future__ import annotations

import streamlit as st

from pixelle_video.services.video_manual_acceptance import (
    VIDEO_ACCEPTANCE_CHECKS,
    VideoManualAcceptanceRecord,
    read_video_manual_acceptance,
    record_video_manual_acceptance,
)


def render_video_manual_acceptance(*, task_dir, video_path, ui=st):
    """An explicit human decision, separate from the generation task status."""
    with ui.expander("成片交付验收", expanded=True):
        try:
            status, snapshot = read_video_manual_acceptance(task_dir=task_dir, video_path=video_path)
        except (OSError, ValueError) as exc:
            ui.error(f"验收证据无法核对：{exc}")
            return
        labels = {
            "pending": "生成完成，等待人工验收",
            "passed": "人工验收通过，可交付",
            "failed": "人工验收不通过",
            "stale": "产物或验收依据已变化，原验收结论失效",
        }
        ui.markdown(f"**{labels[status]}**")
        if status != "pending":
            ui.caption("该任务的验收记录已锁定。需要修改时，请主动发起新任务。")
            return
        if snapshot["frame_status"] == "pending":
            ui.caption("请先在下方逐镜证据中完成原图验收，再提交成片通过结论。")
        elif snapshot["frame_status"] == "failed":
            ui.warning("已有分镜原图验收不通过，当前成片不能标记为可交付。")
        ui.caption("请完整观看并听音，再逐项确认。保存验收不会修改视频或触发重新生成。")
        with ui.form(f"video_acceptance_{snapshot['task_id']}"):
            checks = {key: ui.checkbox(label, value=False) for key, label in VIDEO_ACCEPTANCE_CHECKS.items()}
            reviewer = ui.text_input("验收人", value="")
            reason = ui.text_area("不通过的具体原因；全部通过时留空", value="")
            submitted = ui.form_submit_button("保存人工验收")
        if not submitted:
            return
        try:
            record = VideoManualAcceptanceRecord(
                **{key: value for key, value in snapshot.items() if key != "frame_status"},
                status="passed" if all(checks.values()) else "failed",
                checks=checks, reviewer=reviewer, reason=reason,
            )
            record_video_manual_acceptance(task_dir=task_dir, video_path=video_path, record=record)
        except (OSError, ValueError) as exc:
            ui.error(f"验收未保存：{exc}")
            return
        ui.success("人工验收已保存。")
        ui.rerun()
