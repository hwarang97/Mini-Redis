"""TCP client transport."""

from __future__ import annotations

import socket  # socket 모듈은 TCP 연결 생성과 송수신 같은 순수 transport 책임만 담당한다.
from typing import Any  # send()가 문자열/정수/리스트/None 등 여러 RESP 응답 타입을 받을 수 있어서 Any를 사용한다.

from mini_redis.protocol.resp import RespCodec  # RESP 직렬화/역직렬화는 transport 바깥의 전용 codec에 맡긴다.
from mini_redis.types import Command  # 클라이언트가 서버로 보내는 명령의 공통 형태를 유지한다.


class TCPClient:
    """Send RESP-encoded commands to the TCP server."""

    def __init__(self, host: str, port: int, codec: RespCodec) -> None:
        self._host = host
        self._port = port
        self._codec = codec

    def send(self, command: Command) -> Any:
        # socket.create_connection(...)은 (host, port) 튜플을 받아 TCP 연결을 열어 주는 표준 헬퍼다.
        # with 문을 쓰면 블록을 빠져나갈 때 close()가 자동 호출되어 소켓이 정리된다.
        with socket.create_connection((self._host, self._port)) as conn:
            # sendall(...)은 payload 전체가 전송될 때까지 내부적으로 반복 전송해 준다.
            conn.sendall(self._codec.encode_command(command))
            # makefile("rb")는 소켓을 "바이너리 읽기 스트림"처럼 감싸 준다.
            # RESP는 줄 단위/길이 단위로 읽어야 해서 recv() 반복보다 stream API가 더 잘 맞는다.
            with conn.makefile("rb") as stream:
                # 응답 파싱은 codec에게 위임해서 TCP 클라이언트는 transport 책임만 유지한다.
                return self._codec.decode_response_stream(stream)
