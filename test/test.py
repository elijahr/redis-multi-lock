import time
from typing import (
    Dict,
    List,
    Literal,
    Optional,
    TypedDict,
)

import pytest
import redis

from redis_multi_lock import (
    _acquisitions,
    multi_lock,
)


class State(TypedDict):
    pexpiretime: int
    value: Optional[Literal[""]]


States = Dict[str, State]


@pytest.fixture(name="client")
def fixture_client() -> redis.Redis:
    c = redis.Redis(db=10, decode_responses=True)
    c.flushall()
    return c


def get_state(client: redis.Redis) -> States:
    keys: List[str] = client.keys()  # type: ignore[assignment]
    state = {}
    for key in keys:
        item: State = {
            "value": client.get(key),  # type: ignore[typeddict-item]
            "pexpiretime": client.pexpiretime(key),
        }
        state[key] = item
    return state


def test__multi_lock(
    client: redis.Redis,
) -> None:
    with multi_lock(("a", "b", "c"), client=client) as failures:
        assert _acquisitions.get() == {"a", "b", "c"}
        assert failures == set()
        assert get_state(client) == {
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
    assert get_state(client) == {}


def test__multi_lock__px(
    client: redis.Redis,
) -> None:
    with multi_lock(("a", "b", "c"), px=100000, client=client) as failures:
        now = round(time.time() * 1000)
        assert _acquisitions.get() == {"a", "b", "c"}
        assert failures == set()
        assert get_state(client) == {
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
    assert get_state(client) == {}


def test__multi_lock__nested(
    client: redis.Redis,
) -> None:
    with multi_lock(("a", "b", "c"), client=client):
        with multi_lock(("b", "c", "d"), client=client) as failures:
            with multi_lock(
                (
                    "c",
                    "d",
                    "e",
                    "f",
                ),
                client=client,
            ) as failures:
                assert _acquisitions.get() == {"a", "b", "c", "d", "e", "f"}
                assert failures == set()
                assert get_state(client) == {
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
            assert get_state(client) == {
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
        assert get_state(client) == {
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
    assert get_state(client) == {}


def test__multi_lock__failure(
    client: redis.Redis,
) -> None:
    now = round(time.time() * 1000)
    client.set("a", "", px=100000)
    client.set("b", "", px=100000)
    with multi_lock(("a", "b", "c", "d"), client=client) as failures:
        assert failures == {"a", "b"}
        assert _acquisitions.get() == {"c", "d"}
        assert get_state(client) == {
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
    assert get_state(client) == {
        "a": {
            "pexpiretime": pytest.approx(now + 100000),
            "value": "",
        },
        "b": {
            "pexpiretime": pytest.approx(now + 100000),
            "value": "",
        },
    }
