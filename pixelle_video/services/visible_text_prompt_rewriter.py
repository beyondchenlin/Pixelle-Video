from __future__ import annotations

DRAWING_RISK_REPLACEMENTS = {
    "书页上的文字": "blank page marks",
    "页面文字": "short unreadable page lines",
    "书名": "blank book cover",
    "标题": "blank header bar",
    "名字列表": "repeated unlabeled nodes",
    "人物名字": "similar blank character nodes",
    "家族树图上的名字": "blank family-tree nodes",
    "标签文字": "small icon markers",
    "文字标签": "simple icon markers",
    "readable labels": "unlabeled nodes",
    "name list": "repeated unlabeled nodes",
    "character names": "similar blank character nodes",
    "book title": "blank book cover",
    "page text": "short unreadable page lines",
}

DRAWING_RISK_TERMS = (
    "书页上的文字",
    "页面文字",
    "书名",
    "名字列表",
    "人物名字",
    "家族树图上的名字",
    "标签文字",
    "文字标签",
    "readable labels",
    "name list",
    "character names",
    "book title",
    "page text",
)

NO_VISIBLE_TEXT_DRAWING_CLAUSE = "Use blank page lines, unlabeled nodes, simple icons, and abstract marks only."
NO_VISIBLE_TEXT_NEGATIVE_PROMPT = "readable text, Chinese characters, English words, labels, captions, subtitles, watermark, logo text"


def rewrite_for_no_visible_text(prompt_text: str) -> str:
    text = rewrite_visible_text_drawing_risks(prompt_text)
    if NO_VISIBLE_TEXT_DRAWING_CLAUSE not in text:
        text = f"{text}; {NO_VISIBLE_TEXT_DRAWING_CLAUSE}" if text else NO_VISIBLE_TEXT_DRAWING_CLAUSE
    return " ".join(text.split())


def rewrite_visible_text_drawing_risks(prompt_text: str) -> str:
    """Replace drawing-risk phrases without repeating the global policy clause."""

    text = str(prompt_text or "")
    for source, replacement in DRAWING_RISK_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    return " ".join(text.split())


def detect_visible_text_drawing_risks(prompt_text: str) -> tuple[str, ...]:
    text = str(prompt_text or "")
    lower_text = text.lower()
    issues = []
    for term in DRAWING_RISK_TERMS:
        haystack = lower_text if term.isascii() else text
        needle = term.lower() if term.isascii() else term
        if needle in haystack:
            issues.append(f"visible_text_drawing_risk:{term}")
    return tuple(issues)
