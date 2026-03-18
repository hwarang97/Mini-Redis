"""
RESP를 Redis에서 사용하는 이유와 이 파일의 핵심 역할

1. RESP는 텍스트 기반이라 사람이 읽기 쉽지만, 형식은 엄격해서 기계가 안정적으로 파싱하기 좋다.
2. 문자열, 정수, nil, 배열 같은 Redis의 대표 응답 타입을 한 프로토콜로 일관되게 표현할 수 있다.
3. TCP는 단순히 바이트 흐름만 전달하므로, 명령/응답의 시작과 끝을 구분할 명확한 규칙이 필요하다.
   RESP는 CRLF, 길이 정보, 타입 prefix를 사용해서 멀티라인 데이터도 안전하게 구분하게 해 준다.
4. Redis 생태계의 사실상 표준 프로토콜이라, 클라이언트-서버 책임을 분리하고 확장할 때도 구조가 단순해진다.

이 프로젝트에서의 핵심 포인트

- CLI는 입력/출력만 담당하고, 실제 wire format은 RespCodec이 맡는다.
- TCP 계층은 바이트를 전달만 하고, 명령 해석은 RESP 규칙에 따라 codec이 처리한다.
- 서버는 RESP로 받은 명령을 CommandManager에 넘기고, 실행 결과를 다시 RESP로 인코딩해 돌려준다.
- 즉, RESP는 "사람이 입력한 명령"을 "네트워크에서 안전하게 주고받는 데이터"로 바꾸는 공통 언어다.
"""

from __future__ import annotations

from io import BytesIO  # BytesIO는 bytes payload를 파일처럼 순차적으로 읽게 해 줘서, 스트림 전용 디코더를 재사용할 수 있다.
from typing import Any, BinaryIO  # Any는 여러 RESP 타입(str/int/list/None 등)을 표현하고, BinaryIO는 read/readline 가능한 바이너리 스트림 계약을 뜻한다.

from mini_redis.config import ENCODING  # 문자열을 bytes로 encode/decode 할 때 프로젝트 전체에서 같은 문자 인코딩을 쓰기 위해 가져온다.
from mini_redis.types import Command  # {"name": ..., "args": [...]} 형태의 공통 명령 타입을 그대로 유지하기 위해 사용한다.

CRLF = b"\r\n"  # RESP는 각 줄의 끝을 반드시 CRLF(\r\n)로 구분하므로, 매직값 대신 상수로 고정해 둔다.


