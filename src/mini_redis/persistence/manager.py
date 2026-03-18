"""Persistence hooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_redis.persistence.aof import AOFWriter
from mini_redis.persistence.rdb import RDBSnapshotStore


class PersistenceManager:
    """Coordinate append-only logging and snapshots."""

    def __init__(self, aof_writer: AOFWriter, snapshot_store: RDBSnapshotStore) -> None:
        self._operation_log: list[tuple[object, ...]] = []
        self._aof_writer = aof_writer
        self._snapshot_store = snapshot_store

    def append(self, operation: str, *args: object) -> None:
        self._operation_log.append((operation, *args))
        self._aof_writer.append(operation, list(args))

    def save_snapshot(self, payload: dict[str, Any]) -> Path:
        return self._snapshot_store.save(payload)

    @property
    def operation_log(self) -> list[tuple[object, ...]]:
        return list(self._operation_log)
