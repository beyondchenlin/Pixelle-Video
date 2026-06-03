from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DEPRECATED_RUNTIME_FIELD_NAMES = frozenset(
    {
        "ip_enabled",
        "ip_profile_id",
        "ip_asset_bible_id",
        "visual_role_strategy",
        "visual_role_mode",
        "visual_participation_mode",
        "visual_structure_mode",
        "visual_expression_mode",
        "visual_consistency_mode",
        "visual_role_request",
        "visual_role_profile",
        "visual_role_identity_contract",
        "visual_role_plan_by_frame",
        "visual_role_critique_by_frame",
        "visual_role_projected_prompt_parts_by_frame",
        "visual_role_repair_attempts",
        "visual_role_artifacts",
        "visual_role_plan",
        "visual_role_critique",
        "visual_role_enabled",
        "visual_role_contract",
    }
)

DEPRECATED_RUNTIME_MODULE_TOKENS = frozenset(
    {
        "visual_role_identity",
        "visual_role_planning",
        "visual_role_profile",
        "visual_role_request",
        "visual_role_strategy",
        "visual_anchor_integration_planner",
        "visual_role_identity_contract_builder",
        "visual_role_image_prompt_compiler",
        "visual_role_primary_contract",
        "visual_role_profile_builder",
        "visual_role_prompt_projector",
        "visual_role_scene_planner",
        "visual_role_prompt_critic",
        "visual_role_repair_loop",
    }
)

DEPRECATED_RUNTIME_SYMBOL_NAMES = frozenset(
    {
        "CompiledVisualRoleImagePrompt",
        "VisualConsistencyMode",
        "VisualRoleControlsContract",
        "VisualRoleCritique",
        "VisualRoleIdentityContract",
        "VisualRoleIdentityContractBuilder",
        "VisualRoleIntegratedPromptPlan",
        "VisualRoleMode",
        "VisualRoleParticipationMode",
        "VisualRolePlanningError",
        "VisualRoleProfile",
        "VisualRoleProfileBuilder",
        "VisualRoleProfileError",
        "VisualRolePromptCritic",
        "VisualRolePromptIssue",
        "VisualRolePromptProjectionError",
        "VisualRolePromptProjector",
        "VisualRoleRepairFailedError",
        "VisualRoleRepairLoop",
        "VisualRoleRequest",
        "VisualRoleRequestContract",
        "VisualRoleScenePlanner",
        "VisualRoleStrategy",
        "VisualRoleStrategyControls",
        "VisualRoleStructureMode",
        "compile_visual_role_image_prompt",
    }
)

PROMPT_PARAGRAPH_PROFILE_FIELDS = frozenset(
    {
        "prompt",
        "profile_prompt",
        "prompt_text",
        "positive_prompt",
        "negative_prompt",
        "role_prompt",
        "scene_prompt",
        "style_prompt",
        "identity_prompt",
        "provider_prompt",
    }
)


def reject_deprecated_signature_fields(payload: Any, *, context: str = "payload") -> None:
    """Reject old request/runtime fields at every boundary.

    This function intentionally lives in an architecture guard module so production
    files can reject deprecated fields without hardcoding those tokens locally.
    """
    violations = _find_deprecated_fields(payload)
    if violations:
        joined = ", ".join(sorted(violations))
        raise ValueError(f"{context} contains deprecated visual signature fields: {joined}")


def reject_prompt_paragraph_profile_fields(payload: Any, *, context: str = "profile") -> None:
    violations = _find_prompt_profile_fields(payload)
    if violations:
        joined = ", ".join(sorted(violations))
        raise ValueError(f"{context} contains prompt paragraph fields: {joined}")


def _find_deprecated_fields(payload: Any, *, path: str = "root") -> set[str]:
    results: set[str] = set()
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in DEPRECATED_RUNTIME_FIELD_NAMES:
                results.add(child_path)
            results.update(_find_deprecated_fields(value, path=child_path))
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, item in enumerate(payload):
            results.update(_find_deprecated_fields(item, path=f"{path}[{index}]"))
    return results


def _find_prompt_profile_fields(payload: Any, *, path: str = "root") -> set[str]:
    results: set[str] = set()
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in PROMPT_PARAGRAPH_PROFILE_FIELDS:
                results.add(child_path)
            results.update(_find_prompt_profile_fields(value, path=child_path))
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, item in enumerate(payload):
            results.update(_find_prompt_profile_fields(item, path=f"{path}[{index}]"))
    return results
