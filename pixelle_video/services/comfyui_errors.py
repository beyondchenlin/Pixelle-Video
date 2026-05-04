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


def looks_like_backend_connection_loss(error_message: str) -> bool:
    lowered = (error_message or "").lower()
    return any(
        marker in lowered
        for marker in (
            "cannot connect to host",
            "connection refused",
            "failed to establish a new connection",
            "actively refused",
            "server disconnected",
            "connection reset",
            "connection aborted",
            "clientconnectorerror",
            "clientoserror",
            "connect call failed",
            "远程计算机拒绝网络连接",
        )
    )
