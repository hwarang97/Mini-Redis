# NETWORK.md

## 이 디렉터리의 역할

`network/`는 Mini Redis 프로젝트에서 TCP 통신만 담당하는 계층입니다.

현재 포함된 파일은 아래 두 개입니다.

- `tcp_client.py`
- `tcp_server.py`

이 계층의 핵심 책임은 단순합니다.

- 서버에 TCP 연결을 연다.
- RESP bytes를 주고받는다.
- 받은 데이터를 적절한 codec에 넘긴다.

반대로 이 계층이 하면 안 되는 일도 분명합니다.

- 명령의 의미를 직접 해석하면 안 됩니다.
- Redis 엔진을 직접 호출하면 안 됩니다.
- 응답 포맷 규칙을 여기저기 흩뿌리면 안 됩니다.

즉, `network/`는 transport 계층입니다. 실행은 `CommandManager`, 프로토콜 해석은 `RespCodec`이 맡습니다.

## 전체 연결 흐름

현재 구조의 연결 흐름은 아래처럼 보면 됩니다.

```text
CLI 입력
  -> TCPClient.send()
  -> RespCodec.encode_command()
  -> socket.create_connection()
  -> 서버 소켓 수신
  -> _RequestHandler.handle()
  -> RespCodec.decode_command_stream()
  -> CommandManager.execute()
  -> RespCodec.encode_response()
  -> 클라이언트 수신
  -> RespCodec.decode_response_stream()
  -> CLI 출력
```

핵심은 `network`가 "연결과 전달"만 하고, 실제 명령 실행은 서버 안의 `CommandManager`가 맡는다는 점입니다.

## `tcp_client.py` 설명

### 역할

`TCPClient`는 클라이언트 쪽 transport 담당 객체입니다.

하는 일:

1. 서버 주소로 TCP 연결 생성
2. 명령을 RESP bytes로 인코딩해 전송
3. 서버 응답을 스트림에서 읽어 디코딩
4. 파이썬 값으로 호출자에게 반환

### 생성 방법

기본 사용 예시는 아래와 같습니다.

```python
from mini_redis.network.tcp_client import TCPClient
from mini_redis.protocol.resp import RespCodec

codec = RespCodec()
client = TCPClient(host="127.0.0.1", port=6379, codec=codec)
```

생성자 인자:

- `host`: 접속할 서버 주소
- `port`: 접속할 서버 포트
- `codec`: RESP 직렬화/역직렬화를 담당할 `RespCodec`

### 사용 방법

```python
result = client.send({"name": "PING", "args": []})
```

또는:

```python
result = client.send({"name": "SET", "args": ["user:1", "hello"]})
```

반환값은 디코딩된 파이썬 값입니다.

예:

- `"OK"`
- `"hello"`
- `10`
- `None`
- `["a", "b"]`

### 내부 동작 순서

`send()` 안에서는 대략 아래 순서로 동작합니다.

1. `socket.create_connection((host, port))`
   서버로 TCP 연결을 엽니다.

2. `self._codec.encode_command(command)`
   명령 객체를 RESP Array bytes로 바꿉니다.

3. `conn.sendall(...)`
   인코딩된 bytes 전체를 서버로 보냅니다.

4. `conn.makefile("rb")`
   소켓을 바이너리 읽기 스트림처럼 감쌉니다.

5. `self._codec.decode_response_stream(stream)`
   응답 프레임 1개를 스트림에서 끝까지 읽어서 파이썬 값으로 복원합니다.

여기서 중요한 이유는 응답이 꼭 한 줄이 아닐 수 있기 때문입니다. Bulk String, Array, nil 응답은 길이 정보와 추가 줄을 읽어야 할 수 있어서 단순 `recv()` 루프보다 codec 중심 스트림 파싱이 더 안전합니다.

## `tcp_server.py` 설명

### 역할

`TCPServer`는 서버 쪽 transport 래퍼입니다.

하는 일:

