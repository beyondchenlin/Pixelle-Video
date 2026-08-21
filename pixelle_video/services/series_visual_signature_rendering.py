from __future__ import annotations

from pixelle_video.models.content_bound_ip import IPParticipationMechanism
from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.services.protected_protagonist_composition import (
    protected_protagonist_action,
    protected_protagonist_subject,
)
from pixelle_video.services.series_visual_signature_prompt_presence import (
    normalize_prompt_text,
    prompt_contains_term,
    remove_prompt_term,
)
from pixelle_video.services.structured_group_composition import (
    SINGLE_FACILITATOR_GROUP_ACTION,
    is_structured_group_scene,
)
from pixelle_video.services.structured_timeline_composition import (
    SINGLE_ACTOR_TIMELINE_ACTION,
    is_structured_timeline_scene,
)

_NON_DESCRIPTIVE_REMAINDERS = frozenset(
    {
        "a",
        "an",
        "the",
        "one",
        "a dog",
        "the dog",
        "dog",
        "一只",
        "一个",
        "一位",
        "一种",
    }
)

_INTERNAL_PARTICIPATION_REFERENCE_REWRITES = (
    ("经过视觉锚点参与后", "经过指定角色参与后"),
    ("经过锚点参与后", "经过指定角色参与后"),
    ("视觉锚点必须通过", "指定角色必须通过"),
    ("锚点必须通过", "指定角色必须通过"),
)


def rendered_identity_traits(
    profile: VisualSignatureProfileSnapshot,
) -> tuple[str, ...]:
    """Return visible traits without repeating the rendered entity name."""

    display_name = normalize_prompt_text(profile.display_name)
    seen = {display_name.casefold()}
    result: list[str] = []
    for raw_trait in profile.identity_traits:
        trait = normalize_prompt_text(raw_trait)
        if not trait:
            continue
        rendered = _remove_display_name(trait, display_name)
        key = rendered.casefold()
        if (
            not rendered
            or key in seen
            or key in _NON_DESCRIPTIVE_REMAINDERS
        ):
            continue
        seen.add(key)
        result.append(rendered)
    return tuple(
        trait
        for trait in result
        if not any(
            other.casefold() != trait.casefold()
            and len(other) > len(trait)
            and prompt_contains_term(other, trait)
            for other in result
        )
    )


def rendered_identity_terms(
    profile: VisualSignatureProfileSnapshot,
) -> tuple[str, ...]:
    return (normalize_prompt_text(profile.display_name), *rendered_identity_traits(profile))


def rendered_identity_clause(profile: VisualSignatureProfileSnapshot) -> str:
    """Build one provider-facing mention while preserving stored profile hashes."""

    display_name, *traits = rendered_identity_terms(profile)
    clause = f"The single recurring identity is {display_name}"
    if traits:
        clause += ", visibly defined by " + ", ".join(traits)
    return clause


def rendered_provider_action_verb(
    action_verb: str,
    *,
    participation_mechanism: IPParticipationMechanism,
    interaction_target: str = "",
    physical_metaphor: str = "",
    user_overrode_action: bool = False,
) -> str:
    rendered = normalize_prompt_text(action_verb)
    protagonist = protected_protagonist_subject(
        (interaction_target,),
        physical_metaphor,
        interaction_target,
    )
    if (
        not user_overrode_action
        and rendered == "承受并整理"
        and protagonist
    ):
        return protected_protagonist_action(
            protagonist,
            physical_metaphor,
            interaction_target,
        )
    if (
        not user_overrode_action
        and rendered == "连接"
        and is_structured_group_scene(interaction_target, physical_metaphor)
    ):
        return SINGLE_FACILITATOR_GROUP_ACTION
    if (
        not user_overrode_action
        and rendered == "承受并整理"
        and is_structured_timeline_scene(interaction_target, physical_metaphor)
    ):
        return SINGLE_ACTOR_TIMELINE_ACTION
    if (
        participation_mechanism is IPParticipationMechanism.CONFLICT_PARTICIPANT
        and rendered == "拉住并权衡"
    ):
        return "用同一个身体的一只前爪指向对比图中央的分界线并权衡"
    return rendered


def rendered_provider_participation_text(
    value: str,
    *,
    action_verb: str = "",
    provider_action_verb: str = "",
) -> str:
    """Render contract participation facts without leaking internal anchor jargon."""

    rendered = normalize_prompt_text(value)
    for source, replacement in _INTERNAL_PARTICIPATION_REFERENCE_REWRITES:
        rendered = rendered.replace(source, replacement)
    if action_verb and provider_action_verb:
        rendered = rendered.replace(action_verb, provider_action_verb)
    return rendered


def _remove_display_name(trait: str, display_name: str) -> str:
    if trait.casefold() == display_name.casefold():
        return ""
    rendered = remove_prompt_term(trait, display_name)
    return " ".join(rendered.strip(" ,.;:，。；：+-").split())


__all__ = [
    "rendered_identity_clause",
    "rendered_identity_terms",
    "rendered_identity_traits",
    "rendered_provider_action_verb",
    "rendered_provider_participation_text",
]
