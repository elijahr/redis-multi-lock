import functools
import threading
from collections import (
    Counter,
)
from contextlib import (
    asynccontextmanager,
    contextmanager,
)
from contextvars import (
    ContextVar,
    Token,
)
from typing import (
    AsyncGenerator,
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

from redis_multi_lock import (
    _acquisitions,
    _make_script,
    process_acquire_responses,
)

__all__ = ("multi_lock_async",)


async def _try_acquire_async(
    names: Iterable[str],
    px: Optional[ExpiryT] = None,
    client: Optional[redis.asyncio.Redis] = None,
) -> Tuple[Set[str], Set[str], Token[str]]:
    if client is None:
        client = redis.asyncio.Redis()
    script, names_to_acquire = _make_script(names, px=px, client=client)
    responses = await script()
    return process_acquire_responses(names_to_acquire, responses)


async def _release_async(
    names: Set[str],
    token: Token[str],
    client: redis.asyncio.Redis,
) -> None:
    if names:
        await client.delete(*names)
    _acquisitions.reset(token)


@asynccontextmanager
async def multi_lock_async(
    names: Iterable[str],
    px: Optional[ExpiryT] = None,
    client: Optional[redis.asyncio.Redis] = None,
) -> AsyncGenerator[Set[str], None]:
    successes, failures, token = await _try_acquire_async(names, px=px, client=client)
    try:
        yield failures
    finally:
        await _release_async(successes, token, client)
