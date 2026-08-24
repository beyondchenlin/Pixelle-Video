from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.article_concretization import (
    ARTICLE_CONCRETIZATION_FLAT_OPTION_KEYS,
    ArticleConcretizationRequest,
)
from pixelle_video.models.image_style_selection import normalize_image_style_selection
from pixelle_video.models.mode_resolution import (
    ARTICLE_VISUAL_PLANNING_REQUEST_KEYS,
    ArticleVisualPlanningRequest,
)
from pixelle_video.models.script_generation_limits import SCRIPT_TARGET_WORDS_MAX
from pixelle_video.models.series_visual_signature_request import (
    SeriesVisualSignatureControlsContract,
    SeriesVisualSignatureRequest,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureStrategy,
    resolve_effective_signature_mode_with_v44_context,
)
from pixelle_video.models.storyboard_limits import (
    DEFAULT_STORYBOARD_GENERATION_LIMITS,
    DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN,
    StoryboardGenerationLimits,
    storyboard_generation_limits_from_config,
)
from pixelle_video.models.storyboard_plan import (
    ScriptLengthMode,
    StoryboardCountMode,
    StoryboardGenerationMode,
    StoryboardPlan,
)
from pixelle_video.prompt_language import (
    DEFAULT_PROMPT_LANGUAGE,
    PromptLanguage,
    normalize_prompt_language,
)
from pixelle_video.tts_audio_strategy import SUPPORTED_STANDARD_TTS_AUDIO_STRATEGIES
from pixelle_video.utils.bool_parsing import coerce_bool

LEGACY_STANDARD_STORYBOARD_PARAMS = frozenset(
    {
        "n_scenes",
        "split_mode",
        "min_narration_words",
        "max_narration_words",
    }
)

PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS = frozenset(
    {
        "plan_id",
        "plan_revision",
        "frame_id",
        "source_digest",
    }
)
LEGACY_FRAME_OVERRIDE_IDENTITY_FIELDS = frozenset({"scene_id", "snapshot_identity"})
PLAN_FRAME_OVERRIDE_VALUE_FIELDS = frozenset(
    {
        "source_text",
        "visual_goal",
        "prompt_intent",
        "shot_type",
        "shot_purpose",
        "primary_subject",
        "secondary_subjects",
        "world_elements",
        "continuity_anchors",
        "focus_detail",
        "mandatory_anchor_area_ratio",
        "mandatory_anchor_horizontal_position",
        "mandatory_anchor_depth_position",
        "mandatory_anchor_visible_extent",
        "mandatory_anchor_action_verb",
        "mandatory_anchor_interaction_target",
    }
)
PLAN_FRAME_OVERRIDE_METADATA_FIELDS = PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS | frozenset(
    {
        "locked_fields",
        "override_source",
    }
)
PLAN_FRAME_OVERRIDE_ALLOWED_FIELDS = (
    PLAN_FRAME_OVERRIDE_METADATA_FIELDS | PLAN_FRAME_OVERRIDE_VALUE_FIELDS
)
VIDEO_GENERATION_MODES = frozenset({"generate", "fixed"})
STORYBOARD_GENERATION_LIMITS = DEFAULT_STORYBOARD_GENERATION_LIMITS
STORYBOARD_SCENE_COUNT_MIN = STORYBOARD_GENERATION_LIMITS.min_scene_count
STORYBOARD_SCENE_COUNT_MAX = STORYBOARD_GENERATION_LIMITS.max_scene_count
STORYBOARD_GENERATION_OPTION_KEYS = (
    "storyboard_mode",
    "storyboard_count_mode",
    "storyboard_scene_count",
    "storyboard_max_scene_count",
    "storyboard_prompt_language",
)
STORYBOARD_PLANNING_OPTION_KEYS = (
    "world_preset_id",
    "generation_world_hint",
    "shot_preset_id",
    "consistency_strength",
    "content_mode",
    "role_strategy",
    "role_locking_strength",
    "shot_strategy",
    "frame_overrides",
)
IP_PROMPT_CHAIN_OPTION_KEYS = (
    "series_visual_signature_enabled",
    "series_visual_signature_asset_bible_id",
    "series_visual_signature_profile_id",
    "series_visual_signature_expression_mode",
    "series_visual_signature_structure_mode",
    "series_visual_signature_participation_mode",
    "series_visual_signature_mode",
    "series_visual_signature_consistency_mode",
    "series_visual_signature_presentation_mode",
    "series_visual_signature_enforcement",
    "series_visual_signature_fallback_enabled",
    "series_visual_signature_fallback_mode",
    "series_visual_signature_min_visibility",
    "series_visual_signature_llm_prompt_assembly_enabled",
    "mandatory_content_bound_anchor",
    "series_visual_signature_contract_version",
    "series_visual_signature_output_validation_mode",
    "series_visual_signature_output_max_attempts",
)
ARTICLE_VISUAL_PLANNING_OPTION_KEYS = (
    *ARTICLE_VISUAL_PLANNING_REQUEST_KEYS,
    *ARTICLE_CONCRETIZATION_FLAT_OPTION_KEYS,
)


