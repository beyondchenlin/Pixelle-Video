from pathlib import Path
from typing import Any

INDEX_TTS2_WORKFLOW_STEMS = frozenset({"tts_index2", "indextts2", "index_tts2"})


def is_index_tts2_workflow_key(workflow_key: Any) -> bool:
    workflow_stem = Path(str(workflow_key or "")).stem.lower()
    return workflow_stem in INDEX_TTS2_WORKFLOW_STEMS
