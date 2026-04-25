from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from pixelle_video.models.render_package import (
    CaptionCue,
    SentenceUnit,
    resolve_render_window,
)
from pixelle_video.models.text_style import DEFAULT_CAPTION_STYLE_ID
from pixelle_video.utils.text_splitting import (
    format_caption_text,
    split_text_into_subtitle_phrases,
)


def build_caption_cues_from_sentences(
    sentence_units: Sequence[SentenceUnit],
    *,
    style_profile: str = DEFAULT_CAPTION_STYLE_ID,
    punctuation_mode: str = "strip_all",
) -> list[CaptionCue]:
    captions: list[CaptionCue] = []
    for sentence in sentence_units:
        try:
            start, end = resolve_render_window(sentence)
        except ValueError:
            continue

        captions.extend(
            _build_sentence_caption_cues(
                sentence=sentence,
                start=float(start),
                end=float(end),
                style_profile=style_profile,
                punctuation_mode=punctuation_mode,
            )
        )
    return captions


def _build_sentence_caption_cues(
    *,
    sentence: SentenceUnit,
    start: float,
    end: float,
    style_profile: str,
    punctuation_mode: str,
) -> list[CaptionCue]:
    phrases = split_text_into_subtitle_phrases(sentence.text)
    if not phrases:
        return []

    if len(phrases) == 1 or end <= start:
        return [
            CaptionCue(
                id=sentence.id,
                text=format_caption_text(
                    sentence.text,
                    punctuation_mode=punctuation_mode,
                ),
                start=float(start),
                end=float(end),
                frame_indices=list(sentence.frame_indices),
                style_profile=style_profile,
            )
        ]

    weights = [_estimate_caption_phrase_weight(phrase) for phrase in phrases]
    total_weight = sum(weights) or len(phrases)
    span = float(end) - float(start)
    elapsed_weight = 0.0
    captions: list[CaptionCue] = []

    for index, (phrase, weight) in enumerate(zip(phrases, weights), start=1):
        cue_start = float(start) if index == 1 else captions[-1].end
        if index == len(phrases):
            cue_end = float(end)
        else:
            elapsed_weight += weight
            cue_end = float(start) + span * (elapsed_weight / total_weight)

        if cue_end <= cue_start:
            continue

        captions.append(
            CaptionCue(
                id=f"{sentence.id}-cue-{index}",
                text=format_caption_text(phrase, punctuation_mode=punctuation_mode),
                start=cue_start,
                end=cue_end,
                frame_indices=list(sentence.frame_indices),
                style_profile=style_profile,
            )
        )

    if not captions:
        return []

    captions[-1] = replace(captions[-1], end=float(end))
    return captions


def _estimate_caption_phrase_weight(text: str) -> int:
    visible_chars = [char for char in text if not char.isspace()]
    return max(1, len(visible_chars))
