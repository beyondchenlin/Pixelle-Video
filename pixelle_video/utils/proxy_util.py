"""自适应代理工具模块 - 自动检测并配置网络代理."""

from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from typing import Generator
from urllib.parse import urlparse

from loguru import logger


def _is_proxy_reachable(proxy_url: str, timeout: float = 3.0) -> bool:
    """检测代理是否可用."""
    if not proxy_url:
        return False

    try:
        parsed = urlparse(proxy_url)
        host = parsed.hostname
        port = parsed.port or (8080 if parsed.scheme in ("http", "https") else 1080)

        if not host:
            return False

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as exc:
        logger.debug(f"代理检测失败 {proxy_url}: {exc}")
        return False


def _get_proxy_from_env() -> tuple[str | None, str | None]:
    """从环境变量获取代理配置."""
    http_proxy = (
        os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
    )
    https_proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
    )
    return http_proxy, https_proxy


def detect_best_proxy() -> tuple[str | None, str | None]:
    """
    自动检测最佳代理配置.

    返回:
        (http_proxy, https_proxy) - 如果代理不可用则返回 (None, None)
    """
    http_proxy, https_proxy = _get_proxy_from_env()

    # 检查代理是否可用
    if http_proxy and _is_proxy_reachable(http_proxy):
        logger.info(f"使用 HTTP 代理: {http_proxy}")
        return http_proxy, https_proxy or http_proxy

    if https_proxy and _is_proxy_reachable(https_proxy):
        logger.info(f"使用 HTTPS 代理: {https_proxy}")
        return http_proxy or https_proxy, https_proxy

    # 代理不可用，使用直连
    logger.debug("代理不可用或环境变量未设置，使用直连")
    return None, None


@contextmanager
def adaptive_proxy_env() -> Generator[None, None, None]:
    """
    上下文管理器 - 自动配置最优代理环境.

    使用示例:
        with adaptive_proxy_env():
            # 这里的网络请求会自动使用最佳代理配置
            model_file_download(...)
    """
    http_proxy, https_proxy = detect_best_proxy()

    # 保存原始环境变量
    original_http = os.environ.get("HTTP_PROXY")
    original_https = os.environ.get("HTTPS_PROXY")
    original_http_lower = os.environ.get("http_proxy")
    original_https_lower = os.environ.get("https_proxy")

    try:
        if http_proxy:
            os.environ["HTTP_PROXY"] = http_proxy
            os.environ["http_proxy"] = http_proxy
        else:
            # 清除代理环境变量，强制直连
            os.environ.pop("HTTP_PROXY", None)
            os.environ.pop("http_proxy", None)

        if https_proxy:
            os.environ["HTTPS_PROXY"] = https_proxy
            os.environ["https_proxy"] = https_proxy
        else:
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("https_proxy", None)

        yield

    finally:
        # 恢复原始环境变量
        if original_http is not None:
            os.environ["HTTP_PROXY"] = original_http
        else:
            os.environ.pop("HTTP_PROXY", None)

        if original_https is not None:
            os.environ["HTTPS_PROXY"] = original_https
        else:
            os.environ.pop("HTTPS_PROXY", None)

        if original_http_lower is not None:
            os.environ["http_proxy"] = original_http_lower
        else:
            os.environ.pop("http_proxy", None)

        if original_https_lower is not None:
            os.environ["https_proxy"] = original_https_lower
        else:
            os.environ.pop("https_proxy", None)


def setup_adaptive_proxy() -> tuple[str | None, str | None]:
    """
    设置全局自适应代理.

    修改当前进程的环境变量为最佳代理配置.
    返回实际使用的代理地址.
    """
    http_proxy, https_proxy = detect_best_proxy()

    if http_proxy:
        os.environ["HTTP_PROXY"] = http_proxy
        os.environ["http_proxy"] = http_proxy
    else:
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("http_proxy", None)

    if https_proxy:
        os.environ["HTTPS_PROXY"] = https_proxy
        os.environ["https_proxy"] = https_proxy
    else:
        os.environ.pop("HTTPS_PROXY", None)
        os.environ.pop("https_proxy", None)

    return http_proxy, https_proxy
