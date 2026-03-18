"""Shared configuration defaults."""

from __future__ import annotations

from pathlib import Path

HOST = "127.0.0.1"
PORT = 6380
ENCODING = "utf-8"
DEFAULT_RECOVERY_POLICY = "best-effort"
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
APPEND_ONLY_FILE = DATA_DIR / "appendonly.aof"
SNAPSHOT_FILE = DATA_DIR / "dump.rdb.json"
PERSISTENCE_META_FILE = DATA_DIR / "persistence.meta.json"
