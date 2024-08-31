__version__ = "0.1.0"

import functools
import threading
from collections import (
    Counter,
)
from contextlib import (
    contextmanager,
)
from contextvars import (
    ContextVar,
    Token,
)
from typing import (
    Callable,
    Generator,
    Iterable,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    Union,
)

import redis
import redis.asyncio
import redis.commands.core
from redis.typing import (
    ExpiryT,
)

__all__ = (
    "multi_lock",
    "__version__",
)

acquire_lua = """
local resp = {}
for i=1, #KEYS do
    if redis.pcall('SET', KEYS[i], "", "NX", unpack(ARGV) )["err"] == nil then
        resp[i] = 1
    else
        resp[i] = 0
    end
end
return resp
"""


_acquisitions: ContextVar[Set[str]] = ContextVar("_acquisitions", default=set())


def _make_script(
    names: Iterable[str],
    client: Union[redis.Redis, redis.asyncio.Redis],
    px: Optional[ExpiryT] = None,
) -> Tuple[Callable[[], List[int]], Set[str],]:
    script = client.register_script(acquire_lua)

    # Only acquire what is not already acquired
    names_to_acquire = set(names) - _acquisitions.get()

    script = functools.partial(script, keys=tuple(names_to_acquire))
    if px is not None:
        script = functools.partial(script, args=("px", px))

    return script, names_to_acquire


def _try_acquire(
    names: Iterable[str],
    px: Optional[ExpiryT] = None,
    client: Optional[redis.Redis] = None,
) -> Tuple[Set[str], Set[str], Token[str]]:
    if client is None:
        client = redis.Redis()
    script, names_to_acquire = _make_script(names, px=px, client=client)
    responses = script()
    return process_acquire_responses(names_to_acquire, responses)


def _release(
    names: Set[str],
    token: Token[str],
    client: redis.Redis,
) -> None:
    if names:
        client.delete(*names)
    _acquisitions.reset(token)


@contextmanager
def multi_lock(
    names: Iterable[str],
    px: Optional[ExpiryT] = None,
    client: Optional[redis.Redis] = None,
) -> Generator[Set[str], None, None]:
    successes, failures, token = _try_acquire(names, px=px, client=client)
    try:
        yield failures
    finally:
        _release(successes, token, client)


def process_acquire_responses(
    names_to_acquire: Set[str],
    responses: List[Union[Literal[0], Literal[1]]],
) -> Tuple[Set[str], Set[str], Token[str]]:
    failures = set()
    for i, acquired in enumerate(responses):
        if not acquired:
            failures.add(names_to_acquire[i])
    successes = names_to_acquire - failures
    # Update acquisitions context
    token = _acquisitions.set(_acquisitions.get() | successes)
    return successes, failures, token