def _normalize_optional_contract_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None



@dataclass(frozen=True)
class IPControlsContract:
    series_visual_signature_enabled: bool = False
    series_visual_signature_asset_bible_id: str | None = None
    series_visual_signature_profile_id: str | None = None
    series_visual_signature_expression_mode: str = "auto"
    series_visual_signature_structure_mode: str = "auto"
    series_visual_signature_participation_mode: str = "auto"
    series_visual_signature_mode: str = "auto"
    series_visual_signature_consistency_mode: str = "off"
    effective_series_visual_signature_mode: str = "auto"
    series_visual_signature_llm_prompt_assembly_enabled: bool = False
    mandatory_content_bound_anchor: bool = False
    series_visual_signature_contract_version: str | None = None
    series_visual_signature_output_validation_mode: str = "off"
    series_visual_signature_output_max_attempts: int = 1

    @classmethod
    def from_mapping(cls, params: Mapping[str, Any] | None) -> "IPControlsContract":
        mapping = params or {}
        series_visual_signature_enabled = coerce_bool(mapping.get("series_visual_signature_enabled", False), default=False)
        series_visual_signature_asset_bible_id = _normalize_optional_contract_string(mapping.get("series_visual_signature_asset_bible_id"))
        series_visual_signature_profile_id = _normalize_optional_contract_string(mapping.get("series_visual_signature_profile_id"))
        visual_controls = SeriesVisualSignatureControlsContract.from_mapping(mapping)
        return cls(
            series_visual_signature_enabled=series_visual_signature_enabled,
            series_visual_signature_asset_bible_id=series_visual_signature_asset_bible_id,
            series_visual_signature_profile_id=series_visual_signature_profile_id,
            series_visual_signature_expression_mode=visual_controls.expression_mode.value,
            series_visual_signature_structure_mode=visual_controls.structure_mode.value,
            series_visual_signature_participation_mode=visual_controls.participation_mode.value,
            series_visual_signature_mode=visual_controls.strategy.signature_mode.value,
            series_visual_signature_consistency_mode=visual_controls.strategy.consistency_mode.value,
            effective_series_visual_signature_mode=visual_controls.strategy.effective_signature_mode.value,
            series_visual_signature_llm_prompt_assembly_enabled=visual_controls.llm_prompt_assembly_enabled,
            mandatory_content_bound_anchor=visual_controls.mandatory_content_bound_anchor,
            series_visual_signature_contract_version=visual_controls.contract_version,
            series_visual_signature_output_validation_mode=visual_controls.output_validation_mode,
            series_visual_signature_output_max_attempts=visual_controls.output_max_attempts,
        )

    def validate(self) -> None:
        if not self.series_visual_signature_enabled:
            return
        if self.series_visual_signature_asset_bible_id is None:
            raise ValueError("series_visual_signature_asset_bible_id is required when series_visual_signature_enabled=True")
        if self.series_visual_signature_profile_id is None:
            raise ValueError("series_visual_signature_profile_id is required when series_visual_signature_enabled=True")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"series_visual_signature_enabled": self.series_visual_signature_enabled}
        if not self.series_visual_signature_enabled:
            return payload
        if self.series_visual_signature_asset_bible_id is not None:
            payload["series_visual_signature_asset_bible_id"] = self.series_visual_signature_asset_bible_id
        if self.series_visual_signature_profile_id is not None:
            payload["series_visual_signature_profile_id"] = self.series_visual_signature_profile_id
        payload["series_visual_signature_expression_mode"] = self.series_visual_signature_expression_mode
        payload["series_visual_signature_structure_mode"] = self.series_visual_signature_structure_mode
        payload["series_visual_signature_participation_mode"] = self.series_visual_signature_participation_mode
        payload["series_visual_signature_mode"] = self.series_visual_signature_mode
        payload["series_visual_signature_consistency_mode"] = self.series_visual_signature_consistency_mode
        payload["effective_series_visual_signature_mode"] = self.effective_series_visual_signature_mode
        payload["series_visual_signature_llm_prompt_assembly_enabled"] = (
            self.series_visual_signature_llm_prompt_assembly_enabled
        )
        payload["mandatory_content_bound_anchor"] = self.mandatory_content_bound_anchor
        payload["series_visual_signature_contract_version"] = (
            self.series_visual_signature_contract_version
        )
        payload["series_visual_signature_output_validation_mode"] = (
            self.series_visual_signature_output_validation_mode
        )
        payload["series_visual_signature_output_max_attempts"] = (
            self.series_visual_signature_output_max_attempts
        )
        return payload


