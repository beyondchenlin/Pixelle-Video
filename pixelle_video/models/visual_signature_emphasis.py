from __future__ import annotations

from enum import Enum


class VisualSignatureEmphasis(str, Enum):
    """Series-level visual prominence assigned before per-frame model calls."""

    STANDARD = "standard"
    ENHANCED = "enhanced"


__all__ = ["VisualSignatureEmphasis"]
