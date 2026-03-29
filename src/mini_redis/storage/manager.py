"""Primary in-memory storage."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any


@dataclass
class _Entry:
    key: str
    value: str


@dataclass
class _OperationSample:
    operation: str
    elapsed_us: float
    rehashing: bool
    size: int


class StorageManager:
    """Store key/value pairs in a hash table with incremental rehashing."""

    _MAX_LOAD_FACTOR = 0.75
    _INITIAL_CAPACITY = 4
    _REHASH_STEPS_PER_OPERATION = 1

    def __init__(self) -> None:
        self._table = self._build_table(self._INITIAL_CAPACITY)
        self._rehash_table: list[list[_Entry]] | None = None
        self._rehash_index = 0
        self._size = 0
        self._recent_operations: deque[_OperationSample] = deque(maxlen=64)
        self._rehash_starts = 0
        self._rehash_completions = 0
        self._rehash_started_at_ns: int | None = None
        self._last_rehash_duration_us: float | None = None

    def get(self, key: str) -> str | None:
        def run() -> str | None:
            self._advance_rehash()
            entry = self._find_entry(key)
            return None if entry is None else entry.value

        return self._record_operation("get", run)

    def set(self, key: str, value: str) -> None:
        def run() -> None:
            self._advance_rehash()
            self._start_rehash_if_needed()

            if self._rehash_table is not None:
                if self._upsert_entry(self._rehash_table, key, value):
                    return
                if self._delete_entry(self._table, key):
                    self._insert_entry(self._rehash_table, key, value)
                    return
                self._size += 1
                self._insert_entry(self._rehash_table, key, value)
                return

            if self._upsert_entry(self._table, key, value):
                return

            self._size += 1
            self._insert_entry(self._table, key, value)
            self._start_rehash_if_needed()

        self._record_operation("set", run)

    def delete(self, key: str) -> bool:
        def run() -> bool:
            self._advance_rehash()
            deleted = False

            if self._rehash_table is not None:
                deleted = self._delete_entry(self._rehash_table, key) or deleted

            deleted = self._delete_entry(self._table, key) or deleted
            if deleted:
                self._size -= 1
            return deleted

        return self._record_operation("delete", run)

    def exists(self, key: str) -> bool:
        def run() -> bool:
            self._advance_rehash()
            return self._find_entry(key) is not None

        return self._record_operation("exists", run)

    def keys(self) -> list[str]:
        def run() -> list[str]:
            self._advance_rehash()
            return sorted(self.items().keys())

        return self._record_operation("keys", run)

    def items(self) -> dict[str, str]:
        def run() -> dict[str, str]:
            self._advance_rehash()
            return self._collect_items()

        return self._record_operation("items", run)

    def clear(self) -> int:
        def run() -> int:
            removed = self._size
            self._table = self._build_table(self._INITIAL_CAPACITY)
            self._rehash_table = None
            self._rehash_index = 0
            self._size = 0
            self._rehash_started_at_ns = None
            self._last_rehash_duration_us = None
            return removed

        return self._record_operation("clear", run)

    def load_items(self, values: dict[str, str]) -> None:
        def run() -> None:
            self._table = self._build_table(self._INITIAL_CAPACITY)
            self._rehash_table = None
            self._rehash_index = 0
            self._size = 0
            self._rehash_started_at_ns = None
            self._last_rehash_duration_us = None
            for key, value in values.items():
                self.set(key, value)

        self._record_operation("load_items", run)

    def inspect(self, include_table: bool = False) -> dict[str, Any]:
        active_capacity = len(self._table)
        rehash_capacity = 0 if self._rehash_table is None else len(self._rehash_table)
        total_buckets = active_capacity if self._rehash_table is None else len(self._table)
        rehash_progress = (
            1.0
            if self._rehash_table is None
            else self._rehash_index / max(total_buckets, 1)
        )
        latencies = [sample.elapsed_us for sample in self._recent_operations]
        payload: dict[str, Any] = {
            "size": self._size,
            "active_capacity": active_capacity,
            "rehash_capacity": rehash_capacity,
            "is_rehashing": self._rehash_table is not None,
            "rehash_index": self._rehash_index,
            "rehash_progress": round(rehash_progress, 4),
            "rehash_starts": self._rehash_starts,
            "rehash_completions": self._rehash_completions,
            "last_rehash_duration_us": self._last_rehash_duration_us,
            "latency": {
                "samples": len(latencies),
                "last_us": None if not latencies else round(latencies[-1], 3),
                "max_us": None if not latencies else round(max(latencies), 3),
                "avg_us": None if not latencies else round(sum(latencies) / len(latencies), 3),
            },
            "recent_operations": [
                {
                    "operation": sample.operation,
                    "elapsed_us": round(sample.elapsed_us, 3),
                    "rehashing": sample.rehashing,
                    "size": sample.size,
                }
                for sample in self._recent_operations
            ],
        }
        if include_table:
            payload["table"] = {
                "active": self._serialize_table(self._table),
                "rehash": []
                if self._rehash_table is None
                else self._serialize_table(self._rehash_table),
            }
            payload["items"] = self._collect_items()
        return payload

    def latest_operation(self) -> dict[str, Any] | None:
        if not self._recent_operations:
            return None
        sample = self._recent_operations[-1]
        return {
            "operation": sample.operation,
            "elapsed_us": round(sample.elapsed_us, 3),
            "rehashing": sample.rehashing,
            "size": sample.size,
        }

    def reset_diagnostics(self) -> None:
        self._recent_operations.clear()
        self._rehash_starts = 0
        self._rehash_completions = 0
        self._rehash_started_at_ns = None
        self._last_rehash_duration_us = None

    def _build_table(self, capacity: int) -> list[list[_Entry]]:
        return [[] for _ in range(max(capacity, self._INITIAL_CAPACITY))]

    def _iter_tables(self) -> list[list[list[_Entry]]]:
        if self._rehash_table is None:
            return [self._table]
        return [self._table, self._rehash_table]

    def _bucket_index(self, key: str, capacity: int) -> int:
        return hash(key) % capacity

    def _find_entry_in_table(self, table: list[list[_Entry]], key: str) -> _Entry | None:
        bucket = table[self._bucket_index(key, len(table))]
        for entry in bucket:
            if entry.key == key:
                return entry
        return None

    def _find_entry(self, key: str) -> _Entry | None:
        if self._rehash_table is not None:
            entry = self._find_entry_in_table(self._rehash_table, key)
            if entry is not None:
                return entry
        return self._find_entry_in_table(self._table, key)

    def _insert_entry(self, table: list[list[_Entry]], key: str, value: str) -> None:
        bucket = table[self._bucket_index(key, len(table))]
        bucket.insert(0, _Entry(key=key, value=value))

    def _upsert_entry(self, table: list[list[_Entry]], key: str, value: str) -> bool:
        entry = self._find_entry_in_table(table, key)
        if entry is None:
            return False
        entry.value = value
        return True

    def _delete_entry(self, table: list[list[_Entry]], key: str) -> bool:
        bucket = table[self._bucket_index(key, len(table))]
        for index, entry in enumerate(bucket):
            if entry.key == key:
                del bucket[index]
                return True
        return False

    def _load_factor(self) -> float:
        return self._size / len(self._table)

    def _start_rehash_if_needed(self) -> None:
        if self._rehash_table is not None:
            return
        if self._load_factor() <= self._MAX_LOAD_FACTOR:
            return
        self._rehash_table = self._build_table(len(self._table) * 2)
        self._rehash_index = 0
        self._rehash_starts += 1
        self._rehash_started_at_ns = perf_counter_ns()

    def _advance_rehash(self, steps: int | None = None) -> None:
        if self._rehash_table is None:
            return

        remaining_steps = steps or self._REHASH_STEPS_PER_OPERATION
        while remaining_steps > 0 and self._rehash_table is not None:
            if self._rehash_index >= len(self._table):
                self._table = self._rehash_table
                self._rehash_table = None
                self._rehash_index = 0
                self._rehash_completions += 1
                if self._rehash_started_at_ns is not None:
                    self._last_rehash_duration_us = (
                        perf_counter_ns() - self._rehash_started_at_ns
                    ) / 1_000
                    self._rehash_started_at_ns = None
                return

            bucket = self._table[self._rehash_index]
            for entry in bucket:
                self._insert_entry(self._rehash_table, entry.key, entry.value)
            self._table[self._rehash_index] = []
            self._rehash_index += 1
            remaining_steps -= 1

    def _collect_items(self) -> dict[str, str]:
        combined: dict[str, str] = {}
        for table in self._iter_tables():
            for bucket in table:
                for entry in bucket:
                    combined[entry.key] = entry.value
        return combined

    def _serialize_table(self, table: list[list[_Entry]]) -> list[list[str]]:
        return [[entry.key for entry in bucket] for bucket in table]

    def _record_operation(self, operation: str, callback):
        started_at_ns = perf_counter_ns()
        result = callback()
        elapsed_us = (perf_counter_ns() - started_at_ns) / 1_000
        self._recent_operations.append(
            _OperationSample(
                operation=operation,
                elapsed_us=elapsed_us,
                rehashing=self._rehash_table is not None,
                size=self._size,
            )
        )
        return result
