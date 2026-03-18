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

## Example commands

```text
PING
HELP
SET user:1 hello
GET user:1
MGET user:1 user:2
INFO PERSISTENCE
INFO MONGO
INSPECT STORAGE
INSPECT STORAGE FULL
INSPECT STORAGE RESET
INSPECT STORAGE RUN 20
INSPECT STORAGE UPDATE 20
PROBE SET demo:key 1
PROBE UPDATE inspect:run:0 updated:0
BENCHMARK REDIS 1000 KEEP
BENCHMARK MONGO 1000
BENCHMARK HYBRID 1000
WATCH 0.2 20 INSPECT STORAGE
WATCH 0.5 10 INSPECT STORAGE FULL
LIVESET 20 0.1
DUMPALL
SAVE
LOAD
REPAIRAOF
REWRITEAOF
FLUSHDB
QUIT
```

## Rehash inspection

Use `PROBE`, `INSPECT STORAGE RUN`, and `INSPECT STORAGE UPDATE` when you want to generate writes in real time and observe whether resizing introduces per-request latency spikes.

- `PROBE SET <key> <value>`
  - Executes one write and immediately returns a one-line summary.
- `PROBE UPDATE <key> <value>`
  - Updates an existing key and returns the same one-line summary.
- `INSPECT STORAGE RUN <count>`
  - Generates synthetic insert requests on the server and prints one summary line per request.
- `INSPECT STORAGE UPDATE <count>`
  - Updates the synthetic `inspect:run:<index>` keys created by `RUN`.
- `INSPECT STORAGE`
  - Shows the current storage summary in one line.
- `INSPECT STORAGE FULL`
  - Shows the full bucket layout and item map.
- `INSPECT STORAGE RESET`
  - Clears in-memory diagnostic counters and recent operation samples only.

Example:

```text
FLUSHDB
INSPECT STORAGE RESET
INSPECT STORAGE RUN 40
INSPECT STORAGE
INSPECT STORAGE UPDATE 40
INSPECT STORAGE FULL
```

## Benchmark modes

Use `BENCHMARK` to compare write cost across backends:

- `BENCHMARK REDIS <count>`
  - Measures in-memory Redis writes only.
- `BENCHMARK MONGO <count>`
  - Measures MongoDB writes only.
- `BENCHMARK HYBRID <count>`
  - Measures writing the same keys to Redis and MongoDB together.

All benchmark responses include elapsed time, throughput, and backend-specific details. Redis and hybrid runs also include storage latency and rehash diagnostics.

## Recovery policies

- `best-effort`: load snapshot when available and replay valid AOF entries while ignoring corrupted tail
- `snapshot-first`: prefer snapshot plus valid AOF replay
- `aof-only`: rebuild only from AOF and ignore snapshot contents
- `strict`: fail startup when corrupted AOF content is detected

## Runtime config keys

- `recovery_policy`
- `fsync_policy`
- `autosave_interval`
- `autorewrite_min_operations`

## MongoDB sync

Mini Redis keeps in-memory storage as the primary runtime state and can optionally sync write operations to MongoDB. The sync path is:

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
