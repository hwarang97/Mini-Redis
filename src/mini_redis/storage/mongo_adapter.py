"""MongoDB integration seam."""

from __future__ import annotations


class MongoAdapter:
    """Optional external database sync point."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.synced: list[tuple[str, str]] = []

    def maybe_sync(self, key: str, value: str) -> None:
        if self.enabled:
            self.synced.append((key, value))