@dataclass(frozen=True)
class StoryboardControlsContract:
    storyboard_mode: str = StoryboardGenerationMode.SMART.value
    storyboard_count_mode: str = StoryboardCountMode.AUTO.value
    storyboard_scene_count: Any = None
    storyboard_max_scene_count: Any = None
    storyboard_prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE
    world_preset_id: str | None = None
    generation_world_hint: str | None = None
    shot_preset_id: str | None = None
    consistency_strength: str | None = None
    content_mode: str | None = None
    role_strategy: str | None = None
    role_locking_strength: str | None = None
    shot_strategy: str | None = None
    frame_overrides: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_mapping(
        cls,
        params: Mapping[str, Any] | None,
        *,
        default_prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
    ) -> "StoryboardControlsContract":
        mapping = params or {}
        storyboard_mode = (
            _normalize_optional_contract_string(mapping.get("storyboard_mode"))
            or StoryboardGenerationMode.SMART.value
        )
        storyboard_count_mode = (
            _normalize_optional_contract_string(mapping.get("storyboard_count_mode"))
            or StoryboardCountMode.AUTO.value
        )
        storyboard_scene_count = mapping.get("storyboard_scene_count")
        storyboard_max_scene_count = mapping.get("storyboard_max_scene_count")

        if storyboard_mode == StoryboardGenerationMode.SMART.value:
            if storyboard_count_mode == StoryboardCountMode.AUTO.value:
                storyboard_count_mode = StoryboardCountMode.AUTO.value
                storyboard_scene_count = None
            storyboard_max_scene_count = None
        elif storyboard_mode in {
            StoryboardGenerationMode.PUNCTUATION.value,
            StoryboardGenerationMode.SENTENCE.value,
        }:
            if storyboard_count_mode in {
                StoryboardCountMode.AUTO.value,
                StoryboardCountMode.MANUAL.value,
            }:
                storyboard_count_mode = StoryboardCountMode.AUTO.value
                storyboard_scene_count = None

        frame_overrides = ()
        if mapping.get("frame_overrides") is not None:
            frame_overrides = tuple(normalize_plan_frame_overrides(mapping.get("frame_overrides")))

        return cls(
            storyboard_mode=storyboard_mode,
            storyboard_count_mode=storyboard_count_mode,
            storyboard_scene_count=storyboard_scene_count,
            storyboard_max_scene_count=storyboard_max_scene_count,
            storyboard_prompt_language=normalize_prompt_language(
                mapping.get("storyboard_prompt_language"),
                default=default_prompt_language,
            ),
            world_preset_id=_normalize_optional_contract_string(mapping.get("world_preset_id")),
            generation_world_hint=_normalize_optional_contract_string(
                mapping.get("generation_world_hint")
            ),
            shot_preset_id=_normalize_optional_contract_string(mapping.get("shot_preset_id")),
            consistency_strength=_normalize_optional_contract_string(mapping.get("consistency_strength")),
            content_mode=_normalize_optional_contract_string(mapping.get("content_mode")),
            role_strategy=_normalize_optional_contract_string(mapping.get("role_strategy")),
            role_locking_strength=_normalize_optional_contract_string(
                mapping.get("role_locking_strength")
            ),
            shot_strategy=_normalize_optional_contract_string(mapping.get("shot_strategy")),
            frame_overrides=frame_overrides,
        )

    def to_generation_dict(self) -> dict[str, Any]:
        return {
            "storyboard_mode": self.storyboard_mode,
            "storyboard_count_mode": self.storyboard_count_mode,
            "storyboard_scene_count": self.storyboard_scene_count,
            "storyboard_max_scene_count": self.storyboard_max_scene_count,
            "storyboard_prompt_language": self.storyboard_prompt_language,
        }

    def to_planning_dict(self, *, include_prompt_language: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if include_prompt_language:
            payload["storyboard_prompt_language"] = self.storyboard_prompt_language
        for key in (
            "world_preset_id",
            "generation_world_hint",
            "shot_preset_id",
            "consistency_strength",
            "content_mode",
            "role_strategy",
            "role_locking_strength",
            "shot_strategy",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.frame_overrides:
            payload["frame_overrides"] = [dict(override) for override in self.frame_overrides]
        return payload


def normalize_standard_video_generation_params(
    params: Mapping[str, Any] | None,
    *,
    default_prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> dict[str, Any]:
    normalized = dict(params or {})
    storyboard_contract = StoryboardControlsContract.from_mapping(
        normalized,
        default_prompt_language=default_prompt_language,
    )
    ip_contract = IPControlsContract.from_mapping(normalized)
    series_visual_signature_contract = SeriesVisualSignatureControlsContract.from_mapping(normalized)
    article_visual_planning_request = ArticleVisualPlanningRequest.from_mapping(normalized)
    for key in (*STORYBOARD_GENERATION_OPTION_KEYS, *STORYBOARD_PLANNING_OPTION_KEYS):
        normalized.pop(key, None)
    for key in IP_PROMPT_CHAIN_OPTION_KEYS:
        normalized.pop(key, None)
    for key in ARTICLE_VISUAL_PLANNING_OPTION_KEYS:
        normalized.pop(key, None)
    normalized.update(storyboard_contract.to_generation_dict())
    normalized.update(storyboard_contract.to_planning_dict(include_prompt_language=True))
    normalized.update(ip_contract.to_dict())
    normalized.update(series_visual_signature_contract.to_generation_dict())
    article_visual_planning_params = article_visual_planning_request.to_dict()
    normalized.update(article_visual_planning_params)
    normalized.update(
        _article_concretization_generation_params(
            article_visual_planning_request.article_concretization
        )
    )
    _apply_v44_series_visual_signature_strategy_effective_mode(
        normalized,
        series_visual_signature_contract=series_visual_signature_contract,
        article_visual_planning_request=article_visual_planning_request,
    )
    return normalized


def _article_concretization_generation_params(
    request: ArticleConcretizationRequest,
) -> dict[str, Any]:
    payload = request.to_dict()
    return {
        "article_concretization_enabled": payload["enabled"],
        "cognitive_anchor_kind": payload["cognitive_anchor_kind"],
        "explanation_diagram_grammar": payload["explanation_diagram_grammar"],
        "series_visual_signature_role": payload["series_visual_signature_role"],
        "diagram_render_style": payload["diagram_render_style"],
        "diagram_aspect_ratio": payload["diagram_aspect_ratio"],
        "diagram_visible_text_policy": payload["diagram_visible_text_policy"],
        "diagram_approved_labels": payload["diagram_approved_labels"],
        "diagram_user_intent_hint": payload["diagram_user_intent_hint"],
    }


def _apply_v44_series_visual_signature_strategy_effective_mode(
    normalized: dict[str, Any],
    *,
    series_visual_signature_contract: SeriesVisualSignatureControlsContract,
    article_visual_planning_request: ArticleVisualPlanningRequest,
) -> None:
    series_visual_signature_strategy = article_visual_planning_request.series_visual_signature_strategy
    if (
        series_visual_signature_strategy is SeriesVisualSignatureStrategy.AUTO
        or "effective_series_visual_signature_mode" not in normalized
    ):
        return

    effective_signature_mode = resolve_effective_signature_mode_with_v44_context(
        requested_signature_mode=series_visual_signature_contract.strategy.signature_mode,
        consistency_mode=series_visual_signature_contract.strategy.consistency_mode,
        series_visual_signature_strategy=series_visual_signature_strategy,
        subject_replacement_allowed=series_visual_signature_strategy is SeriesVisualSignatureStrategy.PARTICIPANT,
    )
    normalized["effective_series_visual_signature_mode"] = effective_signature_mode.value


def validate_standard_video_generation_params(
    params: Mapping[str, Any],
    *,
    config: Any | None = None,
    limits: StoryboardGenerationLimits | None = None,
) -> None:
    normalize_image_style_selection(
        params.get("image_style_id"),
        params.get("image_style_revision"),
        prompt_prefix=params.get("prompt_prefix"),
    )
    effective_limits = limits or storyboard_generation_limits_from_config(config)
    legacy_fields = sorted(
        name
        for name in LEGACY_STANDARD_STORYBOARD_PARAMS
        if name in params and params[name] is not None
    )
    if legacy_fields:
        raise ValueError(
            "legacy storyboard parameter is not supported in standard video generation: "
            + ", ".join(legacy_fields)
        )

    ArticleVisualPlanningRequest.from_mapping(params)
    SeriesVisualSignatureControlsContract.from_mapping(params)

    mode = params.get("mode", "generate")
    if mode not in VIDEO_GENERATION_MODES:
        raise ValueError(f"unsupported video generation mode: {mode}")

    tts_audio_strategy = params.get("tts_audio_strategy")
    if (
        tts_audio_strategy is not None
        and tts_audio_strategy not in SUPPORTED_STANDARD_TTS_AUDIO_STRATEGIES
    ):
        raise ValueError(
            f"unsupported standard tts_audio_strategy: {tts_audio_strategy}"
        )

    storyboard_mode = params.get("storyboard_mode", StoryboardGenerationMode.SMART.value)
    if storyboard_mode not in {item.value for item in StoryboardGenerationMode}:
        raise ValueError(f"unsupported storyboard mode: {storyboard_mode}")

    count_mode = params.get("storyboard_count_mode", StoryboardCountMode.AUTO.value)
    if count_mode not in {item.value for item in StoryboardCountMode}:
        raise ValueError(f"unsupported storyboard count mode: {count_mode}")

    scene_count = params.get("storyboard_scene_count")
    deterministic_max_scene_count = params.get("storyboard_max_scene_count")
    if storyboard_mode == "smart":
        if count_mode == "manual":
            if scene_count is None:
                raise ValueError("storyboard_scene_count is required with smart manual mode")
            if (
                type(scene_count) is not int
                or not effective_limits.min_scene_count
                <= scene_count
                <= effective_limits.max_scene_count
            ):
                raise ValueError(
                    "storyboard_scene_count must be between "
                    f"{effective_limits.min_scene_count} and {effective_limits.max_scene_count}"
                )
        elif scene_count is not None:
            raise ValueError("storyboard_scene_count is valid only with smart manual mode")
        if deterministic_max_scene_count is not None:
            raise ValueError(
                "storyboard_max_scene_count is only valid for deterministic storyboard modes"
            )
    else:
        if count_mode != "auto":
            raise ValueError("deterministic storyboard modes require auto count mode")
        if scene_count is not None:
            raise ValueError("storyboard_scene_count is not valid for deterministic storyboard modes")
        if deterministic_max_scene_count is not None and (
            type(deterministic_max_scene_count) is not int
            or not DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN
            <= deterministic_max_scene_count
            <= effective_limits.deterministic_max_scene_count_limit
        ):
            raise ValueError(
                "storyboard_max_scene_count must be between "
                f"{DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN} and "
                f"{effective_limits.deterministic_max_scene_count_limit}"
            )

    script_length_mode = params.get("script_length_mode", "auto")
    if script_length_mode not in {item.value for item in ScriptLengthMode}:
        raise ValueError(f"unsupported script length mode: {script_length_mode}")

    script_target_words = params.get("script_target_words")
    if mode == "fixed":
        if script_length_mode != "auto":
            raise ValueError("script_length_mode is only configurable in generate mode")
        if script_target_words is not None:
            raise ValueError("script_target_words is only valid in generate mode")
    elif script_length_mode == "custom":
        if script_target_words is None:
            raise ValueError("script_target_words is required with custom script length mode")
        if (
            type(script_target_words) is not int
            or script_target_words < 1
            or script_target_words > SCRIPT_TARGET_WORDS_MAX
        ):
            raise ValueError(
                "invalid script_target_words: must be a positive integer "
                f"no greater than {SCRIPT_TARGET_WORDS_MAX}"
            )
    elif script_target_words is not None:
        raise ValueError("script_target_words is only valid with custom script length mode")

    validate_plan_frame_override_payloads(params.get("frame_overrides"))
    IPControlsContract.from_mapping(params).validate()
    SeriesVisualSignatureRequest.from_mapping(params).validate()


def is_plan_frame_override_payload(override: Mapping[str, Any]) -> bool:
    return PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS <= set(override.keys())


def validate_plan_frame_override_payloads(
    frame_overrides: Sequence[Mapping[str, Any]] | None,
) -> None:
    normalize_plan_frame_overrides(frame_overrides)


def normalize_plan_frame_overrides(
    frame_overrides: Sequence[Mapping[str, Any]] | None,
    *,
    storyboard_plan: StoryboardPlan | None = None,
) -> list[dict[str, Any]]:
    if not frame_overrides:
        return []

    frame_ids = (
        {frame.frame_id for frame in storyboard_plan.frames}
        if storyboard_plan is not None
        else None
    )
    normalized: list[dict[str, Any]] = []
    for override in frame_overrides:
        if not isinstance(override, Mapping):
            raise ValueError("frame override must be a mapping")
        if set(override.keys()) & LEGACY_FRAME_OVERRIDE_IDENTITY_FIELDS:
            raise ValueError("legacy frame override identity is not supported")
        missing = PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS - set(override.keys())
        if missing:
            raise ValueError(f"frame override missing identity field: {sorted(missing)[0]}")
        invalid_keys = set(override.keys()) - PLAN_FRAME_OVERRIDE_ALLOWED_FIELDS
        if invalid_keys:
            raise ValueError(f"unsupported frame override field: {sorted(invalid_keys)[0]}")

        normalized_override = dict(override)
        _validate_identity_scalar("plan_id", normalized_override["plan_id"])
        _validate_identity_scalar("frame_id", normalized_override["frame_id"])
        _validate_source_digest(normalized_override["source_digest"])
        if type(normalized_override["plan_revision"]) is not int or normalized_override["plan_revision"] < 1:
            raise ValueError("frame override plan_revision must be a positive integer")

        locked_fields = _normalize_locked_fields(normalized_override.get("locked_fields"))
        normalized_override["locked_fields"] = locked_fields
        provided_fields = [
            field_name
            for field_name in PLAN_FRAME_OVERRIDE_VALUE_FIELDS
            if field_name in normalized_override and normalized_override[field_name] is not None
        ]
        for field_name in provided_fields:
            if field_name not in locked_fields:
                raise ValueError(f"frame override field {field_name} must be listed in locked_fields")
        _validate_mandatory_anchor_overrides(normalized_override)

        if storyboard_plan is not None:
            if normalized_override["plan_id"] != storyboard_plan.plan_id:
                raise ValueError("frame override plan_id does not match current storyboard plan")
            if normalized_override["plan_revision"] != storyboard_plan.revision:
                raise ValueError("frame override plan_revision does not match current storyboard plan")
            if normalized_override["source_digest"] != storyboard_plan.source_digest:
                raise ValueError("frame override source_digest does not match current storyboard plan")
            if normalized_override["frame_id"] not in frame_ids:
                raise ValueError("frame override frame_id does not match current storyboard plan")

        normalized.append(normalized_override)

    return normalized


def _validate_identity_scalar(field_name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"frame override {field_name} must be a non-empty string")


def _validate_source_digest(value: Any) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("frame override source_digest must be a SHA-256 hex digest")


def _validate_mandatory_anchor_overrides(override: dict[str, Any]) -> None:
    ratio = override.get("mandatory_anchor_area_ratio")
    if ratio is not None:
        if isinstance(ratio, bool):
            raise ValueError("mandatory anchor area ratio must be a number")
        try:
            numeric_ratio = float(ratio)
        except (TypeError, ValueError) as exc:
            raise ValueError("mandatory anchor area ratio must be a number") from exc
        if not 0.0 < numeric_ratio <= 1.0:
            raise ValueError("mandatory anchor area ratio must be in (0, 1]")
        if numeric_ratio != ratio:
            override["mandatory_anchor_area_ratio"] = numeric_ratio

    allowed_values = {
        "mandatory_anchor_horizontal_position": {
            "left",
            "center",
            "right",
            "cross_frame",
        },
        "mandatory_anchor_depth_position": {
            "foreground",
            "midground",
            "background",
            "full_frame",
        },
        "mandatory_anchor_visible_extent": {
            "full_body",
            "half_body",
            "partial",
            "distant_silhouette",
            "headshot",
            "recognizable_detail",
        },
    }
    for field_name, allowed in allowed_values.items():
        value = override.get(field_name)
        if value is not None and str(value).strip() not in allowed:
            raise ValueError(f"unsupported {field_name}: {value}")

    for field_name in (
        "mandatory_anchor_action_verb",
        "mandatory_anchor_interaction_target",
    ):
        value = override.get(field_name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{field_name} must be a non-empty string")


def _normalize_locked_fields(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("frame override locked_fields must be a non-empty list")

    locked_fields: list[str] = []
    for item in value:
        if item not in PLAN_FRAME_OVERRIDE_VALUE_FIELDS:
            raise ValueError(f"unsupported locked frame field: {item}")
        if item not in locked_fields:
            locked_fields.append(item)
    return locked_fields
