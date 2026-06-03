from __future__ import annotations

from pixelle_video.services.visible_text_prompt_rewriter import (
    detect_visible_text_drawing_risks,
    rewrite_for_no_visible_text,
)


def test_rewriter_replaces_drawing_risk_terms_without_self_leaking() -> None:
    prompt = "打开的书页上的文字和人物名字列表，旁边是家族树图上的名字。"

    rewritten = rewrite_for_no_visible_text(prompt)

    assert "书页上的文字" not in rewritten
    assert "人物名字" not in rewritten
    assert "名字列表" not in rewritten
    assert "家族树图上的名字" not in rewritten
    assert "blank page marks" in rewritten
    assert detect_visible_text_drawing_risks(rewritten) == ()
