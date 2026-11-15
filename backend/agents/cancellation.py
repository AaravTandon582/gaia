"""Request-local cancellation, also propagated into asyncio worker threads."""

import asyncio
from contextvars import ContextVar
from threading import Event


scan_cancel_event: ContextVar[Event | None] = ContextVar("scan_cancel_event", default=None)


def check_cancelled() -> None:
    event = scan_cancel_event.get()
    if event is not None and event.is_set():
        raise asyncio.CancelledError
