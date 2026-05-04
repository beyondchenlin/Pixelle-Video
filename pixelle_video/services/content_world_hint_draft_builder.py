from __future__ import annotations

from pixelle_video.models.content_world import ContentWorldProfile


def build_world_hint_draft(
    profile: ContentWorldProfile,
    *,
    prompt_language: str = "zh_CN",
) -> str:
    clauses = (
        _english_clauses(profile)
        if prompt_language == "en_US"
        else _chinese_clauses(profile)
    )
    return " ".join(clause for clause in clauses if clause).strip()


def _chinese_clauses(profile: ContentWorldProfile) -> list[str]:
    return [
        profile.summary or "",
        profile.time_space or "",
        profile.visual_environment or "",
        f"整体氛围为{profile.atmosphere}。" if profile.atmosphere else "",
        f"叙事边界：{profile.story_constraints}。" if profile.story_constraints else "",
        f"IP 融入方式：{profile.ip_integration_guidance}。" if profile.ip_integration_guidance else "",
    ]


def _english_clauses(profile: ContentWorldProfile) -> list[str]:
    return [
        profile.summary or "",
        profile.time_space or "",
        profile.visual_environment or "",
        f"Overall atmosphere: {profile.atmosphere}." if profile.atmosphere else "",
        f"Story constraints: {profile.story_constraints}." if profile.story_constraints else "",
        f"IP integration: {profile.ip_integration_guidance}." if profile.ip_integration_guidance else "",
    ]
