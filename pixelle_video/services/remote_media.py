from __future__ import annotations

import asyncio
import ipaddress
import math
import os
import socket
import tempfile
from collections.abc import Iterable
from pathlib import Path, PureWindowsPath
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from pixelle_video.utils.os_util import get_output_path, get_temp_path

MediaType = Literal["audio", "image", "video"]
DEFAULT_MAX_MEDIA_BYTES = {
    "audio": 100 * 1024 * 1024,
    "image": 25 * 1024 * 1024,
    "video": 512 * 1024 * 1024,
}


class RemoteMediaError(RuntimeError):
    """Raised when a workflow output cannot be materialized safely."""


async def materialize_media_source(
    source: str,
    target: str | Path,
    *,
    media_type: MediaType,
    max_bytes: int | None = None,
    trusted_private_origins: Iterable[str] = (),
    trusted_local_roots: Iterable[str | Path] = (),
    client: httpx.AsyncClient | None = None,
    max_redirects: int = 3,
    request_timeout_seconds: float = 300.0,
) -> Path:
    """Stream one local or remote workflow output into an atomic local artifact."""

    if media_type not in DEFAULT_MAX_MEDIA_BYTES:
        raise ValueError("unsupported media type")
    byte_limit = DEFAULT_MAX_MEDIA_BYTES[media_type] if max_bytes is None else max_bytes
    if isinstance(byte_limit, bool) or not isinstance(byte_limit, int) or byte_limit < 1:
        raise ValueError("max_bytes must be positive")
    if (
        isinstance(max_redirects, bool)
        or not isinstance(max_redirects, int)
        or max_redirects < 0
        or max_redirects > 10
    ):
        raise ValueError("max_redirects must be between zero and ten")
    if (
        isinstance(request_timeout_seconds, bool)
        or not isinstance(request_timeout_seconds, (int, float))
        or not math.isfinite(request_timeout_seconds)
        or request_timeout_seconds <= 0
        or request_timeout_seconds > 3600
    ):
        raise ValueError("request_timeout_seconds must be between zero and 3600")

    source_text = str(source or "").strip()
    if not source_text:
        raise RemoteMediaError("workflow output source is empty")
    target_path = Path(target).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    parsed = urlsplit(source_text)
    if parsed.scheme.lower() not in {"http", "https"}:
        if parsed.scheme and not PureWindowsPath(source_text).is_absolute():
            raise RemoteMediaError("workflow output URL scheme is not allowed")
        local_roots = [target_path.parent, *trusted_local_roots]
        return await asyncio.to_thread(
            _copy_local_media_atomically,
            Path(source_text),
            target_path,
            media_type,
            byte_limit,
            local_roots,
        )

    trusted = {_normalize_origin(value) for value in trusted_private_origins}
    timeout = httpx.Timeout(
        connect=min(10.0, request_timeout_seconds),
        read=request_timeout_seconds,
        write=min(30.0, request_timeout_seconds),
        pool=min(10.0, request_timeout_seconds),
    )
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    )
    try:
        return await _download_media_atomically(
            active_client,
            source_text,
            target_path,
            media_type=media_type,
            max_bytes=byte_limit,
            trusted_private_origins=trusted,
            max_redirects=max_redirects,
        )
    finally:
        if owns_client:
            await active_client.aclose()


def configured_workflow_output_origins(core: object) -> tuple[str, ...]:
    """Return explicitly configured ComfyUI origins that may resolve to private hosts."""

    config = getattr(core, "config", {}) or {}
    comfyui = config.get("comfyui", {}) if isinstance(config, dict) else {}
    candidates: list[str] = []
    if isinstance(comfyui, dict):
        top_level_url = comfyui.get("comfyui_url")
        if isinstance(top_level_url, str) and top_level_url.strip():
            candidates.append(top_level_url)
        backends = comfyui.get("backends", {})
        if isinstance(backends, dict):
            for profile in backends.values():
                if not isinstance(profile, dict):
                    continue
                url = profile.get("url")
                if isinstance(url, str) and url.strip():
                    candidates.append(url)
    normalized: list[str] = []
    for value in candidates:
        try:
            origin = _origin_text(_normalize_origin(value))
        except RemoteMediaError:
            continue
        if origin not in normalized:
            normalized.append(origin)
    return tuple(normalized)


