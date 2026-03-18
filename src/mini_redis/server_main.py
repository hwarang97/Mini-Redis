"""Server entrypoint."""

from __future__ import annotations

from mini_redis.bootstrap import build_command_manager
from mini_redis.config import HOST, PORT
from mini_redis.network.tcp_server import TCPServer
from mini_redis.protocol.resp import RespCodec


def main() -> None:
    server = TCPServer(
        host=HOST,
        port=PORT,
        manager=build_command_manager(),
        codec=RespCodec(),
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
