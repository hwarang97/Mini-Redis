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
BGSAVE
BGREWRITEAOF
CONFIG GET *
CONFIG SET fsync_policy always
SET user:1 hello
GET user:1
INFO PERSISTENCE
MGET user:1 user:2
EXISTS user:1
INCR counter
EXPIRE user:1 60
TTL user:1
KEYS
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
