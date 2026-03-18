# Mini Redis

Mini Redis는 Redis의 핵심 동작을 Python으로 재구성한 미니 서버 프로젝트입니다.
기본적인 Key-Value 저장소를 넘어 RESP 프로토콜, TCP 통신, TTL, 태그 기반 invalidation,
AOF/RDB 스타일 persistence, 복구 정책, storage inspection과 benchmarking까지 포함해
서버 내부 구조를 계층적으로 구현했습니다.

## 1. Overview

### 목표

- Redis의 핵심 동작을 직접 구현하며 내부 구조를 이해한다.
- CLI, Network, Protocol, Command Routing, Engine, Storage를 분리된 계층으로 설계한다.
- 단순 CRUD를 넘어서 TTL, persistence, recovery, diagnostics까지 포함한 서버를 만든다.

### 핵심 키워드

- `RESP`
- `TCP Server / Client`
- `CommandManager`
- `CommandQueue`
- `TTL`
- `Tag-based Invalidation`
- `AOF / Snapshot`
- `Recovery Policy`
- `Incremental Rehashing`

## 2. Features At A Glance

| 구분 | 구현 내용 |
| --- | --- |
| Client UX | `mini-redis-cli`, ASCII 배너, 응답 포맷팅, timing 표시 |
| Protocol | RESP 인코딩/디코딩, 멀티라인 프레임 처리 |
| Network | TCP 서버/클라이언트 구현, 서버는 지속 연결 처리, 기본 CLI 클라이언트는 명령마다 새 연결 사용 |
| Command Layer | 명령 정규화, FIFO 실행, 핸들러 기반 라우팅 |
| Core Data | `SET`, `GET`, `MGET`, `DELETE`, `EXISTS`, `INCR`, `KEYS`, `DUMPALL` |
| Expiration | `EXPIRE`, `TTL`, 만료 key 정리 |
| Invalidation | `TAGS`, `INVALIDATE <tag>` |
| Persistence | `SAVE`, `LOAD`, `BGSAVE`, `REWRITEAOF`, `BGREWRITEAOF`, `REPAIRAOF`, `FLUSHDB` |
| Diagnostics | `INSPECT STORAGE`, `PROBE`, storage 상태/latency/rehash 진행도 관찰 |
| Benchmark | `BENCHMARK REDIS|MONGO|HYBRID` |
| Runtime Config | `CONFIG GET`, `CONFIG SET` |
| Observability | `INFO PERSISTENCE`, `INFO MONGO` |
| Testing | CLI, RESP, TCP, Storage, TTL, Persistence, Recovery, Diagnostics, Mongo 경계 테스트 |

## 3. Distinctive Features

이 프로젝트의 특징은 Redis 명령을 흉내내는 데서 끝나지 않고, 내부 동작과 운영 상태를
관찰할 수 있는 기능들을 함께 구현했다는 점입니다.

| 기능 | 설명 |
| --- | --- |
| Tag-based Invalidation | `SET ... TAGS ...` 와 `INVALIDATE <tag>` 로 관련 key를 묶어서 제거할 수 있습니다. |
| Observable Persistence | `INFO PERSISTENCE` 로 snapshot, AOF, metadata, background task 상태를 확인할 수 있습니다. |
| Recovery Policies | `best-effort`, `snapshot-first`, `aof-only`, `strict` 복구 정책을 지원합니다. |
| Repairable AOF | `REPAIRAOF` 로 손상된 AOF tail을 복구할 수 있습니다. |
| FIFO Command Queue | `CommandManager`가 동시 요청을 FIFO 순서로 직렬 실행합니다. |
| Incremental Rehash Storage | 내부 해시 테이블이 incremental rehashing 방식으로 동작합니다. |
| Storage Inspection | `INSPECT STORAGE`, `PROBE` 로 rehash 진행도와 요청 latency를 관찰할 수 있습니다. |
| Benchmark Modes | `BENCHMARK REDIS`, `BENCHMARK MONGO`, `BENCHMARK HYBRID` 로 백엔드별 쓰기 비용을 비교할 수 있습니다. |
| Debug-friendly Dump | `DUMPALL` 이 key, value, ttl, tags를 함께 보여줍니다. |
| CLI Local Helpers | `.help`, `.demo`, `.clear`, `.exit`, `WATCH`, `LIVESET` 같은 로컬 helper를 제공합니다. |

