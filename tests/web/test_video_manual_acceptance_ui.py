import json

from streamlit.testing.v1 import AppTest


def test_video_review_requires_explicit_human_action(tmp_path):
    root = tmp_path / "task-ui"
    root.mkdir()
    (root / "final.mp4").write_bytes(b"video-fixture")
    (root / "storyboard.json").write_text(json.dumps({"frames": [], "planning_snapshot": {}}))
    script = (
        "from web.components.video_manual_acceptance import render_video_manual_acceptance\n"
        f"render_video_manual_acceptance(task_dir={str(root)!r}, video_path='final.mp4')"
    )
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert len(app.checkbox) == 8
    assert all(not item.value for item in app.checkbox)
    assert not (root / "video_manual_acceptance.json").exists()
    app.text_input[0].set_value("测试审核人")
    app.text_area[0].set_value("节奏不合格")
    app.button[0].click().run()
    assert not app.exception
    record = json.loads((root / "video_manual_acceptance.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert any("人工验收不通过" in item.value for item in app.markdown)
