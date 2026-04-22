from dataclasses import dataclass, field
from typing import List, Sequence

from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.models.storyboard import StoryboardFrame
from pixelle_video.utils.text_splitting import (
    join_text_units,
    join_tts_sentence_units,
    split_text_into_sentences,
)


@dataclass
class TimingPlan:
    sentences: List[SentenceUnit] = field(default_factory=list)
    blocks: List[AudioBlock] = field(default_factory=list)


class TimingPlanner:
    def __init__(
        self,
        mode: str,
        max_sentences: int,
        max_chars: int,
        *,
        normalize_block_text_for_tts: bool = False,
    ):
        self.mode = (mode or "paragraph").strip().lower()
        self.max_sentences = max(1, max_sentences)
        self.max_chars = max(1, max_chars)
        self.normalize_block_text_for_tts = bool(normalize_block_text_for_tts)

    def build(self, frames: Sequence[StoryboardFrame]) -> TimingPlan:
        sentences = self._build_sentence_units(frames)
        blocks = self._build_audio_blocks(sentences)
        return TimingPlan(sentences=sentences, blocks=blocks)

    def _build_sentence_units(self, frames: Sequence[StoryboardFrame]) -> List[SentenceUnit]:
        sentences: List[SentenceUnit] = []
        for frame in frames:
            for sentence_offset, sentence_text in enumerate(
                split_text_into_sentences(frame.narration),
                start=1,
            ):
                sentences.append(
                    SentenceUnit(
                        id=f"sentence-{frame.index + 1}-{sentence_offset}",
                        text=sentence_text,
                        frame_indices=[frame.index],
                    )
                )
        return sentences

    def _build_audio_blocks(self, sentences: Sequence[SentenceUnit]) -> List[AudioBlock]:
        if not sentences:
            return []

        if self.mode == "sentence":
            return [
                self._create_block([sentence], position)
                for position, sentence in enumerate(sentences, start=1)
            ]

        blocks: List[AudioBlock] = []
        current_group: List[SentenceUnit] = []

        for sentence in sentences:
            if current_group and self._would_exceed_limits(current_group, sentence):
                blocks.append(self._create_block(current_group, len(blocks) + 1))
                current_group = [sentence]
            else:
                current_group.append(sentence)

        if current_group:
            blocks.append(self._create_block(current_group, len(blocks) + 1))

        return blocks

    def _would_exceed_limits(
        self,
        current_group: Sequence[SentenceUnit],
        next_sentence: SentenceUnit,
    ) -> bool:
        sentence_count = len(current_group) + 1
        if sentence_count > self.max_sentences:
            return True

        candidate_text = (
            join_tts_sentence_units(
                [*(sentence.text for sentence in current_group), next_sentence.text]
            )
            if self.normalize_block_text_for_tts
            else join_text_units(
                [*(sentence.text for sentence in current_group), next_sentence.text]
            )
        )
        return len(candidate_text) > self.max_chars

    def _create_block(
        self,
        sentence_units: Sequence[SentenceUnit],
        position: int,
    ) -> AudioBlock:
        block_id = f"block-{position}"
        for sentence in sentence_units:
            sentence.block_id = block_id

        return AudioBlock(
            id=block_id,
            text=(
                join_tts_sentence_units(sentence.text for sentence in sentence_units)
                if self.normalize_block_text_for_tts
                else join_text_units(sentence.text for sentence in sentence_units)
            ),
            source_frame_indices=[
                frame_index
                for sentence in sentence_units
                for frame_index in sentence.frame_indices
            ],
        )
