import pytest

from api.tasks.lease import LostLeaseError, RedisGenerationLease


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_redis_submit_lock_is_owner_scoped():
    redis = FakeRedis()
    lease = RedisGenerationLease(redis=redis)

    assert await lease.acquire_submit_lock("fp-1", "owner-1") is True
    assert await lease.acquire_submit_lock("fp-1", "owner-2") is False
    await lease.release_submit_lock("fp-1", "owner-2")
    assert await lease.acquire_submit_lock("fp-1", "owner-3") is False
    await lease.release_submit_lock("fp-1", "owner-1")
    assert await lease.acquire_submit_lock("fp-1", "owner-3") is True


@pytest.mark.asyncio
async def test_redis_heartbeat_rejects_stale_token():
    redis = FakeRedis()
    lease = RedisGenerationLease(redis=redis)
    await lease.create_task_lease("task-1", "worker-1", "token-1")

    with pytest.raises(LostLeaseError):
        await lease.heartbeat("task-1", "worker-1", "token-old")


@pytest.mark.asyncio
async def test_redis_task_lease_release_is_owner_and_token_scoped():
    redis = FakeRedis()
    lease = RedisGenerationLease(redis=redis)
    await lease.create_task_lease("task-1", "worker-1", "token-1")

    await lease.release_task_lease("task-1", "worker-2", "token-1")
    assert await redis.get("pixelle:generation:task:task-1:lease") is not None

    await lease.release_task_lease("task-1", "worker-1", "token-1")
    assert await redis.get("pixelle:generation:task:task-1:lease") is None
