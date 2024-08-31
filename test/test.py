import asyncio
from typing import (
    Dict,
)

import pytest
import pytest_asyncio
import redis
import redis.asyncio
from redis import (
    Redis,
)

from redis_multi_lock import (
    _acquisitions,
    multi_lock,
)


@pytest.fixture
def client():
    c = redis.Redis(db=10)
    c.flushall()
    return c


@pytest.fixture
def names():
    return ("a", "b", "c")


def redis_state(client: redis.Redis) -> Dict[str, bytes]:
    keys = client.keys()
    pipeline = client.pipeline()
    for key in keys:
        pipeline.get(key)
    state = {}
    for i, value in enumerate(pipeline.execute()):
        key = keys[i].decode()
        state[key] = value
    return state


def test__multi_lock(client, names):
    with multi_lock(names, client=client) as failures:
        assert _acquisitions.get() == {"a", "b", "c"}
        assert failures == set()
        assert redis_state(client) == {
            "a": b"",
            "b": b"",
            "c": b"",
        }
    assert _acquisitions.get() == set()
    assert redis_state(client) == {}


def test__multi_lock__nested(client, names):
    with multi_lock(names, client=client):
        with multi_lock(names, client=client) as failures:
            assert _acquisitions.get() == {"a", "b", "c"}
            assert failures == set()
            assert redis_state(client) == {
                "a": b"",
                "b": b"",
                "c": b"",
            }
        assert _acquisitions.get() == {"a", "b", "c"}
        assert redis_state(client) == {
            "a": b"",
            "b": b"",
            "c": b"",
        }
    assert _acquisitions.get() == set()
    assert redis_state(client) == {}
