"""Progress event localization helpers for web UI."""

from loguru import logger

from pixelle_video.models.progress import (
    ProgressEvent,
    ProgressEventType,
    ProgressI18nMessage,
    progress_event_i18n_key,
    progress_frame_action_i18n_key,
)
from web.i18n import tr


def localize_progress_extra_info(extra_info) -> str:
    if extra_info is None:
        return ""

    if isinstance(extra_info, ProgressI18nMessage):
        return tr(
            extra_info.key,
            fallback=extra_info.fallback,
            **dict(extra_info.params),
        )

    text = str(extra_info).strip()
    if not text:
        return ""
    return tr(text, fallback=text)


def format_progress_event_message(event: ProgressEvent) -> str:
    if event.event_type == ProgressEventType.FRAME_STEP:
        action_key = progress_frame_action_i18n_key(event.action)
        if action_key is None:
            logger.warning(f"Unregistered progress frame action: {event.action}")
            action_text = tr("progress.generation")
        else:
            action_text = tr(action_key)

        message_key = progress_event_i18n_key(ProgressEventType.FRAME_STEP)
        return tr(
            message_key or "progress.frame_step",
            current=event.frame_current,
            total=event.frame_total,
            step=event.step,
            action=action_text,
        )

    if event.event_type == ProgressEventType.PROCESSING_FRAME:
        message_key = progress_event_i18n_key(ProgressEventType.PROCESSING_FRAME)
        return tr(
            message_key or "progress.frame",
            current=event.frame_current,
            total=event.frame_total,
        )

    message_key = progress_event_i18n_key(event.event_type)
    if message_key is None:
        logger.warning(f"Unregistered progress event type: {event.event_type}")
        message_key = progress_event_i18n_key(ProgressEventType.GENERATION) or "progress.generation"

    return tr(message_key)
