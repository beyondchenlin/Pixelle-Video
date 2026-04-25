"""Generation submit locks and execution leases."""

from __future__ import annotations

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