## 4. Architecture

![Mini Redis Architecture](docs/architecture.png)

### 역할 분리

- CLI는 입력과 출력 UX를 담당합니다.
- RESP Codec은 명령과 응답을 네트워크 바이트 포맷으로 변환합니다.
- TCP 계층은 transport만 담당합니다.
- `CommandManager`는 명령 정규화와 실행 순서를 담당합니다.
- `CommandQueue`는 동시 요청을 FIFO 순서로 직렬화합니다.
- Redis Engine은 비즈니스 로직을 수행합니다.
- 각 Manager는 storage, ttl, invalidation, persistence 역할을 분리해서 담당합니다.

### 요청 처리 흐름

1. 사용자가 CLI에 명령을 입력합니다.
2. CLI Parser가 입력을 명령 형식으로 정리합니다.
3. Client RespCodec이 명령을 RESP 포맷으로 인코딩합니다.
4. TCP Client가 서버로 요청을 전송합니다.
5. TCP Server와 Server RespCodec이 요청을 해석합니다.
6. `CommandQueue`가 명령 실행 순서를 제어합니다.
7. Mini Redis Engine이 각 하위 매니저에 작업을 위임합니다.
8. 실행 결과는 다시 RESP 응답으로 인코딩되어 CLI로 돌아옵니다.
9. CLI Renderer가 결과를 사람이 읽기 쉬운 형태로 출력합니다.

## 5. Core Components

### 5-1. Command Flow

1. 사용자가 CLI에서 명령을 입력합니다.
2. 명령은 RESP 배열 형식으로 인코딩됩니다.
3. TCP 서버가 명령을 수신하고 `CommandManager`에 전달합니다.
4. `CommandManager`는 명령을 정규화한 뒤 `CommandQueue`에 전달합니다.
5. `CommandQueue`는 FIFO 순서로 하나씩 실행합니다.
6. Redis Engine이 실제 로직을 수행합니다.
7. 결과는 RESP 응답으로 인코딩되어 클라이언트로 반환됩니다.

### 5-2. Command Queue And Bottleneck Handling

Mini Redis는 여러 요청이 동시에 들어오더라도 공유 상태를 안전하게 유지하기 위해
모든 명령 실행을 `CommandQueue`를 통해 직렬화합니다.

- 각 요청은 queue에 ticket 형태로 들어갑니다.
- queue의 맨 앞 요청만 실행 권한을 가집니다.
- 나머지 요청은 대기 상태로 유지됩니다.
- 현재 실행이 끝나면 다음 요청이 FIFO 순서로 실행됩니다.

이 구조는 병목을 없애기보다는, 병목을 예측 가능하고 안전한 대기열로 바꾸는 방식입니다.

#### 장점

- 여러 스레드가 storage, ttl, persistence, invalidation 상태를 동시에 변경하지 않도록 막습니다.
- race condition 대신 FIFO 순서의 일관된 실행 흐름을 보장합니다.
- 명령 실행 순서를 추적하기 쉽고 디버깅이 단순합니다.
- `queued_commands`, `active_command`, `processed_commands` 같은 상태를 확인할 수 있습니다.

#### Trade-off

- 앞선 명령이 오래 걸리면 뒤의 명령도 함께 대기하게 됩니다.
- 즉, throughput 최적화보다는 데이터 정합성과 예측 가능한 실행 순서를 우선한 구조입니다.

### 5-3. Storage

- in-memory Key-Value 저장소입니다.
- 내부 해시 테이블은 incremental rehashing 방식으로 확장됩니다.
- `KEYS`, `DUMPALL`, `MGET` 등 조회 명령을 지원합니다.
- `INSPECT STORAGE` 를 통해 현재 테이블 크기, rehash 상태, 최근 요청 시간을 볼 수 있습니다.

