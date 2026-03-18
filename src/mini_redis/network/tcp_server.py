"""TCP server transport layer."""

from __future__ import annotations

import socketserver
from time import perf_counter_ns

from mini_redis.commands.manager import CommandManager
from mini_redis.network.timing import unwrap_timed_command
from mini_redis.network.timing import wrap_timed_response
from mini_redis.protocol.resp import RespCodec


class _RequestHandler(socketserver.StreamRequestHandler):
    """Transport-only request handler that delegates execution."""

    manager: CommandManager
    codec: RespCodec

    def handle(self) -> None:
        while True:
            try:
                command = self.codec.decode_command_stream(self.rfile)
            except (OSError, ValueError):
                return

            command, wants_timing = unwrap_timed_command(command)
            if command["name"] == "__INVALID_TIMED__":
                response = "ERR timed transport requires a nested command"
                wants_timing = False
            elif wants_timing:
                started = perf_counter_ns()
                response = self.manager.execute(command)
                server_time_us = (perf_counter_ns() - started) // 1000
                response = wrap_timed_response(response, int(server_time_us))
            else:
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
