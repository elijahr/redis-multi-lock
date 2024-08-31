import asyncio
from typing import (
    Dict,
)

import pytest
import pytest_asyncio
import redis
import redis.asyncio

from redis_multi_lock import (
    _acquisitions,
)
from redis_multi_lock.asyncio import (
    multi_lock_async,
)


@pytest_asyncio.fixture
async def client():
    c = redis.asyncio.Redis(db=10)
    await c.flushall()
    try:
        yield c
    except:
        await c.close()


@pytest.fixture
def names():
    return ("a", "b", "c")


async def redis_state(client: redis.asyncio.Redis) -> Dict[str, bytes]:
    keys = await client.keys()
    pipeline = client.pipeline()
    for key in keys:
        pipeline.get(key)
    state = {}
    for i, value in enumerate(await pipeline.execute()):
        key = keys[i].decode()
        state[key] = value
    return state


@pytest.mark.asyncio
async def test__multi_lock_async(client, names):
    async with multi_lock_async(names, client=client) as failures:
        assert _acquisitions.get() == {"a", "b", "c"}
        assert failures == set()
        assert await redis_state(client) == {
            "a": b"",
            "b": b"",
            "c": b"",
        }
    assert _acquisitions.get() == set()
    assert await redis_state(client) == {}


@pytest.mark.asyncio
async def test__multi_lock_async__nested(client, names):
    async with multi_lock_async(names, client=client):
        async with multi_lock_async(names, client=client) as failures:
            assert _acquisitions.get() == {"a", "b", "c"}
            assert failures == set()
            assert await redis_state(client) == {
                "a": b"",
                "b": b"",
                "c": b"",
            }
        assert _acquisitions.get() == {"a", "b", "c"}
        assert await redis_state(client) == {
            "a": b"",
            "b": b"",
            "c": b"",
        }
    assert _acquisitions.get() == set()
    assert await redis_state(client) == {}
