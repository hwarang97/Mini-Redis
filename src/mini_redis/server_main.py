"""Server entrypoint."""

from __future__ import annotations

from mini_redis.bootstrap import build_command_manager
from mini_redis.config import HOST, PORT
from mini_redis.network.tcp_server import TCPServer
from mini_redis.protocol.resp import RespCodec


def _read_info_fields(payload: object) -> dict[str, str]:
    if not isinstance(payload, str):
        return {}

    fields: dict[str, str] = {}
    for line in payload.replace("\r\n", "\n").splitlines():
        if ":" not in line or line.startswith("# "):
            continue
        key, value = line.split(":", 1)
        fields[key] = value
    return fields


def main() -> None:
    manager = build_command_manager()
    report = manager.recovery_report
    server = TCPServer(
        host=HOST,
        port=PORT,
        manager=manager,
        codec=RespCodec(),
    )
    if report is not None:
        print(
            "Recovery summary:"
            f" snapshot_loaded={report.snapshot_loaded}"
            f" replayed_entries={report.replayed_entries}"
            f" recovered_keys={report.recovered_keys}"
            f" aof_corruption_detected={report.aof_corruption_detected}"
            f" ignored_aof_entries={report.ignored_aof_entries}"
            f" corrupted_aof_line={report.corrupted_aof_line}"
        )
    mongo_info = _read_info_fields(manager.execute({"name": "INFO", "args": ["MONGO"]}))
    print(
        "Mongo status:"
        f" enabled={mongo_info.get('enabled', 'unknown')}"
        f" connected={mongo_info.get('connected', 'unknown')}"
        f" database={mongo_info.get('database', '-')}"
        f" collection={mongo_info.get('collection', '-')}"
    )
    print(f"Mini Redis server listening on {HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
