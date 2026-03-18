"""Primary in-memory storage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _Entry:
    key: str
    value: str


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

    def get(self, key: str) -> str | None:
        self._advance_rehash()
        entry = self._find_entry(key)
        return None if entry is None else entry.value

    def set(self, key: str, value: str) -> None:
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

    def delete(self, key: str) -> bool:
        self._advance_rehash()
        deleted = False

        if self._rehash_table is not None:
            deleted = self._delete_entry(self._rehash_table, key) or deleted

        deleted = self._delete_entry(self._table, key) or deleted
        if deleted:
            self._size -= 1
        return deleted

    def exists(self, key: str) -> bool:
        self._advance_rehash()
        return self._find_entry(key) is not None

    def keys(self) -> list[str]:
        self._advance_rehash()
        return sorted(self.items().keys())

    def items(self) -> dict[str, str]:
        self._advance_rehash()
        combined: dict[str, str] = {}
        for table in self._iter_tables():
            for bucket in table:
                for entry in bucket:
                    combined[entry.key] = entry.value
        return combined

    def clear(self) -> int:
        removed = self._size
        self._table = self._build_table(self._INITIAL_CAPACITY)
        self._rehash_table = None
        self._rehash_index = 0
        self._size = 0
        return removed

    def load_items(self, values: dict[str, str]) -> None:
        self._table = self._build_table(self._INITIAL_CAPACITY)
        self._rehash_table = None
        self._rehash_index = 0
        self._size = 0
        for key, value in values.items():
            self.set(key, value)

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

    def _advance_rehash(self, steps: int | None = None) -> None:
        if self._rehash_table is None:
            return

        remaining_steps = steps or self._REHASH_STEPS_PER_OPERATION
        while remaining_steps > 0 and self._rehash_table is not None:
            if self._rehash_index >= len(self._table):
                self._table = self._rehash_table
                self._rehash_table = None
                self._rehash_index = 0
                return

            bucket = self._table[self._rehash_index]
            for entry in bucket:
                self._insert_entry(self._rehash_table, entry.key, entry.value)
            self._table[self._rehash_index] = []
            self._rehash_index += 1
            remaining_steps -= 1