- 소켓 서버를 띄운다.
- 요청마다 handler를 실행한다.
- 들어온 RESP 명령을 codec으로 해석한다.
- 해석한 명령을 `CommandManager`에 전달한다.
- 실행 결과를 다시 RESP로 인코딩해서 응답한다.

중요한 점:

- TCP 서버는 `Redis`를 직접 호출하지 않습니다.
- 실행 진입점은 반드시 `CommandManager`입니다.

### 생성 방법

```python
from mini_redis.bootstrap import build_command_manager
from mini_redis.network.tcp_server import TCPServer
from mini_redis.protocol.resp import RespCodec

manager = build_command_manager()
server = TCPServer(
    host="127.0.0.1",
    port=6379,
    manager=manager,
    codec=RespCodec(),
)
```

생성자 인자:

- `host`: 바인딩할 주소
- `port`: 리슨할 포트
- `manager`: 서버 실행 진입점인 `CommandManager`
- `codec`: RESP 해석용 `RespCodec`

### 실행 방법

```python
server.serve_forever()
```

종료:

```python
server.shutdown()
```

실제 엔트리포인트에서는 `try/finally`로 감싸서 종료 시 소켓이 정리되도록 사용하는 것이 좋습니다.

## 서버 내부 처리 흐름

서버의 실제 요청 처리는 `_RequestHandler.handle()`에서 시작됩니다.

동작 흐름:

1. `self.rfile`에서 요청 스트림을 읽음
2. `codec.decode_command_stream(self.rfile)`로 RESP 명령 파싱
3. `manager.execute(command)` 호출
4. 반환값을 `codec.encode_response(response)`로 인코딩
5. `self.wfile.write(...)`로 클라이언트에게 응답

이 흐름이 중요한 이유는 transport 계층과 실행 계층이 깔끔하게 분리되기 때문입니다.

### 왜 `decode_command_stream()`을 써야 하는가

예전처럼 "한 줄 읽기" 방식은 RESP에 맞지 않습니다.

예를 들어 아래 명령은 여러 줄입니다.

```text
*3\r\n
$3\r\n
SET\r\n
$3\r\n
key\r\n
$5\r\n
value\r\n
```

이 경우 첫 줄만 읽으면 아직 명령이 완성되지 않았습니다.

그래서 서버는:

- 첫 줄만 읽는 방식 대신
- 스트림 전체에서 필요한 만큼 계속 읽는 `decode_command_stream()`
- 을 사용해야 합니다.

이것이 RESP를 제대로 처리하는 핵심 포인트입니다.

## `ThreadedTCPServer`는 왜 필요한가

`tcp_server.py`에는 `socketserver.ThreadingTCPServer`를 상속한 `ThreadedTCPServer`가 있습니다.

역할:

- 각 연결 요청을 별도 스레드에서 처리
- 테스트나 로컬 실습 중 빠른 재시작 가능

설정:

```python
allow_reuse_address = True
```

이 옵션은 서버를 껐다가 바로 다시 켤 때 포트 재사용을 좀 더 수월하게 해 줍니다.

## 엔트리포인트에서의 실제 연결 방법

### 서버 시작

현재 [server_main.py](D:/jungleCamp/Projects/miniRedis/src/mini_redis/server_main.py)는 아래 흐름으로 서버를 시작합니다.

1. `build_command_manager()`로 `CommandManager` 생성
2. `RespCodec()` 생성
3. `TCPServer(host, port, manager, codec)` 생성
4. `serve_forever()` 실행

즉, 서버는 bootstrapping 단계에서 실행 엔진과 network transport를 연결해 주는 방식입니다.

### 클라이언트 시작

현재 [cli_main.py](D:/jungleCamp/Projects/miniRedis/src/mini_redis/cli_main.py)는 아래 흐름으로 동작합니다.

1. `RespCodec()` 생성
2. `TCPClient(host, port, codec)` 생성
3. `CLIClient(...).run()` 실행

