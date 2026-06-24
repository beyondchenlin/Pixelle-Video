from pixelle_video.services.comfyui_errors import (
    looks_like_backend_connection_loss,
    looks_like_memory_exhaustion,
    looks_like_transient_backend_execution_error,
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


def test_memory_exhaustion_matches_cuda_allocator_failure():
    assert looks_like_memory_exhaustion("fatal   : Memory allocation failure")
    assert looks_like_memory_exhaustion("CUBLAS_STATUS_ALLOC_FAILED")


def test_transient_backend_execution_error_matches_cuda_engine_failure():
    assert looks_like_transient_backend_execution_error(
        "GET was unable to find an engine to execute this computation\n"
    )
    assert looks_like_transient_backend_execution_error(
        "CUDA error: unknown error\nSearch for `cudaErrorUnknown' in CUDA docs."
    )
    assert not looks_like_transient_backend_execution_error(
        "required_identity_trait_missing"
    )
