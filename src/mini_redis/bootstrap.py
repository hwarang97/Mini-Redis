"""Application wiring."""

from __future__ import annotations

from mini_redis.commands.handlers.delete import DeleteHandler
from mini_redis.commands.handlers.exists import ExistsHandler
from mini_redis.commands.handlers.expire import ExpireHandler
from mini_redis.commands.handlers.flushdb import FlushDBHandler
from mini_redis.commands.handlers.get import GetHandler
from mini_redis.commands.handlers.incr import IncrHandler
from mini_redis.commands.handlers.keys import KeysHandler
from mini_redis.commands.handlers.mget import MGetHandler
from mini_redis.commands.handlers.ping import PingHandler
from mini_redis.commands.handlers.quit import QuitHandler
from mini_redis.commands.handlers.save import SaveHandler
from mini_redis.commands.handlers.set import SetHandler
from mini_redis.commands.handlers.ttl import TTLHandler
from mini_redis.commands.manager import CommandManager
from mini_redis.config import APPEND_ONLY_FILE, SNAPSHOT_FILE
from mini_redis.engine.redis import Redis
from mini_redis.persistence.aof import AOFWriter
from mini_redis.persistence.invalidation import InvalidationManager
from mini_redis.persistence.manager import PersistenceManager
from mini_redis.persistence.rdb import RDBSnapshotStore
from mini_redis.storage.manager import StorageManager
from mini_redis.storage.mongo_adapter import MongoAdapter
from mini_redis.storage.ttl import TTLManager


def build_command_manager() -> CommandManager:
    storage = StorageManager()
    ttl = TTLManager()
    persistence = PersistenceManager(
        aof_writer=AOFWriter(APPEND_ONLY_FILE),
        snapshot_store=RDBSnapshotStore(SNAPSHOT_FILE),
    )
    invalidation = InvalidationManager()
    mongo = MongoAdapter(enabled=False)
    redis = Redis(
        storage=storage,
        ttl=ttl,
        persistence=persistence,
        invalidation=invalidation,
        mongo=mongo,
    )

    handlers = {
        "PING": PingHandler(redis),
        "SET": SetHandler(redis),
        "GET": GetHandler(redis),
        "MGET": MGetHandler(redis),
        "DELETE": DeleteHandler(redis),
        "EXISTS": ExistsHandler(redis),
        "INCR": IncrHandler(redis),
        "EXPIRE": ExpireHandler(redis),
        "TTL": TTLHandler(redis),
        "KEYS": KeysHandler(redis),
        "FLUSHDB": FlushDBHandler(redis),
        "SAVE": SaveHandler(redis),
        "QUIT": QuitHandler(redis),
    }
    return CommandManager(handlers=handlers)
