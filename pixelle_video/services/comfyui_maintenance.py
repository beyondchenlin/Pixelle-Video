from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Literal

import httpx
from loguru import logger

ComfyUIReleaseIntensity = Literal["high", "low"]
ComfyUIExtensionName = Literal["indextts2", "gguf", "omnivoice"]
ComfyUIExtensionMissingEndpointMode = Literal["optional", "required"]
_IDLE_POLL_INTERVAL_SECONDS = 0.2
_RELEASE_SETTLE_POLL_INTERVAL_SECONDS = 0.5
_RELEASE_MIN_VRAM_FREE_GAIN_BYTES = 512 * 1024 * 1024


_FREE_MEMORY_PAYLOADS: dict[ComfyUIReleaseIntensity, dict[str, bool]] = {
    "high": {"unload_models": True, "free_memory": True},
    "low": {"unload_models": True, "free_memory": False},
}

_EXTENSION_RELEASE_ENDPOINTS: dict[ComfyUIExtensionName, str] = {
    "indextts2": "/pixelle/indextts2/free",
    "gguf": "/pixelle/gguf/free",
    "omnivoice": "/pixelle/omnivoice/free",
}
_EXTENSION_HEALTH_ENDPOINTS: dict[ComfyUIExtensionName, str] = {
    "indextts2": "/pixelle/indextts2/health",
    "gguf": "/pixelle/gguf/health",
    "omnivoice": "/pixelle/omnivoice/health",
}
_UNIFIED_RELEASE_HEALTH_ENDPOINT = "/pixelle/health"
_UNIFIED_RELEASE_ENDPOINT = "/pixelle/free"
_UNIFIED_TARGETED_RELEASE_CONTRACT_REVISION = 1
_EXTENSION_PATCH_INSTRUCTIONS: dict[ComfyUIExtensionName, str] = {
    "indextts2": (
        "Install or update ComfyUI-Pixelle-Release-Protocol with "
        "tools/install_pixelle_release_protocol.py, then restart ComfyUI."
    ),
    "gguf": (
        "Install or update ComfyUI-Pixelle-Release-Protocol with "
        "tools/install_pixelle_release_protocol.py, then restart ComfyUI."
    ),
    "omnivoice": (
        "Install or update ComfyUI-Pixelle-Release-Protocol with "
        "tools/install_pixelle_release_protocol.py, then restart ComfyUI."
    ),
}
_EXTENSION_MIN_CONTRACT_REVISIONS: dict[ComfyUIExtensionName, int] = {
    "gguf": 2,
}

_VRAM_RESPONSE_KEYS = (
    "cuda_allocated_before",
    "cuda_allocated_after",
    "cuda_reserved_before",
    "cuda_reserved_after",
)
_SYSTEM_VRAM_DEVICE_KEYS = (
    "name",
    "type",
    "vram_total",
    "vram_free",
    "torch_vram_total",
    "torch_vram_free",
)


def validate_comfyui_system_stats_payload(payload: Any) -> dict[str, Any]:
    """Validate the minimal response contract shared by every ComfyUI probe."""
    if not isinstance(payload, dict) or not isinstance(payload.get("system"), dict):
        raise RuntimeError(
            "ComfyUI /system_stats response is missing the required system object"
        )
    return payload


@dataclass(frozen=True)
class ComfyUIExtensionReleaseResult:
    extension: str
    endpoint: str
    released: bool
    safe_to_continue: bool = False
    protocol_version: int | None = None
    contract_revision: int | None = None
    missing_endpoint: bool = False
    message: str = ""
    response: dict[str, Any] | None = None

    def to_log_dict(self) -> dict[str, Any]:
        vram = {}
        if self.response is not None:
            vram = {
                key: self.response[key]
                for key in _VRAM_RESPONSE_KEYS
                if key in self.response
            }
        return {
            "extension": self.extension,
            "endpoint": self.endpoint,
            "released": self.released,
            "safe_to_continue": self.safe_to_continue,
            "protocol_version": self.protocol_version,
            "contract_revision": self.contract_revision,
            "missing_endpoint": self.missing_endpoint,
            "message": self.message,
            "vram": vram,
            "raw_response": self.response or {},
        }


