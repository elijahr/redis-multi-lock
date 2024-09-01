import time
from test.test import (
    State,
    States,
)
from typing import (
    AsyncGenerator,
    List,
)

import pytest
import pytest_asyncio
import redis
import redis.asyncio

from redis_multi_lock import (
    _acquisitions,
)
from redis_multi_lock.asyncio import (
    multi_lock,
)


@pytest_asyncio.fixture(scope="function", name="client")
async def fixture_client() -> AsyncGenerator[redis.asyncio.Redis, None]:
    c = redis.asyncio.Redis(db=10, decode_responses=True)
    await c.flushall()
    try:
        yield c
    finally:
        await c.aclose()


async def get_state(client: redis.asyncio.Redis) -> States:
    keys: List[str] = await client.keys()
    state = {}
    for key in keys:
        item: State = {
            "value": await client.get(key),
            "pexpiretime": await client.pexpiretime(key),  # type: ignore[misc]
        }
        state[key] = item
    return state


@pytest.mark.asyncio(loop_scope="function")
async def test__multi_lock(
    client: redis.asyncio.Redis,
) -> None:
    async with multi_lock(("a", "b", "c"), client=client) as failures:
        assert _acquisitions.get() == {"a", "b", "c"}
        assert failures == set()
        assert await get_state(client) == {
            "a": {
                "pexpiretime": -1,
                "value": "",
            },
            "b": {
                "pexpiretime": -1,
                "value": "",
            },
            "c": {
                "pexpiretime": -1,
                "value": "",
            },
        }
    assert _acquisitions.get() == set()
    assert await get_state(client) == {}


@pytest.mark.asyncio
async def test__multi_lock__px(
    client: redis.asyncio.Redis,
) -> None:
    async with multi_lock(("a", "b", "c"), px=100000, client=client) as failures:
        now = round(time.time() * 1000)
        assert _acquisitions.get() == {"a", "b", "c"}
        assert failures == set()
        assert await get_state(client) == {
            "a": {
                "pexpiretime": pytest.approx(now + 100000),
                "value": "",
            },
            "b": {
                "pexpiretime": pytest.approx(now + 100000),
                "value": "",
            },
            "c": {
                "pexpiretime": pytest.approx(now + 100000),
                "value": "",
            },
        }
    assert _acquisitions.get() == set()
    assert await get_state(client) == {}


@pytest.mark.asyncio(loop_scope="function")
async def test__multi_lock__nested(
    client: redis.asyncio.Redis,
) -> None:
    async with multi_lock(("a", "b", "c"), client=client):
        async with multi_lock(("b", "c", "d"), client=client) as failures:
            async with multi_lock(
                ("c", "d", "e", "f"),
                client=client,
            ) as failures:
                assert _acquisitions.get() == {"a", "b", "c", "d", "e", "f"}
                assert failures == set()
                assert await get_state(client) == {
                    "a": {
                        "pexpiretime": -1,
                        "value": "",
                    },
                    "b": {
                        "pexpiretime": -1,
                        "value": "",
                    },
                    "c": {
                        "pexpiretime": -1,
                        "value": "",
                    },
                    "d": {
                        "pexpiretime": -1,
                        "value": "",
                    },
                    "e": {
                        "pexpiretime": -1,
                        "value": "",
                    },
                    "f": {
                        "pexpiretime": -1,
                        "value": "",
                    },
                }
            assert _acquisitions.get() == {"a", "b", "c", "d"}
            assert failures == set()
            assert await get_state(client) == {
                "a": {
                    "pexpiretime": -1,
                    "value": "",
                },
                "b": {
                    "pexpiretime": -1,
                    "value": "",
                },
                "c": {
                    "pexpiretime": -1,
                    "value": "",
                },
                "d": {
                    "pexpiretime": -1,
                    "value": "",
                },
            }
        assert _acquisitions.get() == {"a", "b", "c"}
        assert await get_state(client) == {
            "a": {
                "pexpiretime": -1,
                "value": "",
            },
            "b": {
                "pexpiretime": -1,
                "value": "",
            },
            "c": {
                "pexpiretime": -1,
                "value": "",
            },
        }
    assert _acquisitions.get() == set()
    assert await get_state(client) == {}


@pytest.mark.asyncio(loop_scope="function")
async def test__multi_lock__failure(
    client: redis.asyncio.Redis,
) -> None:
    now = round(time.time() * 1000)
    await client.set("a", "", px=100000)
    await client.set("b", "", px=100000)
    async with multi_lock(("a", "b", "c", "d"), client=client) as failures:
        assert failures == {"a", "b"}
        assert _acquisitions.get() == {"c", "d"}
        assert await get_state(client) == {
            "a": {
                "pexpiretime": pytest.approx(now + 100000),
                "value": "",
            },
            "b": {
                "pexpiretime": pytest.approx(now + 100000),
                "value": "",
            },
            "c": {
                "pexpiretime": -1,
                "value": "",
            },
            "d": {
                "pexpiretime": -1,
                "value": "",
            },
        }
    assert _acquisitions.get() == set()
    assert await get_state(client) == {
        "a": {
            "pexpiretime": pytest.approx(now + 100000),
            "value": "",
        },
        "b": {
            "pexpiretime": pytest.approx(now + 100000),
            "value": "",
        },
    }
