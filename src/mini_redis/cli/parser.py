"""CLI parsing for user-entered commands."""

from __future__ import annotations

import shlex

from mini_redis.types import Command


def parse_cli_command(raw: str) -> Command | None:
    text = raw.strip()
    if not text:
        return None

    parts = shlex.split(text)
    if not parts:
        return None

    return {"name": parts[0].upper(), "args": parts[1:]}
