<p align="center">
  <img src="./img/mini-redis-logo.png" alt="Mini Redis Logo" width="220" />
</p>

# Mini-Redis

Mini-Redis is a Python-based Redis-like server built around a custom TCP + RESP stack.

This project is organized with clear boundaries between transport, protocol, command routing, and internal data managers:

- CLI client for local UX
- RESP codec for wire encoding/decoding
- TCP client/server for transport only
- `CommandManager` as the server-side execution entrypoint
- Per-command handlers that invoke the internal `Redis` engine
- Modular managers for storage, TTL, persistence, invalidation, and Mongo integration
- File-backed AOF/RDB skeleton under `data/`

## Actual Screen

The main screen below shows the interactive CLI connected to the Mini-Redis server.

![Mini Redis Main Page](./img/mini-redis-main.png)

From this screen, you can:

- send Redis-like commands such as `PING`, `SET`, `GET`, `TTL`, and `FLUSHDB`
- inspect internal storage behavior through `INSPECT STORAGE`
- observe incremental rehashing and request latency using `INSPECT STORAGE RUN <count>`
- update the generated keys with `INSPECT STORAGE UPDATE <count>` to see whether resizing finishes
- test persistence and recovery flows with commands like `SAVE`, `LOAD`, and `INFO PERSISTENCE`

In short, the CLI is not only a command interface, but also a live diagnostic surface for explaining how the Mini-Redis server behaves internally.

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
SET user:1 hello
GET user:1
MGET user:1 user:2
EXISTS user:1
INCR counter
EXPIRE user:1 60
TTL user:1
KEYS
SAVE
FLUSHDB
DELETE user:1
QUIT
```
