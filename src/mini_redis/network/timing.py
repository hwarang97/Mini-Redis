"""Transport-only helpers for timing metadata."""

from __future__ import annotations

from typing import Any

TIMING_MARKER = "__mini_redis_timing__"


def wrap_timed_response(value: Any, server_time_us: int) -> list[Any]:
    """Attach server execution timing without changing command-layer return values."""

    return [TIMING_MARKER, server_time_us, value]


def unwrap_timed_response(value: Any) -> tuple[Any, float | None]:
    """Return the original payload and server time in milliseconds when present."""

    if (
        isinstance(value, list)
        and len(value) == 3
        and value[0] == TIMING_MARKER
        and isinstance(value[1], int)
    ):
        return value[2], value[1] / 1000
    return value, None
