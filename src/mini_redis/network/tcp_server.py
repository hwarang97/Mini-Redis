"""TCP server transport layer."""

from __future__ import annotations

import socketserver  # socketserver는 요청별 핸들러와 스트림 입출력을 제공해서 transport 계층 구현을 단순하게 해 준다.

from mini_redis.commands.manager import CommandManager  # 서버는 직접 Redis를 부르지 않고 CommandManager를 실행 진입점으로 사용해야 한다.
from mini_redis.protocol.resp import RespCodec  # wire format 해석은 RESP codec에 맡겨 transport/프로토콜 책임을 분리한다.


class _RequestHandler(socketserver.StreamRequestHandler):
    """Transport-only request handler that delegates execution."""

    manager: CommandManager
    codec: RespCodec

    def handle(self) -> None:
        while True:
            try:
                # self.rfile은 StreamRequestHandler가 제공하는 바이너리 입력 스트림이다.
                # decode_command_stream(...)은 한 줄짜리 JSON이 아니라, 여러 줄에 걸친 RESP 프레임 전체를 끝까지 읽을 수 있다.
                command = self.codec.decode_command_stream(self.rfile)
            except ValueError:
                # 잘못되었거나 중간에 끊긴 프레임, 혹은 클라이언트 종료는 transport 레벨에서 조용히 끝낸다.
                return
            # 한 연결에서 여러 명령을 연속 처리할 수 있게 loop를 유지한다.
            # 실제 실행은 반드시 CommandManager를 통해서만 이루어져, TCP 서버가 비즈니스 로직을 직접 처리하지 않는다.
            # 요청별 스레드는 여기까지는 병렬로 들어올 수 있지만, "명령을 어떤 경로로 실행할지"에 대한 공통 관문은
            # manager.execute(...) 하나로 고정해 두었다. 그래서 이후 queue 기반 직렬화나 공통 후처리를 추가하더라도
            # transport 코드를 거의 건드리지 않고 이 경계 안에서 확장할 수 있다.
            response = self.manager.execute(command)
            # encode_response(...)는 실행 결과를 RESP bytes로 바꿔 클라이언트에 다시 써 준다.
            self.wfile.write(self.codec.encode_response(response))
            self.wfile.flush()


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    # 같은 주소를 빠르게 다시 바인딩할 수 있게 해서 테스트/재시작 시 "address already in use"를 줄인다.
    allow_reuse_address = True


class TCPServer:
    """Wrap socketserver setup so transport stays separate from execution."""

    def __init__(self, host: str, port: int, manager: CommandManager, codec: RespCodec) -> None:
        # type(...) 내장 함수로 handler 클래스를 런타임에 하나 만들고,
        # class attribute로 manager / codec을 주입해서 transport 레이어에서 필요한 의존성만 연결한다.
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