class RespCodec:
    """Serialize commands and responses over the TCP boundary."""

    def encode_command(self, command: Command) -> bytes:
        # list 리터럴과 * 언패킹을 사용해 ["COMMAND", "arg1", "arg2"] 형태의 RESP Array 본문을 만든다.
        # command["name"].upper()의 upper()는 내장 문자열 메서드로, set/Set/SET 같은 입력을 모두 대문자 명령명으로 통일한다.
        parts = [command["name"].upper(), *command["args"]]
        # 명령도 RESP 관점에서는 "문자열들로 이루어진 배열"이므로 공통 배열 인코더를 그대로 사용한다.
        return self._encode_array(parts)

    def decode_command(self, payload: bytes) -> Command:
        # BytesIO(...)는 메모리 안의 bytes를 파일 객체처럼 감싸 준다.
        # 이렇게 하면 bytes 전체를 받은 경우에도 stream 기반 decode_command_stream()을 그대로 재사용할 수 있다.
        with BytesIO(payload) as stream:
            return self.decode_command_stream(stream)

    def decode_command_stream(self, stream: BinaryIO) -> Command:
        # 실제 RESP 파싱은 값 단위 공통 디코더에 맡긴다.
        data = self._decode_value(stream)
        # isinstance(...)는 파이썬 내장 함수로, 파싱 결과가 list인지 검사한다.
        # not data는 빈 리스트([])도 거부해서 "명령 이름이 없는 배열"을 막는다.
        if not isinstance(data, list) or not data:
            raise ValueError("RESP command must be a non-empty array")

        # 첫 번째 원소는 명령명이어야 하므로 문자열인지 확인한 뒤 upper()로 다시 한 번 표준화한다.
        name = self._expect_string(data[0]).upper()
        # 리스트 컴프리헨션으로 나머지 원소들을 순회하면서 모두 문자열인지 강제한다.
        # data[1:] 슬라이싱은 첫 원소(명령명)를 제외한 인자 구간만 잘라낸다.
        args = [self._expect_string(arg) for arg in data[1:]]
        return {"name": name, "args": args}

    def encode_response(self, value: Any) -> bytes:
        # 서버 응답은 타입에 따라 Simple String / Integer / Bulk String / Array / Null 로 갈리므로 공통 인코더 하나로 보낸다.
        return self._encode_value(value)

    def decode_response(self, payload: bytes) -> Any:
        # 응답도 decode_command()와 같은 방식으로 BytesIO에 감싸서 스트림 디코더를 재사용한다.
        with BytesIO(payload) as stream:
            return self.decode_response_stream(stream)

    def decode_response_stream(self, stream: BinaryIO) -> Any:
        # socket.makefile("rb") 같은 진짜 네트워크 스트림에서도 동일한 로직으로 RESP 프레임 1개를 읽는다.
        return self._decode_value(stream)

    def format_for_display(self, value: Any) -> str:
        if value is None:
            return "(nil)"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, list):
            if not value:
                return "(empty list)"
            return "\n".join(
                f"{index}) {self.format_for_display(item)}"
                for index, item in enumerate(value, start=1)
            )
        return str(value)

    def _encode_value(self, value: Any) -> bytes:
        if value is None:
            return b"$-1\r\n"
        if isinstance(value, bool):
            # bool은 int의 하위 타입이라서, int 검사보다 먼저 걸러야 True/False가 1/0으로 의도대로 직렬화된다.
            # f-string 안의 조건식(1 if ... else 0)은 파이썬 표현식 결과를 문자열로 끼워 넣는다.
            return f":{1 if value else 0}\r\n".encode(ENCODING)
        if isinstance(value, int):
            # int(...) 자체가 아니라 이미 int 타입인 값을 RESP Integer(:123\r\n) 형식으로 감싼다.
            # encode(ENCODING)는 파이썬 문자열을 네트워크 전송 가능한 bytes로 바꾼다.
            return f":{value}\r\n".encode(ENCODING)
        if isinstance(value, str):
            # startswith(...)는 문자열 메서드다.
            # 현재 프로젝트 규약상 "ERR "로 시작하는 문자열은 RESP Error(-ERR ...)로 내려보낸다.
            if value.startswith("ERR "):
                return f"-{value}\r\n".encode(ENCODING)
            # Redis에서 PONG/OK 같은 상태 응답은 bulk string이 아니라 simple string으로 보내는 편이 표준적이다.
            if value in {"OK", "PONG", "BYE"}:
                return f"+{value}\r\n".encode(ENCODING)
            return self._encode_bulk_string(value)
        if isinstance(value, list):
            # list 응답은 LRANGE 같은 멀티 벌크 응답을 표현할 수 있으므로 재귀적으로 배열 인코딩한다.
            return self._encode_array(value)
        # type(value)는 실제 런타임 타입을 얻는 내장 함수이고, !r는 repr(...) 형식으로 에러 메시지를 더 정확하게 보여 준다.
        raise TypeError(f"Unsupported RESP value type: {type(value)!r}")

    def _encode_array(self, values: list[Any]) -> bytes:
        # b"".join(...)의 join()은 bytes 시퀀스를 한 덩어리로 이어 붙이는 메서드다.
        # 제너레이터 표현식(self._encode_value(value) for value in values)은 각 원소를 순회하며 RESP bytes로 바꾼다.
        encoded_items = b"".join(self._encode_value(value) for value in values)
        # len(values)의 len()은 배열 원소 개수를 구해서 RESP 배열 헤더(*<count>\r\n)에 넣는다.
        return f"*{len(values)}\r\n".encode(ENCODING) + encoded_items

    def _encode_bulk_string(self, value: str) -> bytes:
        # 문자열 길이는 "문자 수"가 아니라 전송될 "바이트 수" 기준이어야 하므로 먼저 encode() 결과를 만든다.
        encoded = value.encode(ENCODING)
        # len(encoded)는 bytes 길이를 계산한다.
        # 마지막에 + CRLF를 붙여서 bulk string payload 끝을 RESP 규약대로 닫는다.
        return f"${len(encoded)}\r\n".encode(ENCODING) + encoded + CRLF

    def _decode_value(self, stream: BinaryIO) -> Any:
        # read(1)의 read()는 스트림에서 정확히 1바이트를 읽는다.
        # RESP는 첫 1바이트(prefix)로 타입을 구분하므로 가장 먼저 prefix를 읽는다.
        prefix = stream.read(1)
        # not prefix는 EOF 등으로 빈 bytes(b"")를 읽은 경우를 잡는다.
        if not prefix:
            raise ValueError("Missing RESP type prefix")

        if prefix == b"+":
            # Simple String은 한 줄을 읽고 bytes -> str decode()만 하면 된다.
            return self._readline(stream).decode(ENCODING)
        if prefix == b"-":
            # Error도 wire format은 한 줄이므로 동일하게 읽는다.
            return self._readline(stream).decode(ENCODING)
        if prefix == b":":
            # int(...)는 문자열 숫자를 파이썬 정수로 바꾸는 내장 함수다.
            return int(self._readline(stream).decode(ENCODING))
        if prefix == b"$":
            # Bulk String은 먼저 길이 줄을 읽고, 그 길이만큼 payload를 추가로 읽는다.
            length = int(self._readline(stream).decode(ENCODING))
            if length == -1:
                return None
            payload = stream.read(length)
            # len(payload)로 실제 읽힌 바이트 수를 검증해, 소켓이 중간에 끊긴 불완전 프레임을 막는다.
            if len(payload) != length:
                raise ValueError("Incomplete RESP bulk string payload")
            self._consume_crlf(stream)
            return payload.decode(ENCODING)
        if prefix == b"*":
            # RESP Array도 먼저 원소 개수를 읽는다.
            length = int(self._readline(stream).decode(ENCODING))
            if length == -1:
                return None
            # range(length)의 range()는 0부터 length-1까지 반복 횟수만 제공한다.
            # 각 원소 타입은 제각각일 수 있으므로 _decode_value()를 재귀 호출해서 하나씩 읽는다.
            return [self._decode_value(stream) for _ in range(length)]
        raise ValueError(f"Unsupported RESP type prefix: {prefix!r}")

    def _readline(self, stream: BinaryIO) -> bytes:
        # readline()은 CRLF가 나올 때까지 한 줄을 읽는다.
        line = stream.readline()
        # endswith(...)는 bytes 메서드로, 읽은 줄이 RESP 규약의 CRLF로 끝나는지 확인한다.
        if not line.endswith(CRLF):
            raise ValueError("RESP line must end with CRLF")
        # 슬라이싱 line[:-2]는 마지막 CRLF 2바이트를 제거하고 순수 내용만 돌려준다.
        return line[:-2]

    def _consume_crlf(self, stream: BinaryIO) -> None:
        # Bulk String payload 뒤에는 별도의 CRLF가 하나 더 붙으므로 정확히 2바이트를 읽어 소비한다.
        suffix = stream.read(2)
        if suffix != CRLF:
            raise ValueError("RESP bulk string must end with CRLF")

    @staticmethod
    def _expect_string(value: Any) -> str:
        # 명령 배열은 ["SET", "key", "value"]처럼 문자열만 와야 하므로 타입을 강제한다.
        if not isinstance(value, str):
            raise ValueError("RESP command values must be strings")
        return value
