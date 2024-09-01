import datetime
from contextlib import (
    asynccontextmanager,
)
from contextvars import (
    Token,
)
from typing import (
    AsyncGenerator,
    Iterable,
    List,
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
    _process_response,
    acquire_lua,
)

__all__ = ("multi_lock",)


async def _try_acquire(
    client: redis.asyncio.Redis,
    names: Iterable[str],
    px: Optional[int] = None,
) -> Tuple[Set[str], Set[str], Token[Set[str]]]:
    script = client.register_script(acquire_lua)
    # Only acquire what is not already acquired
    names_to_acquire = list(set(names) - _acquisitions.get())
    args: List[Union[str, int]] = []
    if px is not None:
        args += ["px", px]
    responses = await script(keys=names_to_acquire, args=args)
    return _process_response(names_to_acquire, responses)


async def _release(
    names: Set[str],
    token: Token[Set[str]],
    client: redis.asyncio.Redis,
) -> None:
    if names:
        await client.delete(*names)
    _acquisitions.reset(token)


@asynccontextmanager
async def multi_lock(
    names: Iterable[str],
    px: Optional[ExpiryT] = None,
    client: Optional[redis.asyncio.Redis] = None,
) -> AsyncGenerator[Set[str], None]:
    if isinstance(px, datetime.timedelta):
        px = round(px.total_seconds() * 1000)
    elif isinstance(px, float):
        px = round(px)

    if client is None:
        client = redis.asyncio.Redis()

    successes, failures, token = await _try_acquire(client, names, px)
    try:
        yield failures
    finally:
        await _release(successes, token, client)
