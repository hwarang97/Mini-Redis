# RESP.md

## RESP란 무엇인가

RESP는 `REdis Serialization Protocol`의 약자입니다. Redis가 클라이언트와 서버 사이에서 명령과 응답을 주고받을 때 사용하는 표준 프로토콜입니다.

TCP는 단순히 바이트를 순서대로 흘려 보내는 통신 방식이라서, "여기부터 한 명령", "여기까지 한 응답" 같은 경계를 스스로 알려주지 않습니다. 그래서 Redis는 RESP를 사용해 데이터의 타입, 길이, 끝나는 위치를 명확하게 표시합니다.

이 프로젝트에서도 RESP는 같은 역할을 합니다.

- CLI가 입력한 명령을 서버가 이해할 수 있는 네트워크 데이터로 바꿉니다.
- 서버 실행 결과를 다시 클라이언트가 읽을 수 있는 응답 형식으로 바꿉니다.
- 멀티라인 데이터나 배열 응답도 안전하게 구분할 수 있게 해 줍니다.

즉, RESP는 "사람이 입력한 명령"과 "TCP로 전달되는 바이트 데이터" 사이를 연결하는 공통 언어입니다.

## 왜 Redis는 RESP를 쓰는가

RESP는 Redis 같은 키-값 서버에 잘 맞는 특징이 있습니다.

1. 단순합니다.
클라이언트와 서버가 구현하기 어렵지 않습니다. 타입 prefix와 길이 정보만 이해하면 안정적으로 파싱할 수 있습니다.

2. 경계가 분명합니다.
Bulk String은 길이를 먼저 보내고, 줄 단위 데이터는 CRLF로 끝을 표시하므로 데이터가 여러 줄이더라도 안전하게 읽을 수 있습니다.

3. 타입 표현이 명확합니다.
문자열, 정수, nil, 배열 같은 Redis 응답을 한 규칙 안에서 일관되게 표현할 수 있습니다.

4. Redis 생태계와 잘 맞습니다.
Redis 명령은 보통 `["SET", "key", "value"]` 같은 배열 형태로 표현하기 쉬운데, RESP Array가 바로 이 구조에 잘 맞습니다.

## 이 프로젝트에서 RESP의 위치

프로젝트의 핵심 흐름은 아래와 같습니다.

```text
CLI Client
  -> RespCodec.encode_command()
  -> TCP Client
  -> TCP Server
  -> RespCodec.decode_command_stream()
  -> CommandManager.execute()
  -> RespCodec.encode_response()
  -> TCP Client
  -> RespCodec.decode_response_stream()
  -> CLI 출력
```

여기서 중요한 경계는 다음과 같습니다.

- CLI는 입력과 출력만 담당합니다.
- `RespCodec`은 RESP 직렬화와 역직렬화만 담당합니다.
- `TCPClient`, `TCPServer`는 바이트를 주고받는 transport만 담당합니다.
- 서버 실행 진입점은 반드시 `CommandManager`입니다.

즉, RESP 관련 규칙은 `protocol/resp.py` 안에 모으고, 다른 계층은 그 codec을 호출만 하는 구조입니다.

## RESP 기본 타입 정리

현재 `resp.py`에서 다루는 주요 RESP 타입은 아래와 같습니다.

### 1. Simple String

형식:

```text
+OK\r\n
```

용도:

- 짧고 단순한 성공 메시지

이 프로젝트에서는 응답 문자열이 일반 문자열일 때 최종적으로 Bulk String으로 인코딩하는 경우가 많지만, RESP 자체 관점에서는 이런 타입이 존재합니다.

### 2. Error

형식:

```text
-ERR something went wrong\r\n
```

용도:

- 오류 메시지 전달

현재 구현에서는 문자열이 `"ERR "`로 시작하면 Error 타입으로 인코딩합니다.

### 3. Integer

형식:

```text
:10\r\n
```

용도:

- 카운터 값
- 존재 여부 개수
- 증가/감소 결과

현재 구현에서는 `int`와 `bool`을 정수 계열 RESP로 보냅니다. `bool`은 `True -> 1`, `False -> 0`으로 바뀝니다.

### 4. Bulk String

형식:

```text
$5\r\nhello\r\n
```

의미:

- `$5`는 뒤에 오는 문자열 payload가 5바이트라는 뜻입니다.
- 그 뒤에 실제 데이터 `hello`
- 마지막 `\r\n`으로 payload 종료

용도:

- 일반 문자열 값
- 키 조회 결과
- 사람이 읽는 대부분의 텍스트 응답

### 5. Null Bulk String