def configured_workflow_output_roots() -> tuple[Path, ...]:
    """Return local runtime roots permitted to contain workflow outputs."""

    return (Path(get_output_path()).resolve(), Path(get_temp_path()).resolve())


async def _download_media_atomically(
    client: httpx.AsyncClient,
    source_url: str,
    target: Path,
    *,
    media_type: MediaType,
    max_bytes: int,
    trusted_private_origins: set[tuple[str, str, int]],
    max_redirects: int,
) -> Path:
    current_url = source_url
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            for redirect_count in range(max_redirects + 1):
                allow_private = await _validate_remote_url(
                    current_url,
                    trusted_private_origins=trusted_private_origins,
                )
                async with client.stream("GET", current_url, follow_redirects=False) as response:
                    _validate_connected_peer(response, allow_private=allow_private)
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count >= max_redirects:
                            raise RemoteMediaError("workflow output exceeded the redirect limit")
                        location = response.headers.get("location")
                        if not location:
                            raise RemoteMediaError("workflow output redirect omitted its location")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    _validate_content_headers(
                        response,
                        media_type=media_type,
                        max_bytes=max_bytes,
                    )
                    total = 0
                    header = bytearray()
                    async for chunk in response.aiter_bytes(64 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > max_bytes:
                            raise RemoteMediaError(
                                "workflow output exceeded the configured byte limit"
                            )
                        if len(header) < 64:
                            header.extend(chunk[: 64 - len(header)])
                        handle.write(chunk)
                    if total < 1:
                        raise RemoteMediaError("workflow output was empty")
                    _validate_media_header(bytes(header), media_type=media_type)
                    handle.flush()
                    os.fsync(handle.fileno())
                    break
            else:  # pragma: no cover - loop guard
                raise RemoteMediaError("workflow output redirect handling failed")
        temporary_path.replace(target)
        return target
    except httpx.HTTPStatusError as exc:
        raise RemoteMediaError(
            f"workflow output download failed with status {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RemoteMediaError("workflow output download failed") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


async def _validate_remote_url(
    value: str,
    *,
    trusted_private_origins: set[tuple[str, str, int]],
) -> bool:
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise RemoteMediaError("workflow output URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise RemoteMediaError("workflow output URL must not contain user information")
    try:
        origin = _normalize_origin(value)
    except ValueError as exc:
        raise RemoteMediaError("workflow output URL contains an invalid port") from exc
    allow_private = origin in trusted_private_origins

    host = parsed.hostname
    port = origin[2]
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            addresses = await asyncio.to_thread(_resolve_host_addresses, host, port)
        except OSError as exc:
            raise RemoteMediaError("workflow output host could not be resolved") from exc
    else:
        addresses = {literal}
    if not addresses:
        raise RemoteMediaError("workflow output host did not resolve to an address")
    if not allow_private and any(not address.is_global for address in addresses):
        raise RemoteMediaError("workflow output URL resolves to a non-public address")
    return allow_private


def _resolve_host_addresses(
    host: str, port: int
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        addresses.add(ipaddress.ip_address(item[4][0]))
    return addresses


def _validate_connected_peer(response: httpx.Response, *, allow_private: bool) -> None:
    if allow_private:
        return
    stream = response.extensions.get("network_stream")
    get_extra_info = getattr(stream, "get_extra_info", None)
    if not callable(get_extra_info):
        raise RemoteMediaError("workflow output connection peer could not be verified")
    peer = get_extra_info("server_addr")
    if not peer:
        raise RemoteMediaError("workflow output connection peer could not be verified")
    try:
        address = ipaddress.ip_address(peer[0] if isinstance(peer, tuple) else peer)
    except ValueError as exc:
        raise RemoteMediaError("workflow output connection peer address is invalid") from exc
    if not address.is_global:
        raise RemoteMediaError("workflow output connection reached a non-public address")


def _validate_content_headers(
    response: httpx.Response,
    *,
    media_type: MediaType,
    max_bytes: int,
) -> None:
    length_header = response.headers.get("content-length")
    if length_header:
        try:
            content_length = int(length_header)
        except ValueError as exc:
            raise RemoteMediaError("workflow output content length is invalid") from exc
        if content_length < 0 or content_length > max_bytes:
            raise RemoteMediaError("workflow output exceeded the configured byte limit")

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type:
        return
    if content_type in {"application/octet-stream", "binary/octet-stream"}:
        return
    if not content_type.startswith(f"{media_type}/"):
        raise RemoteMediaError("workflow output content type does not match the expected media")


def _copy_local_media_atomically(
    source: Path,
    target: Path,
    media_type: MediaType,
    max_bytes: int,
    trusted_local_roots: Iterable[str | Path],
) -> Path:
    resolved_source = source.expanduser().resolve()
    resolved_roots = [Path(root).expanduser().resolve() for root in trusted_local_roots]
    if not any(
        resolved_source == root or resolved_source.is_relative_to(root) for root in resolved_roots
    ):
        raise RemoteMediaError("local workflow output is outside trusted runtime roots")
    if not resolved_source.is_file():
        raise RemoteMediaError("local workflow output is not an existing file")
    temporary_path: Path | None = None
    try:
        with resolved_source.open("rb") as source_handle:
            source_size = os.fstat(source_handle.fileno()).st_size
            if source_size < 1 or source_size > max_bytes:
                raise RemoteMediaError("workflow output exceeded the configured byte limit")
            _validate_media_header(source_handle.read(64), media_type=media_type)
            source_handle.seek(0)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                total = 0
                while chunk := source_handle.read(64 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise RemoteMediaError("workflow output exceeded the configured byte limit")
                    handle.write(chunk)
                if total < 1:
                    raise RemoteMediaError("workflow output was empty")
                handle.flush()
                os.fsync(handle.fileno())
        with temporary_path.open("rb") as copied_handle:
            _validate_media_header(copied_handle.read(64), media_type=media_type)
        temporary_path.replace(target)
        return target
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _validate_media_header(header: bytes, *, media_type: MediaType) -> None:
    if media_type == "video":
        valid = (
            (len(header) >= 12 and header[4:8] in {b"ftyp", b"styp"})
            or header.startswith(b"\x1aE\xdf\xa3")
            or (len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ")
        )
    elif media_type == "audio":
        valid = (
            header.startswith((b"ID3", b"fLaC", b"OggS"))
            or (len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE")
            or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
        )
    else:
        valid = header.startswith(
            (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")
        ) or (len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
    if not valid:
        raise RemoteMediaError("workflow output media signature is invalid")


def _normalize_origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(str(value or "").strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise RemoteMediaError("trusted media origin must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise RemoteMediaError("trusted media origin must not contain user information")
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise RemoteMediaError("trusted media origin contains an invalid port") from exc
    return scheme, parsed.hostname.lower().rstrip("."), port


def _origin_text(origin: tuple[str, str, int]) -> str:
    scheme, host, port = origin
    default_port = 443 if scheme == "https" else 80
    display_host = f"[{host}]" if ":" in host else host
    netloc = display_host if port == default_port else f"{display_host}:{port}"
    return urlunsplit((scheme, netloc, "", "", ""))


__all__ = [
    "DEFAULT_MAX_MEDIA_BYTES",
    "RemoteMediaError",
    "configured_workflow_output_origins",
    "configured_workflow_output_roots",
    "materialize_media_source",
]
