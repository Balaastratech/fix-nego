import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GlobalLimiter:
    """Named semaphore registry for bounded API concurrency."""

    _semaphores: dict[str, asyncio.Semaphore] = {}

    @classmethod
    def get(cls, name: str, limit: int) -> asyncio.Semaphore:
        semaphore = cls._semaphores.get(name)
        if semaphore is None:
            semaphore = asyncio.Semaphore(max(1, limit))
            cls._semaphores[name] = semaphore
        return semaphore


async def run_with_retries(
    operation_name: str,
    func: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    base_backoff_ms: int,
    max_backoff_ms: int,
    is_retryable: Callable[[Exception], bool],
    on_retry: Callable[[int, Exception], Awaitable[None] | None] | None = None,
) -> T:
    attempt = 0
    while True:
        try:
            return await func()
        except Exception as exc:
            attempt += 1
            if attempt > max_retries or not is_retryable(exc):
                raise

            if on_retry is not None:
                maybe_coro = on_retry(attempt, exc)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro

            cap_ms = min(max_backoff_ms, base_backoff_ms * (2 ** (attempt - 1)))
            sleep_ms = random.uniform(0, cap_ms)
            logger.warning(
                "%s retry %s/%s after %sms: %s",
                operation_name,
                attempt,
                max_retries,
                int(sleep_ms),
                exc,
            )
            await asyncio.sleep(sleep_ms / 1000.0)
