"""TCP server transport layer."""

from __future__ import annotations

import socketserver

from mini_redis.commands.manager import CommandManager
from mini_redis.protocol.resp import RespCodec


class _RequestHandler(socketserver.StreamRequestHandler):
    """Transport-only request handler that delegates execution."""

    manager: CommandManager
    codec: RespCodec

    def handle(self) -> None:
        while True:
            try:
                # Read one RESP command at a time from the current socket.
                command = self.codec.decode_command_stream(self.rfile)
            except ValueError:
                # Stop serving this client when the peer closes the socket or sends
                # an incomplete frame; the outer server loop keeps accepting others.
                return

            response = self.manager.execute(command)
            self.wfile.write(self.codec.encode_response(response))
            self.wfile.flush()

            if command["name"] == "QUIT":
                return


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
