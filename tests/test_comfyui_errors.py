from pixelle_video.services.comfyui_errors import (
    looks_like_backend_connection_loss,
    looks_like_memory_exhaustion,
)


def test_backend_connection_loss_matches_common_client_disconnects():
    messages = [
        "Cannot connect to host 127.0.0.1:8000 ssl:default [Connect call failed]",
        "Connection refused by ComfyUI backend",
        "Server disconnected while polling workflow history",
        "远程计算机拒绝网络连接",
    ]

    for message in messages:
        assert looks_like_backend_connection_loss(message)


def test_backend_connection_loss_does_not_match_memory_errors():
    assert not looks_like_backend_connection_loss("CUDA out of memory")
    assert looks_like_memory_exhaustion("CUDA out of memory")