### 5-4. TTL

- `EXPIRE <key> <seconds>` 로 만료 시간을 설정합니다.
- `TTL <key>` 로 남은 시간을 조회합니다.
- 조회나 목록 출력 전에 만료된 key를 자동 정리합니다.

### 5-5. Tag-based Invalidation

- `SET ... TAGS <tag> ...` 로 key를 태그에 연결할 수 있습니다.
- `INVALIDATE <tag>` 는 같은 태그에 속한 key를 한 번에 제거합니다.
- key 삭제, 만료, restore 시에도 태그 인덱스를 함께 정리합니다.

### 5-6. Inspection And Diagnostics

Storage 내부 상태와 rehash 진행도를 관찰하기 위한 기능입니다.

- `INSPECT STORAGE`
  - 현재 storage 상태를 한 줄 요약으로 출력합니다.
- `INSPECT STORAGE FULL`
  - bucket layout과 item map까지 포함한 상세 상태를 출력합니다.
- `INSPECT STORAGE RESET`
  - 최근 진단 기록과 rehash 카운터를 초기화합니다.
- `INSPECT STORAGE RUN <count>`
  - synthetic insert를 연속 실행하며 요청별 상태를 출력합니다.
- `INSPECT STORAGE UPDATE <count>`
  - 기존 synthetic key들을 다시 수정하며 요청별 상태를 출력합니다.
- `PROBE SET <key> <value>`
  - 단일 삽입 요청 1회를 수행하고 latency와 storage 상태를 반환합니다.
- `PROBE UPDATE <key> <value>`
  - 단일 수정 요청 1회를 수행하고 latency와 storage 상태를 반환합니다.

### 5-7. Benchmark

서로 다른 저장 경로의 쓰기 비용을 비교하기 위한 기능입니다.

- `BENCHMARK REDIS <count> [KEEP]`
  - in-memory Redis 쓰기 성능을 측정합니다.
- `BENCHMARK MONGO <count> [KEEP]`
  - Mongo 쓰기 성능을 측정합니다.
- `BENCHMARK HYBRID <count> [KEEP]`
  - Redis와 Mongo에 동시에 쓰는 경로를 측정합니다.

응답에는 elapsed time, throughput, backend-specific details가 포함됩니다.

### 5-8. Persistence

- `SAVE`, `BGSAVE` 로 snapshot을 저장합니다.
- `REWRITEAOF`, `BGREWRITEAOF` 로 현재 live state 기준 AOF를 다시 생성합니다.
- `LOAD` 로 snapshot을 다시 읽어 상태를 복원합니다.
- `REPAIRAOF` 로 손상된 AOF tail을 잘라냅니다.
- `FLUSHDB` 로 메모리 상태와 관련 메타데이터를 초기화합니다.

### 5-9. Recovery

지원하는 복구 정책:

- `best-effort`
- `snapshot-first`
- `aof-only`
- `strict`

기본 복구 흐름:

1. snapshot이 있으면 먼저 로드합니다.
2. snapshot 이후의 AOF tail만 replay합니다.
3. corruption 정책에 따라 손상된 tail을 무시하거나 기동을 실패 처리합니다.

### 5-10. Observability

- `INFO PERSISTENCE`
  - snapshot / AOF / metadata 상태
  - background task 상태
  - recovery 결과
  - key count
- `INFO MONGO`
  - Mongo 연결 여부와 관련 메타데이터
- `CONFIG GET`, `CONFIG SET`
  - `recovery_policy`
  - `fsync_policy`
  - `autosave_interval`
  - `autorewrite_min_operations`

### 5-11. CLI UX

- CLI 시작 시 ASCII 배너와 연결 상태를 표시합니다.
- 응답 타입별 포맷팅과 server time / round-trip time을 출력합니다.
- 다음 로컬 helper를 제공합니다.

```text
.help
.demo
.clear
.exit
WATCH <interval> <count> <command...>
LIVESET <count> [interval] [key_prefix]
```

이 helper들은 서버 명령이 아니라 CLI 내부에서 처리됩니다.