@dataclass(frozen=True)
class ComfyUIMemoryReleaseResult:
    attempted: bool
    released: bool
    comfyui_released: bool = False
    skipped: bool = False
    skipped_reason: str = ""
    intensity: ComfyUIReleaseIntensity | None = None
    queue_running: int | None = None
    queue_pending: int | None = None
    system_vram_before: dict[str, Any] | None = None
    system_vram_after: dict[str, Any] | None = None
    release_confirmed: bool = False
    release_confirmation_reason: str = ""
    safe_to_continue: bool = False
    extensions: tuple[ComfyUIExtensionReleaseResult, ...] = ()

    def __bool__(self) -> bool:
        return self.released

    def to_log_fields(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "released": self.released,
            "comfyui_released": self.comfyui_released,
            "skipped": self.skipped,
            "skipped_reason": self.skipped_reason,
            "intensity": self.intensity,
            "queue_running": self.queue_running,
            "queue_pending": self.queue_pending,
            "system_vram_before": self.system_vram_before,
            "system_vram_after": self.system_vram_after,
            "release_confirmed": self.release_confirmed,
            "release_confirmation_reason": self.release_confirmation_reason,
            "safe_to_continue": self.safe_to_continue,
            "extension_results": [
                extension.to_log_dict()
                for extension in self.extensions
            ],
        }


@dataclass(frozen=True)
class ComfyUIQueueState:
    """Non-destructive snapshot of the shared ComfyUI queue."""

    running: int
    pending: int

    @property
    def busy(self) -> bool:
        return self.running > 0 or self.pending > 0