형식:

```text
$-1\r\n
```

용도:

- 값이 없음
- Redis의 nil 개념 표현

이 프로젝트에서는 파이썬 `None`을 이 형식으로 보냅니다.

### 6. Array

형식:

```text
*3\r\n$3\r\nSET\r\n$3\r\nkey\r\n$5\r\nvalue\r\n
```

의미:

- `*3`은 배열 원소가 3개라는 뜻입니다.
- 각 원소는 다시 자기 타입 규칙대로 인코딩됩니다.

용도:

- 명령 전달
- 여러 값 반환
- `MGET`, `KEYS` 같은 리스트 응답

이 프로젝트에서 클라이언트 명령은 RESP Array로 보내는 것이 핵심입니다.

## 현재 구현에서 명령이 인코딩되는 방식

`encode_command()`는 내부 명령 객체를 아래 구조라고 가정합니다.

```python
{
    "name": "SET",
    "args": ["user:1", "hello"]
}
```

이 값을 RESP Array로 바꾸면 논리적으로는 아래와 같습니다.

```text
["SET", "user:1", "hello"]
```

그리고 wire format은 다음처럼 됩니다.

```text
*3\r\n
$3\r\n
SET\r\n
$6\r\n
user:1\r\n
$5\r\n
hello\r\n
```

이 방식의 장점은 명령명과 인자가 배열의 각 원소로 분리되어 있어서, 공백이나 줄바꿈이 들어 있는 문자열도 길이 기반으로 정확하게 전달할 수 있다는 점입니다.

## 현재 구현에서 응답이 인코딩되는 방식

`encode_response()`는 파이썬 값을 받아서 타입별로 RESP로 바꿉니다.

### 문자열

```python
"hello"
```

결과:

```text
$5\r\nhello\r\n
```

### 정수

```python
10
```

결과:

```text
:10\r\n
```

### 없음

```python
None
```

결과:

```text
$-1\r\n
```

### 배열

```python
["a", "b", None, 3]
```

결과:

- RESP Array로 인코딩
- 각 원소는 재귀적으로 다시 인코딩

### 오류 문자열

```python
"ERR wrong type"
```

결과:

```text
-ERR wrong type\r\n
```

## `resp.py`의 주요 메서드 설명

### `encode_command(command)`

역할:

- 명령 객체를 RESP Array bytes로 바꿉니다.

핵심 포인트:

- 명령명을 `upper()`로 대문자 통일
- `["COMMAND", *args]` 구조 생성
- `_encode_array()`에 위임

### `decode_command(payload)`

역할:

- bytes 전체를 받아서 명령 객체로 복원합니다.

핵심 포인트:

- `BytesIO`로 감싸서 스트림처럼 읽음
- 실제 파싱은 `decode_command_stream()` 재사용

### `decode_command_stream(stream)`

역할:

- 소켓 스트림에서 RESP 명령 프레임 1개를 읽어서 `Command` 형태로 바꿉니다.

핵심 포인트:

- `_decode_value()`로 공통 RESP 파싱
- 결과가 비어 있지 않은 리스트인지 검사
- 첫 원소는 명령명, 나머지는 인자 문자열로 강제

이 메서드가 중요한 이유는 TCP 서버에서 한 줄만 읽는 방식이 아니라, 멀티라인 RESP 프레임 전체를 안전하게 읽을 수 있게 해 주기 때문입니다.

### `encode_response(value)`

역할:

- 서버 실행 결과를 RESP 응답으로 바꿉니다.

핵심 포인트:

- 문자열, 정수, 배열, `None` 등을 타입별로 분기
- `_encode_value()`에 위임

### `decode_response(payload)` / `decode_response_stream(stream)`

역할:

- RESP 응답 bytes를 다시 파이썬 값으로 복원합니다.

차이:

- `decode_response()`는 bytes 전체를 가지고 있을 때 사용
- `decode_response_stream()`은 소켓 스트림처럼 순차 읽기 상황에서 사용

### `format_for_display(value)`

역할:

- 디코딩된 응답을 CLI에서 사람이 보기 좋은 문자열로 바꿉니다.

예:

- `None` -> `(nil)`
- 빈 리스트 -> `(empty list)`
- 리스트 -> `1) item`, `2) item` 형식

이 메서드는 RESP 파싱 자체가 아니라, CLI 표시를 위한 후처리입니다.

## 내부 헬퍼 메서드 설명

### `_encode_value(value)`

입력 타입에 따라 적절한 RESP 타입으로 변환합니다.

