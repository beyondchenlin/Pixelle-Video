"""Shared ComfyUI error classification helpers."""


def looks_like_memory_exhaustion(error_message: str) -> bool:
    lowered = (error_message or "").lower()
    return any(
        marker in lowered
        for marker in (
            "not enough memory",
            "out of memory",
            "defaultcpuallocator",
            "std::bad_alloc",
        )
    )