class ComfyUIMaintenanceClient:
    """Small client for ComfyUI maintenance endpoints used before long renders."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 5.0,
        system_stats_timeout: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        idle_wait_timeout: float = 20.0,
        release_settle_timeout: float = 30.0,
        release_poll_interval: float = _RELEASE_SETTLE_POLL_INTERVAL_SECONDS,
        release_request_timeout: float = 60.0,
        extension_preflight_timeout: float = 15.0,
    ) -> None:
        if idle_wait_timeout <= 0:
            raise ValueError("idle_wait_timeout must be positive")
        if system_stats_timeout <= 0:
            raise ValueError("system_stats_timeout must be positive")
        if release_settle_timeout <= 0:
            raise ValueError("release_settle_timeout must be positive")
        if release_poll_interval <= 0:
            raise ValueError("release_poll_interval must be positive")
        if release_request_timeout <= 0:
            raise ValueError("release_request_timeout must be positive")
        if extension_preflight_timeout <= 0:
            raise ValueError("extension_preflight_timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.system_stats_timeout = system_stats_timeout
        self.transport = transport
        self.idle_wait_timeout = idle_wait_timeout
        self.release_settle_timeout = release_settle_timeout
        self.release_poll_interval = release_poll_interval
        self.release_request_timeout = release_request_timeout
        self.extension_preflight_timeout = extension_preflight_timeout

    async def probe_backend(self) -> dict[str, Any]:
        """Verify that the configured endpoint is a compatible ComfyUI server."""
        response = await self._request(
            "GET",
            "/system_stats",
            timeout=self.timeout,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("ComfyUI /system_stats returned invalid JSON") from exc
        return validate_comfyui_system_stats_payload(payload)

    async def inspect_queue_before_generation(self) -> ComfyUIQueueState:
        """Observe the shared queue without interrupting or deleting foreign work."""
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        state = ComfyUIQueueState(running=running, pending=pending)
        if state.busy:
            logger.info(
                "Preserving existing ComfyUI queue before generation "
                f"(running={running}, pending={pending})"
            )
        else:
            logger.info("ComfyUI queue is idle before generation")
        return state

    async def wait_until_idle(self) -> ComfyUIQueueState:
        """Wait until no running or pending prompt remains without mutating the queue."""
        await self._wait_until_idle()
        return ComfyUIQueueState(running=0, pending=0)

    async def cleanup_before_generation(self) -> ComfyUIQueueState:
        """Compatibility alias for the now non-destructive queue inspection."""
        return await self.inspect_queue_before_generation()

    async def force_cleanup(self) -> None:
        """Explicit emergency operation that interrupts and clears the global queue."""
        await self._force_cleanup()

    async def _force_cleanup(self) -> None:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running == 0 and pending == 0:
            logger.info("Skipping force ComfyUI queue cleanup because queue is already idle")
            return

        logger.info(
            "Running force ComfyUI queue cleanup before video generation "
            f"(running={running}, pending={pending})"
        )
        await self._post("/interrupt", {})
        await self._post("/queue", {"clear": True})
        await self._wait_until_idle()

    async def free_memory(
        self,
        intensity: ComfyUIReleaseIntensity = "high",
    ) -> ComfyUIMemoryReleaseResult:
        payload = _FREE_MEMORY_PAYLOADS.get(intensity)
        if payload is None:
            raise ValueError(f"Unsupported ComfyUI release intensity: {intensity}")
        system_vram_before = await self._get_system_vram_snapshot()
        await self._post("/free", dict(payload))
        system_vram_after, release_confirmed, release_confirmation_reason = (
            await self._wait_for_memory_release_confirmation(system_vram_before)
        )
        return ComfyUIMemoryReleaseResult(
            attempted=True,
            released=release_confirmed,
            comfyui_released=release_confirmed,
            intensity=intensity,
            system_vram_before=system_vram_before,
            system_vram_after=system_vram_after,
            release_confirmed=release_confirmed,
            release_confirmation_reason=release_confirmation_reason,
        )

    async def free_memory_with_extensions(
        self,
        intensity: ComfyUIReleaseIntensity = "high",
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> ComfyUIMemoryReleaseResult:
        payload = _FREE_MEMORY_PAYLOADS.get(intensity)
        if payload is None:
            raise ValueError(f"Unsupported ComfyUI release intensity: {intensity}")

        system_vram_before = await self._get_system_vram_snapshot()
        extension_results = await self.free_extension_models(
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        await self._post("/free", dict(payload))
        system_vram_after, release_confirmed, release_confirmation_reason = (
            await self._wait_for_memory_release_confirmation(system_vram_before)
        )
        safe_to_continue, extension_reason = self._extension_release_confirmation(
            extension_results
        )
        released = safe_to_continue
        if safe_to_continue and not release_confirmed:
            release_confirmation_reason = extension_reason
        elif not safe_to_continue and extension_reason:
            release_confirmation_reason = extension_reason

        return ComfyUIMemoryReleaseResult(
            attempted=True,
            released=released,
            comfyui_released=release_confirmed,
            intensity=intensity,
            system_vram_before=system_vram_before,
            system_vram_after=system_vram_after,
            release_confirmed=release_confirmed,
            release_confirmation_reason=release_confirmation_reason,
            safe_to_continue=safe_to_continue,
            extensions=extension_results,
        )

    async def free_memory_with_extensions_when_idle(
        self,
        *,
        intensity: ComfyUIReleaseIntensity = "high",
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> ComfyUIMemoryReleaseResult:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI memory and extension release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return ComfyUIMemoryReleaseResult(
                attempted=False,
                released=False,
                skipped=True,
                skipped_reason="queue_busy",
                intensity=intensity,
                queue_running=running,
                queue_pending=pending,
            )

        logger.info(
            "Releasing ComfyUI memory and extension caches after idle workflow "
            f"completion ({intensity})"
        )
        result = await self.free_memory_with_extensions(
            intensity,
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        return replace(result, queue_running=running, queue_pending=pending)

    async def preflight_extension_release_endpoints(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "required",
    ) -> tuple[ComfyUIExtensionReleaseResult, ...]:
        unified_discovery = await self._get_unified_extension_capabilities()
        unified_capabilities = unified_discovery[1] if unified_discovery else None
        results: list[ComfyUIExtensionReleaseResult] = []
        for extension in extensions:
            unified_result = self._preflight_result_from_unified_capabilities(
                extension,
                unified_capabilities,
            )
            if unified_result is not None:
                results.append(unified_result)
                continue

            results.append(
                await self._preflight_legacy_extension_health_endpoint(
                    extension,
                    missing_endpoint=missing_endpoint,
                )
            )
        return tuple(results)

    async def _get_unified_extension_capabilities(
        self,
    ) -> tuple[int | None, dict[str, Any]] | None:
        try:
            response = await self._request(
                "GET",
                _UNIFIED_RELEASE_HEALTH_ENDPOINT,
                timeout=self.extension_preflight_timeout,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict) or self._parse_protocol_version(payload) != 2:
            return None
        capabilities = payload.get("extensions")
        if not isinstance(capabilities, dict):
            return None
        normalized_capabilities: dict[str, Any] = {}
        for extension, capability in capabilities.items():
            if not isinstance(capability, dict):
                continue
            normalized_capability = dict(capability)
            normalized_capability.setdefault("protocol_version", 2)
            normalized_capabilities[str(extension)] = normalized_capability
        return self._parse_contract_revision(payload), normalized_capabilities

    def _preflight_result_from_unified_capabilities(
        self,
        extension: ComfyUIExtensionName,
        capabilities: dict[str, Any] | None,
    ) -> ComfyUIExtensionReleaseResult | None:
        if capabilities is None:
            return None
        capability = capabilities.get(extension)
        if not isinstance(capability, dict) or not bool(capability.get("ok")):
            return None

        release_endpoint = str(
            capability.get("release_endpoint") or capability.get("endpoint") or ""
        ).strip()
        if release_endpoint not in {
            _UNIFIED_RELEASE_ENDPOINT,
            _EXTENSION_RELEASE_ENDPOINTS[extension],
        }:
            return None

        protocol_version = self._parse_protocol_version(capability)
        if protocol_version != 2:
            return None
        contract_revision = self._parse_contract_revision(capability)
        minimum_revision = _EXTENSION_MIN_CONTRACT_REVISIONS.get(extension)
        if minimum_revision is not None and (
            contract_revision is None or contract_revision < minimum_revision
        ):
            return None

        return ComfyUIExtensionReleaseResult(
            extension=extension,
            endpoint=_UNIFIED_RELEASE_HEALTH_ENDPOINT,
            released=False,
            safe_to_continue=bool(capability.get("safe_to_continue", True)),
            protocol_version=protocol_version,
            contract_revision=contract_revision,
            response=capability,
        )

    async def _preflight_legacy_extension_health_endpoint(
        self,
        extension: ComfyUIExtensionName,
        *,
        missing_endpoint: ComfyUIExtensionMissingEndpointMode,
    ) -> ComfyUIExtensionReleaseResult:
        endpoint = _EXTENSION_HEALTH_ENDPOINTS[extension]
        try:
            response = await self._request(
                "GET",
                endpoint,
                timeout=self.extension_preflight_timeout,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                message = (
                    f"ComfyUI extension health endpoint {endpoint} is missing. "
                    f"{_EXTENSION_PATCH_INSTRUCTIONS[extension]}"
                )
                if missing_endpoint == "optional":
                    logger.warning(message)
                    return ComfyUIExtensionReleaseResult(
                        extension=extension,
                        endpoint=endpoint,
                        released=False,
                        missing_endpoint=True,
                        message=message,
                    )
                raise RuntimeError(message) from exc
            raise

        payload = response.json()
        data = payload if isinstance(payload, dict) else {}
        if self._parse_protocol_version(data) != 2:
            message = (
                f"ComfyUI extension health endpoint {endpoint} does not expose "
                f"Pixelle release protocol v2. {_EXTENSION_PATCH_INSTRUCTIONS[extension]}"
            )
            raise RuntimeError(message)
        self._ensure_extension_contract_revision(extension, endpoint, data)
        return ComfyUIExtensionReleaseResult(
            extension=extension,
            endpoint=endpoint,
            released=False,
            safe_to_continue=self._is_extension_safe_to_continue(extension, data),
            protocol_version=self._parse_protocol_version(data),
            contract_revision=self._parse_contract_revision(data),
            response=data,
        )

    async def free_extension_models(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> tuple[ComfyUIExtensionReleaseResult, ...]:
        unified_discovery = await self._get_unified_extension_capabilities()
        if self._supports_unified_targeted_release(unified_discovery, extensions):
            try:
                return await self._free_extension_models_via_unified_endpoint(extensions)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise

        return await self._free_extension_models_via_legacy_endpoints(
            extensions,
            missing_endpoint=missing_endpoint,
        )

    def _supports_unified_targeted_release(
        self,
        discovery: tuple[int | None, dict[str, Any]] | None,
        extensions: tuple[ComfyUIExtensionName, ...],
    ) -> bool:
        if discovery is None:
            return False
        contract_revision, capabilities = discovery
        if (
            contract_revision is None
            or contract_revision < _UNIFIED_TARGETED_RELEASE_CONTRACT_REVISION
        ):
            return False
        for extension in extensions:
            capability = capabilities.get(extension)
            if not isinstance(capability, dict) or not bool(capability.get("ok")):
                return False
            if self._parse_protocol_version(capability) != 2:
                return False
            if capability.get("release_endpoint") != _UNIFIED_RELEASE_ENDPOINT:
                return False
            minimum_revision = _EXTENSION_MIN_CONTRACT_REVISIONS.get(extension)
            extension_revision = self._parse_contract_revision(capability)
            if minimum_revision is not None and (
                extension_revision is None or extension_revision < minimum_revision
            ):
                return False
        return True

    async def _free_extension_models_via_unified_endpoint(
        self,
        extensions: tuple[ComfyUIExtensionName, ...],
    ) -> tuple[ComfyUIExtensionReleaseResult, ...]:
        response = await self._request(
            "POST",
            _UNIFIED_RELEASE_ENDPOINT,
            json={"extensions": list(extensions)},
            timeout=self.release_request_timeout,
        )
        payload = response.json()
        data = payload if isinstance(payload, dict) else {}
        raw_results = data.get("results")
        if not isinstance(raw_results, dict):
            raise RuntimeError(
                "ComfyUI unified extension cleanup response is missing the results object"
            )

        results = []
        for extension in extensions:
            extension_data = raw_results.get(extension)
            if not isinstance(extension_data, dict):
                raise RuntimeError(
                    "ComfyUI unified extension cleanup response is missing "
                    f"the '{extension}' result"
                )
            results.append(
                self._extension_release_result_from_payload(
                    extension,
                    _UNIFIED_RELEASE_ENDPOINT,
                    extension_data,
                )
            )
        return tuple(results)

    async def _free_extension_models_via_legacy_endpoints(
        self,
        extensions: tuple[ComfyUIExtensionName, ...],
        *,
        missing_endpoint: ComfyUIExtensionMissingEndpointMode,
    ) -> tuple[ComfyUIExtensionReleaseResult, ...]:
        results: list[ComfyUIExtensionReleaseResult] = []
        for extension in extensions:
            endpoint = _EXTENSION_RELEASE_ENDPOINTS[extension]
            try:
                response = await self._request(
                    "POST",
                    endpoint,
                    json={},
                    timeout=self.release_request_timeout,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    message = (
                        f"ComfyUI extension cleanup endpoint {endpoint} is missing. "
                        f"{_EXTENSION_PATCH_INSTRUCTIONS[extension]}"
                    )
                    if missing_endpoint == "optional":
                        logger.warning(message)
                        results.append(
                            ComfyUIExtensionReleaseResult(
                                extension=extension,
                                endpoint=endpoint,
                                released=False,
                                missing_endpoint=True,
                                message=message,
                            )
                        )
                        continue
                    raise RuntimeError(message) from exc
                raise

            results.append(
                self._extension_release_result_from_payload(
                    extension=extension,
                    endpoint=endpoint,
                    data=response.json(),
                )
            )
        return tuple(results)

    def _extension_release_result_from_payload(
        self,
        extension: ComfyUIExtensionName,
        endpoint: str,
        data: Any,
    ) -> ComfyUIExtensionReleaseResult:
        payload = data if isinstance(data, dict) else {}
        return ComfyUIExtensionReleaseResult(
            extension=extension,
            endpoint=endpoint,
            released=bool(payload.get("released")),
            safe_to_continue=self._is_extension_safe_to_continue(extension, payload),
            protocol_version=self._parse_protocol_version(payload),
            contract_revision=self._parse_contract_revision(payload),
            response=payload,
        )

    async def free_extension_models_when_idle(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> ComfyUIMemoryReleaseResult:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI extension memory release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return ComfyUIMemoryReleaseResult(
                attempted=False,
                released=False,
                skipped=True,
                skipped_reason="queue_busy",
                queue_running=running,
                queue_pending=pending,
            )

        results = await self.free_extension_models(
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        safe_to_continue, reason = self._extension_release_confirmation(results)
        return ComfyUIMemoryReleaseResult(
            attempted=True,
            released=safe_to_continue,
            queue_running=running,
            queue_pending=pending,
            release_confirmed=safe_to_continue,
            release_confirmation_reason=reason,
            safe_to_continue=safe_to_continue,
            extensions=results,
        )

    def _extension_release_confirmation(
        self,
        results: tuple[ComfyUIExtensionReleaseResult, ...],
    ) -> tuple[bool, str]:
        if not results:
            return False, ""

        unconfirmed_reasons: list[str] = []
        for result in results:
            if result.missing_endpoint:
                unconfirmed_reasons.append("extension_endpoint_missing")
                continue
            response = result.response or {}
            if result.protocol_version != 2:
                unconfirmed_reasons.append("extension_legacy_contract_unconfirmed")
                continue
            minimum_revision = _EXTENSION_MIN_CONTRACT_REVISIONS.get(result.extension)
            if minimum_revision is not None:
                revision = result.contract_revision
                if revision is None or revision < minimum_revision:
                    unconfirmed_reasons.append("extension_contract_revision_unconfirmed")
                    continue
            if result.safe_to_continue:
                continue
            residual_objects = response.get("residual_objects")
            if isinstance(residual_objects, list) and residual_objects:
                unconfirmed_reasons.append("extension_residual_objects")
                continue
            errors = response.get("errors")
            if isinstance(errors, list) and errors:
                unconfirmed_reasons.append("extension_errors")
                continue
            unconfirmed_reasons.append("extension_not_safe_to_continue")

        if not unconfirmed_reasons:
            return True, "extension_safe_to_continue"
        return False, unconfirmed_reasons[0]

    def _parse_protocol_version(self, data: dict[str, Any]) -> int | None:
        value = data.get("protocol_version")
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_contract_revision(self, data: dict[str, Any]) -> int | None:
        value = data.get("contract_revision")
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _ensure_extension_contract_revision(
        self,
        extension: ComfyUIExtensionName,
        endpoint: str,
        data: dict[str, Any],
    ) -> None:
        minimum_revision = _EXTENSION_MIN_CONTRACT_REVISIONS.get(extension)
        if minimum_revision is None:
            return
        revision = self._parse_contract_revision(data)
        if revision is not None and revision >= minimum_revision:
            return
        raise RuntimeError(
            f"ComfyUI extension health endpoint {endpoint} exposes protocol v2 but "
            f"not the required contract revision >= {minimum_revision}. "
            f"{_EXTENSION_PATCH_INSTRUCTIONS[extension]}"
        )

    def _is_extension_safe_to_continue(
        self,
        extension: ComfyUIExtensionName,
        data: dict[str, Any],
    ) -> bool:
        if self._parse_protocol_version(data) != 2:
            return False
        minimum_revision = _EXTENSION_MIN_CONTRACT_REVISIONS.get(extension)
        if minimum_revision is not None:
            revision = self._parse_contract_revision(data)
            if revision is None or revision < minimum_revision:
                return False
        return bool(data.get("safe_to_continue"))

    async def free_memory_when_idle(
        self,
        *,
        intensity: ComfyUIReleaseIntensity = "high",
    ) -> ComfyUIMemoryReleaseResult:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI memory release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return ComfyUIMemoryReleaseResult(
                attempted=False,
                released=False,
                skipped=True,
                skipped_reason="queue_busy",
                intensity=intensity,
                queue_running=running,
                queue_pending=pending,
            )

        logger.info(f"Releasing ComfyUI memory after idle workflow completion ({intensity})")
        result = await self.free_memory(intensity)
        return replace(result, queue_running=running, queue_pending=pending)

    async def _get_queue(self) -> dict:
        response = await self._request("GET", "/queue")
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("ComfyUI /queue returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("ComfyUI /queue response must be a JSON object")
        self._queue_counts(data)
        return data

    async def _get_system_vram_snapshot(self) -> dict[str, Any] | None:
        try:
            response = await self._request(
                "GET",
                "/system_stats",
                timeout=self.system_stats_timeout,
            )
            data = response.json()
        except Exception as exc:
            logger.debug(f"Skipping ComfyUI system VRAM snapshot: {exc}")
            return None
        return self._extract_system_vram_snapshot(data)

    def _extract_system_vram_snapshot(self, data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        devices = data.get("devices")
        if not isinstance(devices, list):
            return None

        normalized_devices = []
        for device in devices:
            if not isinstance(device, dict):
                continue
            normalized = {
                key: device[key]
                for key in _SYSTEM_VRAM_DEVICE_KEYS
                if key in device
            }
            if normalized:
                normalized_devices.append(normalized)

        if not normalized_devices:
            return None
        return {"devices": normalized_devices}

    async def _wait_for_memory_release_confirmation(
        self,
        system_vram_before: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, bool, str]:
        if system_vram_before is None:
            system_vram_after = await self._get_system_vram_snapshot()
            reason = "system_stats_unavailable"
            return system_vram_after, False, reason

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.release_settle_timeout
        last_snapshot: dict[str, Any] | None = None
        last_reason = "release_not_observed"
        while True:
            snapshot = await self._get_system_vram_snapshot()
            if snapshot is None:
                reason = "system_stats_unavailable_after_free"
                return last_snapshot, False, reason
            last_snapshot = snapshot

            confirmed, reason = self._is_memory_release_confirmed(
                system_vram_before,
                snapshot,
            )
            last_reason = reason
            if confirmed:
                return snapshot, True, reason

            if loop.time() >= deadline:
                return snapshot, False, last_reason
            await asyncio.sleep(self.release_poll_interval)

    def _is_memory_release_confirmed(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> tuple[bool, str]:
        before_device = self._primary_vram_device(before)
        after_device = self._primary_vram_device(after)
        if before_device is None or after_device is None:
            return True, "vram_snapshot_missing_device"

        before_torch_total = self._to_int(before_device.get("torch_vram_total"))
        after_torch_total = self._to_int(after_device.get("torch_vram_total"))
        if (
            before_torch_total is not None
            and after_torch_total is not None
            and after_torch_total < before_torch_total
        ):
            return True, "torch_reserved_decreased"

        before_vram_free = self._to_int(before_device.get("vram_free"))
        after_vram_free = self._to_int(after_device.get("vram_free"))
        if (
            before_vram_free is not None
            and after_vram_free is not None
            and after_vram_free - before_vram_free >= self._release_vram_free_gain_threshold(after_device)
        ):
            return True, "device_vram_free_increased"

        before_torch_free = self._to_int(before_device.get("torch_vram_free"))
        after_torch_free = self._to_int(after_device.get("torch_vram_free"))
        if (
            before_torch_free is not None
            and after_torch_free is not None
            and before_torch_total is not None
            and after_torch_total is not None
            and before_torch_total > 0
            and after_torch_total > 0
            and after_torch_free / after_torch_total >= 0.8
            and after_torch_free > before_torch_free
        ):
            return True, "torch_reserved_mostly_free"

        return False, "release_not_observed"

    def _primary_vram_device(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        devices = snapshot.get("devices")
        if not isinstance(devices, list) or not devices:
            return None
        for device in devices:
            if isinstance(device, dict) and device.get("type") == "cuda":
                return device
        first = devices[0]
        return first if isinstance(first, dict) else None

    def _to_int(self, value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _release_vram_free_gain_threshold(self, device: dict[str, Any]) -> int:
        vram_total = self._to_int(device.get("vram_total"))
        if vram_total is None or vram_total <= 0:
            return _RELEASE_MIN_VRAM_FREE_GAIN_BYTES
        relative_threshold = max(1, int(vram_total * 0.05))
        return min(_RELEASE_MIN_VRAM_FREE_GAIN_BYTES, relative_threshold)

    async def _wait_until_idle(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.idle_wait_timeout
        while True:
            queue = await self._get_queue()
            running, pending = self._queue_counts(queue)
            if running == 0 and pending == 0:
                return
            if loop.time() >= deadline:
                raise TimeoutError(
                    "Timed out waiting for ComfyUI queue to become idle after "
                    f"{self.idle_wait_timeout:g}s (running={running}, pending={pending}). "
                    "Check the ComfyUI queue for a stuck prompt before retrying."
                )
            await asyncio.sleep(_IDLE_POLL_INTERVAL_SECONDS)

    def _queue_counts(self, queue: dict) -> tuple[int, int]:
        if not isinstance(queue, dict):
            raise RuntimeError("ComfyUI /queue response must be a JSON object")
        missing = [
            key
            for key in ("queue_running", "queue_pending")
            if key not in queue
        ]
        if missing:
            raise RuntimeError(
                "ComfyUI /queue response is missing required field(s): "
                + ", ".join(missing)
            )
        running = queue["queue_running"]
        pending = queue["queue_pending"]
        if not isinstance(running, list) or not isinstance(pending, list):
            raise RuntimeError(
                "ComfyUI /queue fields queue_running and queue_pending must be arrays"
            )
        return len(running), len(pending)

    async def _post(self, path: str, payload: dict) -> None:
        await self._request("POST", path, json=payload)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        requested_timeout = kwargs.get("timeout", self.timeout)
        timeout = httpx.Timeout(self.timeout, connect=min(self.timeout, 2.0))
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            transport=self.transport,
        ) as client:
            try:
                response = await client.request(method, path, **kwargs)
            except httpx.TimeoutException as exc:
                timeout_display = (
                    f"{requested_timeout:g}"
                    if isinstance(requested_timeout, (int, float))
                    else str(requested_timeout)
                )
                raise TimeoutError(
                    f"ComfyUI {method} {self.base_url}{path} timed out "
                    f"after {timeout_display}s"
                ) from exc
            except httpx.RequestError as exc:
                detail = str(exc).strip() or repr(exc) or type(exc).__name__
                raise ConnectionError(
                    f"ComfyUI {method} {self.base_url}{path} request failed: {detail}"
                ) from exc
            response.raise_for_status()
            return response
