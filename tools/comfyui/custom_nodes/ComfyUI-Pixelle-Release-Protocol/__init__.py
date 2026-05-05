"""Pixelle Release Protocol - 提供 Pixelle 标准的健康检查和内存释放接口。

这个 ComfyUI 插件不依赖任何第三方修改，直接在内部实现对 OmniVoice、
GGUF、IndexTTS2 等插件的内存检测与释放。
"""

from aiohttp import web
from server import PromptServer

from . import protocol as _protocol


@PromptServer.instance.routes.get("/pixelle/health")
async def pixelle_health(request: web.Request) -> web.Response:
    return web.json_response(_protocol.unified_health())


@PromptServer.instance.routes.post("/pixelle/free")
async def pixelle_free(request: web.Request) -> web.Response:
    return web.json_response(_protocol.unified_release())


@PromptServer.instance.routes.get("/pixelle/omnivoice/health")
async def omnivoice_health(request: web.Request) -> web.Response:
    return web.json_response(_protocol.omnivoice_health())


@PromptServer.instance.routes.post("/pixelle/omnivoice/free")
async def omnivoice_free(request: web.Request) -> web.Response:
    return web.json_response(_protocol.omnivoice_release())


@PromptServer.instance.routes.get("/pixelle/gguf/health")
async def gguf_health(request: web.Request) -> web.Response:
    return web.json_response(_protocol.gguf_health())


@PromptServer.instance.routes.post("/pixelle/gguf/free")
async def gguf_free(request: web.Request) -> web.Response:
    return web.json_response(_protocol.gguf_release())


@PromptServer.instance.routes.get("/pixelle/indextts2/health")
async def indextts2_health(request: web.Request) -> web.Response:
    return web.json_response(_protocol.indextts2_health())


@PromptServer.instance.routes.post("/pixelle/indextts2/free")
async def indextts2_free(request: web.Request) -> web.Response:
    return web.json_response(_protocol.indextts2_release())


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
