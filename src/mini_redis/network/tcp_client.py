"""TCP client transport."""

from __future__ import annotations

import socket
from typing import Any

from mini_redis.protocol.resp import RespCodec
from mini_redis.types import Command


class TCPClient:
    """Send RESP-encoded commands to the TCP server."""

    def __init__(self, host: str, port: int, codec: RespCodec) -> None:
        self._host = host
        self._port = port
        self._codec = codec

    def send(self, command: Command) -> Any:
        with socket.create_connection((self._host, self._port)) as conn:
            conn.sendall(self._codec.encode_command(command))
            payload = self._recv_line(conn)
        return self._codec.decode_response(payload)

    @staticmethod
    def _recv_line(conn: socket.socket) -> bytes:
        chunks = bytearray()
        while not chunks.endswith(b"\n"):
            data = conn.recv(4096)
            if not data:
                break
            chunks.extend(data)
        return bytes(chunks)
