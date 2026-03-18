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
        if not storage.exists(key):
            return -2

        expires_at = self._expirations.get(key)
        if expires_at is None:
            return -1

        remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        return max(remaining, 0)

    def purge_expired_keys(self, storage: StorageManager) -> list[str]:
        # 만료된 key 목록을 반환해서 상위 오케스트레이터(Redis)가
        # storage 삭제 외에 TTL 외부 인덱스(invalidation 등)도 함께 정리할 수 있게 한다.
        expired_keys: list[str] = []
        for key in list(self._expirations):
            if self.purge_if_expired(key, storage):
                expired_keys.append(key)
        return expired_keys

    def purge_if_expired(self, key: str, storage: StorageManager) -> bool:
        expires_at = self._expirations.get(key)
        if expires_at is None:
            return False
        if datetime.now(timezone.utc) >= expires_at:
            # TTLManager는 "만료 여부 판단 + storage에서 key 제거"까지만 담당한다.
            # invalidation index 정리는 Redis 레이어가 반환값(True)을 보고 처리한다.
            storage.delete(key)
            self._expirations.pop(key, None)
            return True
        return False

    def export(self) -> dict[str, str]:
        return {key: value.isoformat() for key, value in self._expirations.items()}

    def export_remaining(self, storage: StorageManager) -> dict[str, int]:
        self.purge_expired_keys(storage)
        remaining: dict[str, int] = {}
        now = datetime.now(timezone.utc)
        for key, expires_at in self._expirations.items():
            seconds = int((expires_at - now).total_seconds())
            remaining[key] = max(seconds, 0)
        return remaining

    def clear_all(self) -> None:
        self._expirations.clear()

    def load_expirations(
        self,
        values: dict[str, str],
        storage: StorageManager,
    ) -> list[str]:
        # snapshot에 남아 있던 TTL 중 이미 시간이 지난 key는 복구 즉시 제거하고,
        # 어떤 key가 제거됐는지 반환해서 상위 레이어가 보조 인덱스도 같이 정리하게 한다.
        self._expirations = {
            key: datetime.fromisoformat(value) for key, value in values.items()
        }
        return self.purge_expired_keys(storage)
