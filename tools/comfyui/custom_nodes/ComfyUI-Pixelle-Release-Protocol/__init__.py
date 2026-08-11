"""Pixelle Release Protocol - 提供 Pixelle 标准的健康检查和内存释放接口。

这个 ComfyUI 插件不依赖任何第三方修改，直接在内部实现对 OmniVoice、
GGUF、IndexTTS2 等插件的内存检测与释放。
"""

from aiohttp import web
from server import PromptServer

from . import protocol as _protocol


def _queue_counts() -> tuple[int, int] | None:
    prompt_queue = getattr(PromptServer.instance, "prompt_queue", None)
    if prompt_queue is None:
        return None
    try:
        running, pending = prompt_queue.get_current_queue_volatile()
    except Exception:
        return None
    return len(running), len(pending)


@PromptServer.instance.routes.get("/pixelle/health")
async def pixelle_health(request: web.Request) -> web.Response:
    return web.json_response(_protocol.unified_health())


@PromptServer.instance.routes.post("/pixelle/free")
async def pixelle_free(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except (ValueError, TypeError):
        payload = {}
    extensions = payload.get("extensions") if isinstance(payload, dict) else None
    queue_counts = _queue_counts()
    if queue_counts is None:
        return web.json_response(
            {"ok": False, "error": "queue_state_unavailable"},
            status=503,
        )
    running, pending = queue_counts
    if running or pending:
        return web.json_response(
            {
                "ok": False,
                "error": "queue_busy",
                "queue_running": running,
                "queue_pending": pending,
            },
            status=409,
        )
    try:
        result = _protocol.unified_release(extensions)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(result, status=200 if result.get("safe_to_continue") else 500)


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
