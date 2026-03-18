"""TCP server transport layer."""

from __future__ import annotations

import socketserver
from typing import Any

from mini_redis.commands.manager import CommandManager
from mini_redis.protocol.resp import RespCodec


class _RequestHandler(socketserver.StreamRequestHandler):
    """Transport-only request handler that delegates execution."""

    manager: CommandManager
    codec: RespCodec

    def handle(self) -> None:
        payload = self.rfile.readline()
        if not payload:
            return

        command = self.codec.decode_command(payload)
        response = self.manager.execute(command)
        self.wfile.write(self.codec.encode_response(response))


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class TCPServer:
    """Wrap socketserver setup so transport stays separate from execution."""

    def __init__(self, host: str, port: int, manager: CommandManager, codec: RespCodec) -> None:
        handler_cls = type(
            "MiniRedisRequestHandler",
            (_RequestHandler,),
            {"manager": manager, "codec": codec},
        )
        self._server = ThreadedTCPServer((host, port), handler_cls)

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
