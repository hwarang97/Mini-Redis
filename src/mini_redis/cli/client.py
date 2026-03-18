"""Interactive CLI client."""

from __future__ import annotations

from mini_redis.cli.parser import parse_cli_command
from mini_redis.network.tcp_client import TCPClient
from mini_redis.protocol.resp import RespCodec


class CLIClient:
    """Prompt for commands and print server responses."""

    def __init__(self, tcp_client: TCPClient, codec: RespCodec) -> None:
        self._tcp_client = tcp_client
        self._codec = codec

    def run(self) -> None:
        print("Mini Redis CLI. Type QUIT to exit.")
        while True:
            try:
                raw = input("mini-redis> ")
            except EOFError:
                print()
                break

            command = parse_cli_command(raw)
            if command is None:
                continue

            response = self._tcp_client.send(command)
            rendered = self._codec.format_for_display(response)
            print(rendered)

            if command["name"] == "QUIT":
                break
