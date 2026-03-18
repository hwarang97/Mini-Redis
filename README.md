# Mini-Redis

Python skeleton for a collaborative Mini Redis project with explicit module boundaries:

- CLI client for local UX
- RESP codec for wire encoding/decoding
- TCP client/server for transport only
- `CommandManager` as the server-side execution entrypoint
- Per-command handlers that invoke the internal `Redis` engine
- Modular managers for storage, TTL, persistence, invalidation, and Mongo integration
- File-backed AOF/RDB skeleton under `data/`
- JSON metadata file for persistence lifecycle under `data/`
- Optional MongoDB write-through sync via `MongoManager -> MongoAdapter`

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
mini-redis-server
```

In another terminal:

```bash
source .venv/bin/activate
mini-redis-cli
```

Example commands:

```text
PING
HELP
BGSAVE
BGREWRITEAOF
CONFIG GET *
CONFIG SET fsync_policy always
SET user:1 hello
SET user:1:profile profile TAGS user:1
SET user:1:posts posts EX 60 TAGS user:1 feed
GET user:1
INVALIDATE user:1
INFO PERSISTENCE
INFO MONGO
MGET user:1 user:2
EXISTS user:1
INCR counter
EXPIRE user:1 60
TTL user:1
KEYS
DUMPALL
SAVE
LOAD
REPAIRAOF
REWRITEAOF
FLUSHDB
DELETE user:1
QUIT
```

Recovery policies:

- `best-effort`: load snapshot when available and replay valid AOF entries while ignoring corrupted tail
- `snapshot-first`: prefer snapshot plus valid AOF replay
- `aof-only`: rebuild only from AOF and ignore snapshot contents
- `strict`: fail startup when corrupted AOF content is detected

Runtime config keys:

- `recovery_policy`
- `fsync_policy`
- `autosave_interval`
- `autorewrite_min_operations`

## MongoDB sync

Mini Redis keeps in-memory storage as the primary runtime state and can optionally
sync write operations to MongoDB. The sync path is:

`Redis -> MongoManager -> MongoAdapter -> MongoDB`

Enable MongoDB sync with environment variables before starting the server:

```bash
export MINI_REDIS_MONGO_ENABLED=1
export MINI_REDIS_MONGO_URI="mongodb://127.0.0.1:27017"
export MINI_REDIS_MONGO_DB="mini_redis"
export MINI_REDIS_MONGO_COLLECTION="kv_store"
mini-redis-server
```

Project defaults:

- `MINI_REDIS_MONGO_URI`: `mongodb://127.0.0.1:27017`
- `MINI_REDIS_MONGO_DB`: `mini_redis`
- `MINI_REDIS_MONGO_COLLECTION`: `kv_store`
- `MINI_REDIS_MONGO_SERVER_SELECTION_TIMEOUT_MS`: `2000`

When enabled, `SET`, `INCR`, `DELETE`, and `FLUSHDB` will sync to MongoDB and
`INFO MONGO` will show connection and collection metadata.
