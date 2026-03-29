"""Transport-only helpers for timing metadata."""

from __future__ import annotations

from typing import Any

from mini_redis.types import Command

TIMING_MARKER = "__mini_redis_timing__"
TIMED_COMMAND = "__MINI_REDIS_TIMED__"


def wrap_timed_command(command: Command) -> Command:
    """Wrap a command so timing-aware clients can opt into timed responses."""

    return {"name": TIMED_COMMAND, "args": [command["name"], *command["args"]]}


def wrap_timed_response(value: Any, server_time_us: int) -> list[Any]:
    """Attach server execution timing without changing command-layer return values."""

    return [TIMING_MARKER, server_time_us, value]


def unwrap_timed_command(command: Command) -> tuple[Command, bool]:
    """Return the original command and whether timing was explicitly requested."""

    if command["name"] != TIMED_COMMAND:
        return command, False
    if not command["args"]:
        return {"name": "__INVALID_TIMED__", "args": []}, True
    return {"name": command["args"][0], "args": command["args"][1:]}, True


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
