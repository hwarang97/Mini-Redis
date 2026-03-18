"""TTL management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mini_redis.storage.manager import StorageManager


class TTLManager:
    """Track expirations separately from core storage."""

    def __init__(self) -> None:
        self._expirations: dict[str, datetime] = {}

    def set_expiration(self, key: str, ttl_seconds: int | None) -> None:
        if ttl_seconds is None:
            self._expirations.pop(key, None)
            return
        self._expirations[key] = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    def clear_expiration(self, key: str) -> None:
        self._expirations.pop(key, None)

    def ttl(self, key: str, storage: StorageManager) -> int:
        self.purge_if_expired(key, storage)
        if not storage.exists(key):
            return -2

        expires_at = self._expirations.get(key)
        if expires_at is None:
            return -1

        remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        return max(remaining, 0)

    def purge_expired_keys(self, storage: StorageManager) -> None:
        for key in list(self._expirations):
            self.purge_if_expired(key, storage)

    def purge_if_expired(self, key: str, storage: StorageManager) -> None:
        expires_at = self._expirations.get(key)
        if expires_at is None:
            return
        if datetime.now(timezone.utc) >= expires_at:
            storage.delete(key)
            self._expirations.pop(key, None)

    def export(self) -> dict[str, str]:
        return {key: value.isoformat() for key, value in self._expirations.items()}

    def clear_all(self) -> None:
        self._expirations.clear()
