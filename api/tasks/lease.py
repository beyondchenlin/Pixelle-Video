"""Generation submit locks and execution leases."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from typing import Protocol

from api.tasks.models import ExecutionLease, utc_now


class LostLeaseError(RuntimeError):
    """Raised when an owner no longer holds a matching execution lease."""


class GenerationLease(Protocol):
    async def acquire_submit_lock(self, fingerprint: str, owner_id: str) -> bool:
        raise NotImplementedError

    async def release_submit_lock(self, fingerprint: str, owner_id: str) -> None:
        raise NotImplementedError

    async def create_task_lease(
        self,
        task_id: str,
        owner_id: str,
        lease_token: str,
    ) -> ExecutionLease:
        raise NotImplementedError

    async def heartbeat(self, task_id: str, owner_id: str, lease_token: str) -> ExecutionLease:
        raise NotImplementedError

    async def release_task_lease(self, task_id: str, owner_id: str, lease_token: str) -> None:
        raise NotImplementedError

    async def has_task_lease(self, task_id: str, owner_id: str, lease_token: str) -> bool:
        raise NotImplementedError

    def new_token(self) -> str:
        raise NotImplementedError


class InMemoryGenerationLease:
    """Process-local lease implementation for tests and local memory backend."""

    def __init__(self, lease_ttl_seconds: int = 120) -> None:
        self.lease_ttl_seconds = lease_ttl_seconds
        self.submit_locks: dict[str, str] = {}
        self.task_leases: dict[str, tuple[str, str]] = {}

    async def acquire_submit_lock(self, fingerprint: str, owner_id: str) -> bool:
        current_owner = self.submit_locks.get(fingerprint)
        if current_owner is not None:
            return current_owner == owner_id
        self.submit_locks[fingerprint] = owner_id
        return True

    async def release_submit_lock(self, fingerprint: str, owner_id: str) -> None:
        if self.submit_locks.get(fingerprint) == owner_id:
            self.submit_locks.pop(fingerprint, None)

    async def create_task_lease(
        self,
        task_id: str,
        owner_id: str,
        lease_token: str,
    ) -> ExecutionLease:
        current = self.task_leases.get(task_id)
        if current is not None and current != (owner_id, lease_token):
            raise LostLeaseError(task_id)
        self.task_leases[task_id] = (owner_id, lease_token)
        return self._build_execution_lease(task_id, owner_id, lease_token)

    async def heartbeat(self, task_id: str, owner_id: str, lease_token: str) -> ExecutionLease:
        current = self.task_leases.get(task_id)
        if current != (owner_id, lease_token):
            raise LostLeaseError(task_id)
        return self._build_execution_lease(task_id, owner_id, lease_token)

    async def release_task_lease(self, task_id: str, owner_id: str, lease_token: str) -> None:
        if self.task_leases.get(task_id) == (owner_id, lease_token):
            self.task_leases.pop(task_id, None)

    async def has_task_lease(self, task_id: str, owner_id: str, lease_token: str) -> bool:
        return self.task_leases.get(task_id) == (owner_id, lease_token)

    def new_token(self) -> str:
        return secrets.token_urlsafe(24)

    def _build_execution_lease(
        self,
        task_id: str,
        owner_id: str,
        lease_token: str,
    ) -> ExecutionLease:
        return ExecutionLease(
            task_id=task_id,
            owner_id=owner_id,
            lease_token=lease_token,
            lease_expires_at=utc_now() + timedelta(seconds=self.lease_ttl_seconds),
        )


class RedisGenerationLease:
    """Redis-backed generation lock and task lease implementation."""

    _COMPARE_DELETE_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    end
    return 0
    """
    _COMPARE_REFRESH_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        redis.call("SET", KEYS[1], ARGV[1], "EX", ARGV[2])
        return 1
    end
    return 0
    """

    def __init__(
        self,
        *,
        redis,
        namespace: str = "pixelle:generation",
        lease_ttl_seconds: int = 120,
        submit_lock_ttl_seconds: int = 30,
    ) -> None:
        self.redis = redis
        self.namespace = namespace.rstrip(":")
        self.lease_ttl_seconds = lease_ttl_seconds
        self.submit_lock_ttl_seconds = submit_lock_ttl_seconds

    async def acquire_submit_lock(self, fingerprint: str, owner_id: str) -> bool:
        key = self._submit_lock_key(fingerprint)
        acquired = await self.redis.set(
            key,
            owner_id,
            nx=True,
            ex=self.submit_lock_ttl_seconds,
        )
        return bool(acquired)

    async def release_submit_lock(self, fingerprint: str, owner_id: str) -> None:
        key = self._submit_lock_key(fingerprint)
        await self._compare_delete(key, owner_id)

    async def create_task_lease(
        self,
        task_id: str,
        owner_id: str,
        lease_token: str,
    ) -> ExecutionLease:
        key = self._task_lease_key(task_id)
        encoded = self._encode_lease(owner_id, lease_token)
        acquired = await self.redis.set(
            key,
            encoded,
            nx=True,
            ex=self.lease_ttl_seconds,
        )
        if acquired:
            return self._build_execution_lease(task_id, owner_id, lease_token)

        current = await self.redis.get(key)
        if current is not None and self._decode_lease(current) != (owner_id, lease_token):
            raise LostLeaseError(task_id)

        await self.redis.set(
            key,
            encoded,
            ex=self.lease_ttl_seconds,
        )
        return self._build_execution_lease(task_id, owner_id, lease_token)

    async def heartbeat(self, task_id: str, owner_id: str, lease_token: str) -> ExecutionLease:
        key = self._task_lease_key(task_id)
        encoded = self._encode_lease(owner_id, lease_token)
        refreshed = await self._compare_refresh(key, encoded, self.lease_ttl_seconds)
        if not refreshed:
            raise LostLeaseError(task_id)
        return self._build_execution_lease(task_id, owner_id, lease_token)

    async def release_task_lease(self, task_id: str, owner_id: str, lease_token: str) -> None:
        key = self._task_lease_key(task_id)
        await self._compare_delete(key, self._encode_lease(owner_id, lease_token))

    async def has_task_lease(self, task_id: str, owner_id: str, lease_token: str) -> bool:
        key = self._task_lease_key(task_id)
        current = await self.redis.get(key)
        return self._decode(current) == self._encode_lease(owner_id, lease_token)

    def new_token(self) -> str:
        return secrets.token_urlsafe(24)

    def _submit_lock_key(self, fingerprint: str) -> str:
        return f"{self.namespace}:fingerprint:{fingerprint}:submit_lock"

    def _task_lease_key(self, task_id: str) -> str:
        return f"{self.namespace}:task:{task_id}:lease"

    def _build_execution_lease(
        self,
        task_id: str,
        owner_id: str,
        lease_token: str,
    ) -> ExecutionLease:
        return ExecutionLease(
            task_id=task_id,
            owner_id=owner_id,
            lease_token=lease_token,
            lease_expires_at=utc_now() + timedelta(seconds=self.lease_ttl_seconds),
        )

    @staticmethod
    def _encode_lease(owner_id: str, lease_token: str) -> str:
        return json.dumps(
            {"owner_id": owner_id, "lease_token": lease_token},
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def _decode_lease(cls, value) -> tuple[str, str]:
        data = json.loads(cls._decode(value))
        return data["owner_id"], data["lease_token"]

    @staticmethod
    def _decode(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    async def _compare_delete(self, key: str, expected_value: str) -> bool:
        eval_func = getattr(self.redis, "eval", None)
        if callable(eval_func):
            deleted = await eval_func(self._COMPARE_DELETE_SCRIPT, 1, key, expected_value)
            return bool(deleted)

        current = await self.redis.get(key)
        if self._decode(current) == expected_value:
            await self.redis.delete(key)
            return True
        return False

    async def _compare_refresh(self, key: str, expected_value: str, ttl_seconds: int) -> bool:
        eval_func = getattr(self.redis, "eval", None)
        if callable(eval_func):
            refreshed = await eval_func(
                self._COMPARE_REFRESH_SCRIPT,
                1,
                key,
                expected_value,
                str(ttl_seconds),
            )
            return bool(refreshed)

        current = await self.redis.get(key)
        if self._decode(current) == expected_value:
            await self.redis.set(key, expected_value, ex=ttl_seconds)
            return True
        return False


def create_redis_lease(
    redis_url: str,
    *,
    lease_ttl_seconds: int,
    submit_lock_ttl_seconds: int,
) -> RedisGenerationLease:
    import redis.asyncio as redis

    return RedisGenerationLease(
        redis=redis.from_url(redis_url),
        lease_ttl_seconds=lease_ttl_seconds,
        submit_lock_ttl_seconds=submit_lock_ttl_seconds,
    )