## 6. Usage Examples

### 기본 명령

```text
PING
SET user:1 hello
GET user:1
INCR visits
MGET user:1 visits missing:key
```

### TTL + Tags

```text
SET user:1:profile profile TAGS user:1 demo
SET user:1:session live EX 30 TAGS user:1 demo
TTL user:1:session
DUMPALL
```

### Storage Inspection

```text
FLUSHDB
INSPECT STORAGE RESET
INSPECT STORAGE RUN 20
INSPECT STORAGE
INSPECT STORAGE UPDATE 20
INSPECT STORAGE FULL
```

### Single Request Probe

```text
PROBE SET demo:key hello
PROBE UPDATE demo:key hello-again
```

### Benchmark

```text
BENCHMARK REDIS 1000 KEEP
BENCHMARK MONGO 1000
BENCHMARK HYBRID 1000
```

### Persistence

```text
SAVE
INFO PERSISTENCE
CONFIG SET autorewrite_min_operations 1
SET auto:key value
INFO PERSISTENCE
```

## 7. Supported Server Commands

```text
PING
HELP [command]
SET <key> <value> [EX <seconds>] [TAGS <tag> ...]
GET <key>
MGET <key> [key ...]
DELETE <key>
EXISTS <key>
INCR <key>
KEYS
DUMPALL
EXPIRE <key> <seconds>
TTL <key>
INVALIDATE <tag>
INSPECT STORAGE
INSPECT STORAGE FULL
INSPECT STORAGE RESET
INSPECT STORAGE RUN <count>
INSPECT STORAGE UPDATE <count>
PROBE SET <key> <value>
PROBE UPDATE <key> <value>
BENCHMARK REDIS|MONGO|HYBRID <count> [KEEP]
SAVE
BGSAVE
LOAD
REWRITEAOF
BGREWRITEAOF
REPAIRAOF
FLUSHDB
INFO PERSISTENCE
INFO MONGO
CONFIG GET <key>
CONFIG SET <key> <value>
QUIT
```

## 8. CLI Local Commands

다음 명령은 서버로 보내지지 않고 CLI 내부에서 처리됩니다.

| Command | Description |
| --- | --- |
| `.help` | 로컬 helper 목록을 출력합니다. |
| `.demo` | 추천 시연 시퀀스를 출력합니다. |
| `.clear` | 화면을 정리합니다. |
| `.exit` | 서버에 `QUIT`를 보내지 않고 CLI만 종료합니다. |
| `WATCH <interval> <count> <command...>` | 중첩 명령을 주기적으로 반복 실행합니다. |
| `LIVESET <count> [interval] [key_prefix]` | 연속적인 `PROBE SET` 요청을 자동 생성합니다. |

## 9. Testing

현재 테스트 범위:

- CLI parser / CLI output / WATCH / LIVESET
- RESP codec
- TCP round-trip / multiline RESP / persistent server connection
- FIFO command execution
- incremental rehash storage
- TTL
- command flow
- inspect / probe / benchmark
- persistence / restore / repair
- Mongo integration boundary

총 65개의 테스트 케이스가 존재합니다.

## 10. Current Limits

- Mongo 관련 모듈과 `INFO MONGO`는 구현되어 있습니다.
- `BENCHMARK MONGO`, `BENCHMARK HYBRID` 는 Mongo integration이 활성화되어 있어야 동작합니다.
- 하지만 현재 기본 Redis command flow에서 `SET`/`DELETE`가 자동으로 Mongo write-through 되지는 않습니다.
- 따라서 Mongo는 현재 기준으로는 확장 가능한 연동 경계로 보는 것이 가장 정확합니다.

## 11. Run

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
mini-redis-server
```

다른 터미널에서:

```powershell
.venv\Scripts\Activate.ps1
mini-redis-cli
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
mini-redis-server
```

다른 터미널에서:

```bash
source .venv/bin/activate
mini-redis-cli
```

## 12. Data Files

실행 중 생성될 수 있는 파일:

- `data/appendonly.aof`
- `data/dump.rdb.json`
- `data/persistence.meta.json`