즉, CLI는 명령 문자열을 읽고, 실제 네트워크 전송은 `TCPClient`, RESP 변환은 `RespCodec`에 위임합니다.

## 사용 예시

### 1. 서버 실행

프로젝트 엔트리포인트 기준:

```bash
mini-redis-server
```

또는 개발 중 직접 실행:

```bash
python -m mini_redis.server_main
```

### 2. 클라이언트 실행

```bash
mini-redis-cli
```

또는:

```bash
python -m mini_redis.cli_main
```

### 3. CLI에서 명령 입력

```text
PING
SET user:1 hello
GET user:1
MGET user:1 user:2
```

입력된 명령은 내부적으로:

- CLI 파싱
- RESP 인코딩
- TCP 전송
- 서버 실행
- RESP 응답 디코딩

순서를 거쳐 처리됩니다.

## 직접 코드에서 사용하는 예시

### 클라이언트로 요청 보내기

```python
from mini_redis.network.tcp_client import TCPClient
from mini_redis.protocol.resp import RespCodec

codec = RespCodec()
client = TCPClient("127.0.0.1", 6379, codec)

print(client.send({"name": "PING", "args": []}))
print(client.send({"name": "SET", "args": ["demo:key", "value"]}))
print(client.send({"name": "GET", "args": ["demo:key"]}))
```

### 서버 띄우기

```python
from mini_redis.bootstrap import build_command_manager
from mini_redis.network.tcp_server import TCPServer
from mini_redis.protocol.resp import RespCodec

manager = build_command_manager()
server = TCPServer("127.0.0.1", 6379, manager, RespCodec())

try:
    server.serve_forever()
finally:
    server.shutdown()
```

## 이 디렉터리에서 꼭 지켜야 할 구조 원칙

### 1. network는 transport만 담당

`network/`는 연결 생성, 읽기, 쓰기만 담당해야 합니다.

여기에 넣지 말아야 할 것:

- 명령별 인자 해석
- Redis 내부 상태 조작
- RESP 문법 자체 구현

### 2. RESP 처리 로직은 codec에 둔다

network 계층은 아래처럼만 사용해야 합니다.

- `encode_command()`
- `decode_command_stream()`
- `encode_response()`
- `decode_response_stream()`

즉, network는 RESP를 "사용"하지만, RESP 규칙을 "직접 구현"하지 않습니다.

### 3. 실행은 CommandManager를 통해서만

서버가 받은 명령은 반드시:

```python
response = self.manager.execute(command)
```

이 경로를 타야 합니다.

TCP 서버가 직접 `Redis`를 부르면 구조 경계가 무너지고, 명령 검증과 라우팅이 분산되어 유지보수가 어려워집니다.

## 연결 문제를 볼 때 체크할 포인트

네트워크 문제가 생기면 아래 순서로 확인하면 좋습니다.

1. 서버가 실제로 host/port에 바인딩되었는가
2. 클라이언트가 같은 host/port로 접속하는가
3. 명령이 RESP Array 형식으로 인코딩되는가
4. 서버가 `decode_command_stream()`으로 프레임 전체를 읽는가
5. 응답이 `encode_response()`로 정상 인코딩되는가
6. 클라이언트가 `decode_response_stream()`으로 끝까지 읽는가

특히 RESP는 멀티라인 프레임이 많아서, 한 줄만 읽는 방식으로는 정상 동작하지 않는 경우가 많습니다.

## 정리

`network/`는 이 프로젝트에서 "통신선" 역할을 합니다.

- `tcp_client.py`는 서버에 연결해서 명령을 보냅니다.
- `tcp_server.py`는 연결을 받아 명령을 `CommandManager`로 전달합니다.
- RESP 해석은 `RespCodec`이 맡습니다.
- 실제 비즈니스 실행은 `CommandManager`와 그 아래 핸들러가 맡습니다.

이 분리가 유지되어야 CLI, RESP, TCP, command routing, Redis 엔진이 서로 충돌하지 않고 안정적으로 확장됩니다.
