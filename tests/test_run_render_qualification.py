from scripts.run_render_qualification import _report_summary


def test_report_summary_preserves_actionable_gate_errors():
    summary = _report_summary(
        {
            "kind": "golden_matrix",
            "ok": False,
            "errors": ["portrait-contain: media boundary drift"],
        }
    )

    assert summary == {
        "kind": "golden_matrix",
        "ok": False,
        "errors": ["portrait-contain: media boundary drift"],
    }
