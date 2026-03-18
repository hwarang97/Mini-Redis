"""Invalidation manager."""

from __future__ import annotations


class InvalidationManager:
    """Track invalidation events for future cache coordination."""

    def __init__(self) -> None:
        self._events: list[str] = []

    def notify(self, key: str) -> None:
        self._events.append(key)

    @property
    def events(self) -> list[str]:
        return list(self._events)
