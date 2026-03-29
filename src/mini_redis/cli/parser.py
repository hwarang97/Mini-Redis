"""CLI parsing for user-entered commands."""

from __future__ import annotations

import shlex
from typing import TypedDict

from mini_redis.types import Command


class LocalCLICommand(TypedDict):
    name: str
    args: list[str]


def parse_cli_meta_command(raw: str) -> LocalCLICommand | None:
    text = raw.strip()
    if not text.startswith("."):
        return None

    parts = _split_cli_input(text)
    if not parts:
        return None

    return {"name": parts[0].lower(), "args": parts[1:]}


def parse_cli_command(raw: str) -> Command | None:
    text = raw.strip()
    if not text or text.startswith("#"):
        return None

    parts = _split_cli_input(text)
    if not parts:
        return None

    return {"name": parts[0].upper(), "args": parts[1:]}


def _split_cli_input(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError as exc:
        raise ValueError(f"invalid CLI input: {exc}") from exc
