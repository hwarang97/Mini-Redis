"""TCP client transport."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any

from mini_redis.network.timing import unwrap_timed_response
from mini_redis.protocol.resp import RespCodec
from mini_redis.types import Command


@dataclass(frozen=True)
class TimedResponse:
    value: Any
    server_time_ms: float | None


class TCPClient:
    """Send RESP-encoded commands to the TCP server."""

    def __init__(self, host: str, port: int, codec: RespCodec) -> None:
        self._host = host
        self._port = port
        self._codec = codec

    def send(self, command: Command) -> Any:
        return self.send_timed(command).value

    def send_timed(self, command: Command) -> TimedResponse:
        with socket.create_connection((self._host, self._port)) as conn:
            conn.sendall(self._codec.encode_command(command))
            with conn.makefile("rb") as stream:
                payload = self._codec.decode_response_stream(stream)

        value, server_time_ms = unwrap_timed_response(payload)
        return TimedResponse(value=value, server_time_ms=server_time_ms)
