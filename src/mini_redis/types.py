"""Shared type aliases."""

from __future__ import annotations

from typing import TypedDict


class Command(TypedDict):
    name: str
    args: list[str]
