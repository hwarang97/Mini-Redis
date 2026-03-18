"""CLI entrypoint."""

from __future__ import annotations

from mini_redis.config import HOST, PORT
from mini_redis.cli.client import CLIClient
from mini_redis.network.tcp_client import TCPClient
from mini_redis.protocol.resp import RespCodec


def main() -> None:
    codec = RespCodec()
    client = TCPClient(host=HOST, port=PORT, codec=codec)
    CLIClient(tcp_client=client, codec=codec, host=HOST, port=PORT).run()


if __name__ == "__main__":
    main()
