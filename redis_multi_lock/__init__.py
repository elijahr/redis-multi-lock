__version__ = "0.1.0"

import datetime
from contextlib import (
    contextmanager,
)
from contextvars import (
    ContextVar,
    Token,
)
from typing import (
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
    local r = redis.pcall('SET', KEYS[i], "", "NX", unpack(ARGV))
    if r and r["err"] == nil then
        resp[i] = true
    else
        resp[i] = false
    end
end
return resp
"""

_acquisitions: ContextVar[Set[str]] = ContextVar("_acquisitions", default=set())


def _try_acquire(
    client: redis.Redis,
    names: Iterable[str],
    px: Optional[int] = None,
) -> Tuple[Set[str], Set[str], Token[Set[str]]]:
    script = client.register_script(acquire_lua)
    # Only acquire what is not already acquired
    names_to_acquire = list(set(names) - _acquisitions.get())
    args: List[Union[str, int]] = []
    if px is not None:
        args += ["px", int(px)]
    responses = script(keys=names_to_acquire, args=args)
    return _process_response(names_to_acquire, responses)


def _release(
    names: Set[str],
    token: Token[Set[str]],
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
    if isinstance(px, datetime.timedelta):
        px = round(px.total_seconds() * 1000)
    elif isinstance(px, float):
        px = round(px)

    if client is None:
        client = redis.Redis()

    successes, failures, token = _try_acquire(client, names, px)
    try:
        yield failures
    finally:
        _release(successes, token, client)


def _process_response(
    names_to_acquire: List[str],
    responses: List[Union[Literal[0], Literal[1]]],
) -> Tuple[Set[str], Set[str], Token[Set[str]]]:
    failures = set()
    for i, acquired in enumerate(responses):
        if not acquired:
            failures.add(names_to_acquire[i])
    successes = set(names_to_acquire) - failures
    # Update acquisitions context
    token = _acquisitions.set(_acquisitions.get() | successes)
    return successes, failures, token
