"""Shared configuration defaults."""

from __future__ import annotations

import os
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
MONGO_ENABLED = os.getenv("MINI_REDIS_MONGO_ENABLED", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MONGO_URI = os.getenv("MINI_REDIS_MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("MINI_REDIS_MONGO_DB", "mini_redis")
MONGO_COLLECTION = os.getenv("MINI_REDIS_MONGO_COLLECTION", "kv_store")
MONGO_SERVER_SELECTION_TIMEOUT_MS = int(
    os.getenv("MINI_REDIS_MONGO_SERVER_SELECTION_TIMEOUT_MS", "2000")
)
