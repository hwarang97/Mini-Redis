"""Application wiring."""

from __future__ import annotations

from pathlib import Path

from mini_redis.commands.handlers.bgrewriteaof import BGRewriteAOFHandler
from mini_redis.commands.handlers.bgsave import BGSaveHandler
from mini_redis.commands.handlers.config import ConfigHandler
from mini_redis.commands.handlers.delete import DeleteHandler
from mini_redis.commands.handlers.exists import ExistsHandler
from mini_redis.commands.handlers.expire import ExpireHandler
from mini_redis.commands.handlers.flushdb import FlushDBHandler
from mini_redis.commands.handlers.get import GetHandler
from mini_redis.commands.handlers.info import InfoHandler
from mini_redis.commands.handlers.incr import IncrHandler
from mini_redis.commands.handlers.invalidate import InvalidateHandler
from mini_redis.commands.handlers.keys import KeysHandler
from mini_redis.commands.handlers.load import LoadHandler
from mini_redis.commands.handlers.mget import MGetHandler
from mini_redis.commands.handlers.ping import PingHandler
from mini_redis.commands.handlers.quit import QuitHandler
from mini_redis.commands.handlers.repairaof import RepairAOFHandler
from mini_redis.commands.handlers.rewriteaof import RewriteAOFHandler
from mini_redis.commands.handlers.save import SaveHandler
from mini_redis.commands.handlers.set import SetHandler
from mini_redis.commands.handlers.ttl import TTLHandler
from mini_redis.commands.manager import CommandManager
from mini_redis.config import APPEND_ONLY_FILE, DEFAULT_RECOVERY_POLICY, PERSISTENCE_META_FILE, SNAPSHOT_FILE
from mini_redis.engine.redis import Redis
from mini_redis.invalidation.manager import InvalidationManager
from mini_redis.persistence.aof import AOFWriter
from mini_redis.persistence.manager import PersistenceManager
from mini_redis.persistence.meta import PersistenceMetadataStore
from mini_redis.persistence.rdb import RDBSnapshotStore
from mini_redis.storage.manager import StorageManager
from mini_redis.storage.mongo_adapter import MongoAdapter
from mini_redis.storage.ttl import TTLManager


def build_command_manager(
    appendonly_path: Path | None = None,
    snapshot_path: Path | None = None,
    metadata_path: Path | None = None,
    recovery_policy: str | None = None,
) -> CommandManager:
    storage = StorageManager()
    ttl = TTLManager()
    # invalidation을 독립 매니저로 분리해서
    # store/TTL/persistence와 역할 경계를 유지한 채 협업 가능한 구조를 만든다.
    invalidation = InvalidationManager()
    persistence = PersistenceManager(
        aof_writer=AOFWriter(appendonly_path or APPEND_ONLY_FILE),
        snapshot_store=RDBSnapshotStore(snapshot_path or SNAPSHOT_FILE),
        metadata_store=PersistenceMetadataStore(metadata_path or PERSISTENCE_META_FILE),
        recovery_policy=recovery_policy or DEFAULT_RECOVERY_POLICY,
    )
    mongo = MongoAdapter(enabled=False)
    redis = Redis(
        storage=storage,
        ttl=ttl,
        persistence=persistence,
        invalidation=invalidation,
        mongo=mongo,
    )
    # Register Redis-owned work so persistence can trigger background jobs without breaking boundaries.
    persistence.register_background_hooks(redis.save, redis.rewrite_aof)
    recovery_report = persistence.restore(redis)

    handlers = {
        "PING": PingHandler(redis),
        "BGSAVE": BGSaveHandler(redis),
        "BGREWRITEAOF": BGRewriteAOFHandler(redis),
        "CONFIG": ConfigHandler(redis),
        "SET": SetHandler(redis),
        "GET": GetHandler(redis),
        "INFO": InfoHandler(redis),
        "MGET": MGetHandler(redis),
        # INVALIDATE도 다른 명령과 동일하게 CommandManager를 통해 진입시켜
        # TCP/RESP/Redis 경계를 우회하지 않게 한다.
        "INVALIDATE": InvalidateHandler(redis),
        "DELETE": DeleteHandler(redis),
        "EXISTS": ExistsHandler(redis),
        "INCR": IncrHandler(redis),
        "EXPIRE": ExpireHandler(redis),
        "TTL": TTLHandler(redis),
        "KEYS": KeysHandler(redis),
        "LOAD": LoadHandler(redis),
        "FLUSHDB": FlushDBHandler(redis),
        "REPAIRAOF": RepairAOFHandler(redis),
        "REWRITEAOF": RewriteAOFHandler(redis),
        "SAVE": SaveHandler(redis),
        "QUIT": QuitHandler(redis),
    }
    return CommandManager(handlers=handlers, recovery_report=recovery_report)