- `None` -> Null Bulk String
- `bool` -> Integer
- `int` -> Integer
- `str` -> Error 또는 Bulk String
- `list` -> Array

여기서 `bool`을 `int`보다 먼저 검사하는 이유는 파이썬에서 `bool`이 `int`의 하위 타입이기 때문입니다.

### `_encode_array(values)`

배열 전체를 RESP Array 형식으로 만듭니다.

과정:

1. 각 원소를 `_encode_value()`로 인코딩
2. 모두 이어 붙임
3. 앞에 `*원소개수\r\n` 헤더 추가

### `_encode_bulk_string(value)`

문자열을 Bulk String 형식으로 바꿉니다.

주의점:

- 길이는 문자 수가 아니라 `encode()` 후 바이트 수 기준이어야 합니다.
- 한글처럼 멀티바이트 문자가 있을 수 있기 때문입니다.

### `_decode_value(stream)`

RESP 파싱의 중심 메서드입니다.

과정:

1. prefix 1바이트 읽기
2. prefix에 따라 분기
3. 필요한 길이나 줄 정보를 추가로 읽기
4. 파이썬 값으로 복원

지원 분기:

- `+` Simple String
- `-` Error
- `:` Integer
- `$` Bulk String
- `*` Array

Array의 경우 각 원소를 다시 `_decode_value()`로 읽기 때문에 재귀적으로 중첩 구조도 처리할 수 있습니다.

### `_readline(stream)`

한 줄을 읽고, 마지막이 반드시 `CRLF`인지 검사합니다.

이 검사가 필요한 이유:

- RESP는 줄 끝 규칙이 엄격해야 안정적으로 파싱할 수 있습니다.
- 중간에 잘린 프레임이나 잘못된 포맷을 빨리 감지할 수 있습니다.

### `_consume_crlf(stream)`

Bulk String payload 뒤에 따라오는 `CRLF` 두 바이트를 소비합니다.

Bulk String은

```text
$길이\r\n
실제데이터\r\n
```

형태라서 payload를 길이만큼 읽은 뒤, 마지막 `\r\n`도 별도로 제거해야 합니다.

### `_expect_string(value)`

명령 배열의 각 원소가 문자열인지 확인합니다.

명령은 아래처럼 해석되는 것이 계약입니다.

```python
["SET", "key", "value"]
```

따라서 숫자나 리스트 같은 값이 명령 원소로 들어오면 `ValueError`를 발생시켜 잘못된 입력을 빠르게 막습니다.

## 스트림 기반 파싱이 중요한 이유

이번 RESP 구현에서 중요한 변화 중 하나는 "한 줄 읽기"에서 "스트림 기반 RESP 프레임 읽기"로 바뀐 점입니다.

예를 들어 명령 하나가 다음처럼 여러 줄에 걸쳐 올 수 있습니다.

```text
*3\r\n
$3\r\n
SET\r\n
$3\r\n
key\r\n
$5\r\n
value\r\n
```

이 데이터는 한 줄만 읽어서는 완성된 명령이 아닙니다.

그래서 서버는:

- `readline()` 한 번만 읽는 방식이 아니라
- `decode_command_stream()`으로 필요한 만큼 계속 읽어서
- 명령 전체 프레임이 끝날 때까지 파싱해야 합니다.

클라이언트 쪽 응답도 마찬가지입니다. 응답이 Bulk String이나 Array라면 여러 번 읽어야 할 수 있으므로 `decode_response_stream()`이 필요합니다.

## 이 문서 기준 사용 예시

### 명령 인코딩

```python
codec = RespCodec()
payload = codec.encode_command({"name": "GET", "args": ["user:1"]})
```

### 응답 디코딩

```python
codec = RespCodec()
value = codec.decode_response(payload)
```

### 소켓 스트림에서 바로 응답 읽기

```python
with conn.makefile("rb") as stream:
    value = codec.decode_response_stream(stream)
```

## 경계 관점에서 꼭 지켜야 할 점

이 프로젝트 구조에서는 아래 규칙이 중요합니다.

- RESP 포맷 처리 로직은 `RespCodec`에 둡니다.
- TCP 서버는 RESP를 해석한 뒤 `CommandManager`에만 전달합니다.
- 핸들러나 `Redis` 내부에 RESP 문법을 섞지 않습니다.
- CLI는 사람이 보기 좋은 출력만 책임지고, wire format 규칙은 직접 알지 않도록 유지합니다.

이렇게 해야 각 계층의 책임이 섞이지 않고, 다른 팀원이 명령 처리 로직이나 storage를 수정하더라도 네트워크 프로토콜 계층과 충돌이 줄어듭니다.
