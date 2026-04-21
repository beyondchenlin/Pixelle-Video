"""Alignment helpers for mapping forced-aligner output back onto render-package sentences."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, DefaultDict, List, Mapping, Protocol, Sequence

from pixelle_video.models.render_package import AudioBlock, SentenceUnit

DEFAULT_ALIGNMENT_MODEL_PATH = "models/Qwen3-ForcedAligner-0.6B"
DEFAULT_ALIGNMENT_LANGUAGE = "zh"

_TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?|[\u4e00-\u9fff]|[\u3040-\u30ff]|[\uac00-\ud7a3]+",
    re.UNICODE,
)
_TRAILING_SUBTITLE_PUNCTUATION = (
    "\u3002\uff01\uff1f!?.,;:\u3001\uff0c\uff1a\uff1b\u2026"
    "\"'\u201d\u2019)]}\u3009\u300b\u300d\u300f\u3015\u3011>"
)


class AlignmentClient(Protocol):
    def align(self, audio: Any, text: str, language: str = DEFAULT_ALIGNMENT_LANGUAGE) -> Any:
        ...


@dataclass(frozen=True)
class _FlattenedToken:
    token: str
    start: float
    end: float


class _QwenForcedAlignerClient:
    def __init__(self, model_path: str = DEFAULT_ALIGNMENT_MODEL_PATH):
        self.model_path = model_path
        self._aligner = None

    def _load_aligner(self):
        if self._aligner is not None:
            return self._aligner

        try:
            from qwen_asr.inference.qwen3_forced_aligner import Qwen3ForcedAligner
        except ImportError as exc:  # pragma: no cover - depends on optional runtime package
            raise RuntimeError(
                "qwen-asr is required for the default alignment client."
            ) from exc

        self._aligner = Qwen3ForcedAligner.from_pretrained(self.model_path)
        return self._aligner

    def align(self, audio: Any, text: str, language: str = DEFAULT_ALIGNMENT_LANGUAGE) -> Any:
        aligner = self._load_aligner()
        results = aligner.align(audio=audio, text=text, language=language)
        if isinstance(results, list):
            return results[0] if results else None
        return results


class AlignmentService:
    def __init__(
        self,
        client: AlignmentClient | None = None,
        language: str = DEFAULT_ALIGNMENT_LANGUAGE,
    ):
        self.client = client or _QwenForcedAlignerClient()
        self.language = language

    def align_block(
        self,
        block: AudioBlock,
        sentences: Sequence[SentenceUnit],
        language: str | None = None,
    ) -> List[SentenceUnit]:
        if not sentences:
            return list(sentences)
        if not block.audio_path:
            raise ValueError(f"Audio block {block.id!r} is missing audio_path for alignment.")

        alignment = self.client.align(
            audio=block.audio_path,
            text=block.text,
            language=language or self.language,
        )
        flattened_words = self._flatten_aligned_words(alignment)
        self._apply_alignment(sentences, flattened_words)
        return list(sentences)

    def align_blocks(
        self,
        blocks: Sequence[AudioBlock],
        sentences: Sequence[SentenceUnit],
        language: str | None = None,
    ) -> List[SentenceUnit]:
        sentence_groups: DefaultDict[str | None, List[SentenceUnit]] = defaultdict(list)
        for sentence in sentences:
            sentence_groups[sentence.block_id].append(sentence)

        for block in blocks:
            group = sentence_groups.get(block.id, [])
            if group:
                self.align_block(block, group, language=language)

        return list(sentences)

    def _apply_alignment(
        self,
        sentences: Sequence[SentenceUnit],
        flattened_words: Sequence[_FlattenedToken],
    ) -> None:
        word_index = 0
        for sentence in sentences:
            sentence_tokens = self._tokenize_sentence_text(sentence.text)
            if not sentence_tokens:
                continue

            search_index = word_index
            matched_start: float | None = None
            matched_end: float | None = None
            matched = True

            for token in sentence_tokens:
                while (
                    search_index < len(flattened_words)
                    and flattened_words[search_index].token != token
                ):
                    search_index += 1
                if search_index >= len(flattened_words):
                    matched = False
                    break

                if matched_start is None:
                    matched_start = flattened_words[search_index].start
                matched_end = flattened_words[search_index].end
                search_index += 1

            if matched and matched_start is not None and matched_end is not None:
                sentence.source_start = matched_start
                sentence.source_end = matched_end
                word_index = search_index

    def _flatten_aligned_words(self, alignment: Any) -> List[_FlattenedToken]:
        words = self._extract_words(alignment)
        flattened: List[_FlattenedToken] = []

        for word in words:
            text = self._extract_word_text(word)
            start = self._extract_word_start(word)
            end = self._extract_word_end(word)
            for token in self._tokenize_word_text(text):
                flattened.append(_FlattenedToken(token=token, start=start, end=end))

        return flattened

    def _extract_words(self, alignment: Any) -> List[Any]:
        if alignment is None:
            return []
        if isinstance(alignment, list):
            if not alignment:
                return []
            alignment = alignment[0]
        if isinstance(alignment, Mapping):
            words = alignment.get("words")
            if words is None:
                words = alignment.get("items")
            return list(words or [])

        words = getattr(alignment, "items", None)
        if words is None:
            words = getattr(alignment, "words", None)
        if words is None:
            return []
        return list(words)

    def _extract_word_text(self, word: Any) -> str:
        if isinstance(word, Mapping):
            return str(word.get("text", ""))
        return str(getattr(word, "text", ""))

    def _extract_word_start(self, word: Any) -> float:
        if isinstance(word, Mapping):
            value = word.get("start_time", word.get("start", 0.0))
        else:
            value = getattr(word, "start_time", getattr(word, "start", 0.0))
        return float(value or 0.0)

    def _extract_word_end(self, word: Any) -> float:
        if isinstance(word, Mapping):
            value = word.get("end_time", word.get("end", 0.0))
        else:
            value = getattr(word, "end_time", getattr(word, "end", 0.0))
        return float(value or 0.0)

    def _tokenize_sentence_text(self, text: str) -> List[str]:
        return self._tokenize_text(self._strip_trailing_subtitle_punctuation(text))

    def _tokenize_word_text(self, text: str) -> List[str]:
        return self._tokenize_text(text)

    def _tokenize_text(self, text: str) -> List[str]:
        return [token for token in _TOKEN_RE.findall(text) if token]

    def _strip_trailing_subtitle_punctuation(self, text: str) -> str:
        return text.strip().rstrip(_TRAILING_SUBTITLE_PUNCTUATION)
