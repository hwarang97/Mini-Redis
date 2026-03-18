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
INSPECT STORAGE
INSPECT STORAGE FULL
INSPECT STORAGE RESET
INSPECT STORAGE RUN 20
INSPECT STORAGE RUN 20 0.05
PROBE SET demo:key 1
BENCHMARK REDIS 1000 KEEP
BENCHMARK MONGO 1000
BENCHMARK HYBRID 1000
WATCH 0.2 20 INSPECT STORAGE
WATCH 0.5 10 INSPECT STORAGE FULL
LIVESET 20 0.1
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
SAVE
LOAD
REPAIRAOF
REWRITEAOF
FLUSHDB
DELETE user:1
QUIT
```

## Rehash inspection

Use `PROBE SET` and `LIVESET` when you want to generate writes in real time and observe whether resizing introduces per-request latency spikes.

- `PROBE SET <key> <value>`
  - executes one write and immediately returns a one-line summary:
  - `[request 처리 시간] [현재 테이블 크기] [리사이징 여부]`
- `LIVESET <count> [interval_seconds] [key_prefix]`
  - generates repeated `PROBE SET` requests from the CLI so you can observe write bursts live

Example:

```text
LIVESET 30 0.1
```

This will print one line per generated request, for example:

```text
[request 18.200us] [table 8] [rehashing False] size=3 rehash_capacity=0 progress=1.0 storage_set=7.5us
[request 26.100us] [table 8] [rehashing True] size=4 rehash_capacity=16 progress=0.0 storage_set=14.2us
```

If you want to inspect the full bucket layout after the burst, use `INSPECT STORAGE` or `INSPECT STORAGE FULL`.

`INSPECT STORAGE RUN <count> [interval_seconds]` is useful when you want the server itself to generate synthetic writes and immediately show what happened on each request. This is helpful for observing resize and latency behavior without manually typing many `SET` commands.

`INSPECT STORAGE RESET` clears only the in-memory diagnostic counters and recent operation samples. It does not delete stored key/value data.

- `INSPECT STORAGE`
  - shows size, active capacity, rehash capacity, rehash progress, and recent latency samples
- `INSPECT STORAGE FULL`
  - also shows the live key/value view plus the active and rehash bucket layouts
- `WATCH 0.2 20 INSPECT STORAGE`
  - repeats the same command every 0.2 seconds for 20 iterations so you can observe rehash progress live from the CLI

Suggested quick demo:

```text
INSPECT STORAGE RESET
INSPECT STORAGE RUN 40 0.05
INSPECT STORAGE FULL
LIVESET 40 0.05
INSPECT STORAGE
INSPECT STORAGE FULL
```

For larger batch experiments, `BENCHMARK REDIS <count> KEEP` keeps the inserted keys in memory, which makes it easier to inspect bucket growth and rehash progress after the write burst.

## Benchmark modes

Use `BENCHMARK` to compare write cost across backends:

- `BENCHMARK REDIS <count>`
  - measures in-memory Redis writes only
- `BENCHMARK MONGO <count>`
  - measures MongoDB writes only
- `BENCHMARK HYBRID <count>`
  - measures writing the same keys to Redis and MongoDB together

All benchmark responses include elapsed time, throughput, and backend-specific details. Redis and hybrid runs also include storage latency and rehash diagnostics.

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
