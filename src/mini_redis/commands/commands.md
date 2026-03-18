# Mini Redis Commands

이 문서는 현재 `CommandManager`에 등록된 주요 명령과 사용 예시를 정리한 문서입니다.

명령 이름은 실행 전에 모두 대문자로 정규화되므로 `ping`, `Ping`, `PING`는 동일하게 처리됩니다.

## Basic Commands

| Command | Syntax | Return | Description |
| --- | --- | --- | --- |
| `PING` | `PING` | `PONG` | 서버 상태를 확인하는 기본 헬스체크 명령입니다. |
| `HELP` | `HELP [command]` | 문자열 또는 문자열 목록 | 전체 명령 목록이나 특정 명령의 간단한 설명을 반환합니다. |
| `QUIT` | `QUIT` | `BYE` | 클라이언트 세션을 종료할 때 사용합니다. |
| `SET` | `SET <key> <value> [EX <seconds>] [TAGS <tag...>]` | `OK` | 값을 저장하고, 필요하면 TTL과 invalidation tag를 함께 설정합니다. |
| `GET` | `GET <key>` | `<value>` 또는 `None` | 값이 없거나 만료된 경우 `None`을 반환합니다. |
| `DELETE` | `DELETE <key>` | `1` 또는 `0` | 키를 삭제하면 `1`, 삭제할 키가 없으면 `0`을 반환합니다. |
| `EXISTS` | `EXISTS <key>` | `1` 또는 `0` | 키가 현재 존재하는지 확인합니다. |
| `INCR` | `INCR <key>` | 정수 또는 에러 문자열 | 정수 값을 1 증가시킵니다. 키가 없으면 `1`부터 시작합니다. |
| `MGET` | `MGET <key...>` | 값 목록 | 존재하지 않는 키는 `None`으로 반환합니다. |
| `KEYS` | `KEYS` | 키 목록 | 현재 살아 있는 키 목록을 반환합니다. |
| `DUMPALL` | `DUMPALL` | 문자열 목록 | 남아 있는 모든 키의 값, TTL, tag를 보기 쉬운 문자열로 반환합니다. |

## TTL Commands

| Command | Syntax | Return | Description |
| --- | --- | --- | --- |
| `EXPIRE` | `EXPIRE <key> <seconds>` | `1` 또는 `0` | 키가 존재하면 TTL을 설정하고 `1`을 반환합니다. |
| `TTL` | `TTL <key>` | 정수 | 남은 TTL을 초 단위로 반환합니다. TTL이 없으면 `-1`, 키가 없으면 `-2`입니다. |

## Invalidation Commands

| Command | Syntax | Return | Description |
| --- | --- | --- | --- |
| `INVALIDATE` | `INVALIDATE <tag>` | 삭제된 개수 | 해당 tag에 연결된 키들을 삭제합니다. |

## Persistence Commands

| Command | Syntax | Return | Description |
| --- | --- | --- | --- |
| `SAVE` | `SAVE` | 스냅샷 경로 | 즉시 RDB 스냅샷을 저장합니다. |
| `BGSAVE` | `BGSAVE` | 상태 딕셔너리 | 백그라운드 스냅샷 저장을 시작합니다. |
| `LOAD` | `LOAD` | `OK` 또는 에러 문자열 | 스냅샷 파일이 있으면 상태를 복구합니다. |
| `REWRITEAOF` | `REWRITEAOF` | AOF 경로 | 현재 상태 기준으로 AOF를 다시 생성합니다. |
| `BGREWRITEAOF` | `BGREWRITEAOF` | 상태 딕셔너리 | 백그라운드 AOF 재작성 작업을 시작합니다. |
| `REPAIRAOF` | `REPAIRAOF` | 상태 딕셔너리 | AOF 손상 여부를 검사하고 복구를 시도합니다. |
| `FLUSHDB` | `FLUSHDB` | 삭제된 개수 | 메모리상의 모든 key, TTL, invalidation metadata를 비웁니다. |

## Inspection And Diagnostics

이 섹션은 incremental rehashing과 storage 상태를 관찰하기 위한 명령입니다.

### Overview

| Command | Syntax | Return | Description |
| --- | --- | --- | --- |
| `INFO` | `INFO PERSISTENCE` | 문자열 | persistence 상태와 key 개수를 반환합니다. |
| `INFO` | `INFO MONGO` | 문자열 | Mongo 연결 상태와 메타데이터를 반환합니다. |
| `INSPECT` | `INSPECT STORAGE` | 문자열 | storage의 현재 요약 상태를 반환합니다. |
| `INSPECT` | `INSPECT STORAGE FULL` | 문자열 | storage 상태와 버킷/아이템 상세 정보를 반환합니다. |
| `INSPECT` | `INSPECT STORAGE RESET` | `OK` | 최근 진단 기록과 rehash 카운터를 초기화합니다. |
| `INSPECT` | `INSPECT STORAGE RUN <count>` | 문자열 | 임의 key를 `<count>`개 삽입하면서 요청별 상태를 출력합니다. |
| `INSPECT` | `INSPECT STORAGE UPDATE <count>` | 문자열 | `inspect:run:<index>` 키들을 `<count>`번 수정하면서 요청별 상태를 출력합니다. |
| `PROBE` | `PROBE SET <key> <value>` | 문자열 | 단일 삽입 요청 1회를 수행하고 처리 시간과 storage 상태를 출력합니다. |
| `PROBE` | `PROBE UPDATE <key> <value>` | 문자열 | 단일 수정 요청 1회를 수행하고 처리 시간과 storage 상태를 출력합니다. |
| `BENCHMARK` | `BENCHMARK REDIS|MONGO|HYBRID <count> [KEEP]` | 문자열 | Redis, Mongo, 혼합 경로의 실행 시간을 비교합니다. |

### Inspect Summary

`INSPECT STORAGE`는 현재 상태만 간단하게 보여줍니다.

출력 예시:

```text
# Storage
[table size: 128] [resizing: True] [keys: 100] [rehash table size: 256] [progress: 0.7344] [last request: 0.245 ms]
```

각 항목 의미:

- `table size`: 현재 활성 테이블 크기
- `resizing`: rehashing이 진행 중인지 여부
- `keys`: 현재 저장된 key 개수
- `rehash table size`: 새로 옮겨가는 대상 테이블 크기
- `progress`: rehash 진행률
- `last request`: 마지막 storage 연산 처리 시간

### Full Dump

`INSPECT STORAGE FULL`은 요약 정보 외에 실제 버킷 구조와 items를 함께 출력합니다.

테이블 내부 상태를 자세히 보고 싶을 때 사용합니다.

### Reset Diagnostics

`INSPECT STORAGE RESET`은 storage 내부 진단 기록만 초기화합니다.

- key/value 데이터는 지우지 않습니다
- 최근 latency 샘플, recent operations, rehash 카운터를 다시 측정하고 싶을 때 사용합니다

### Insert Probe Run

`INSPECT STORAGE RUN <count>`는 `inspect:run:0`, `inspect:run:1` 같은 임의 key를 자동으로 생성하면서 상태를 출력합니다.

출력 예시:

```text
# Storage Insert Run
[request: 0.393 ms (393.000 us)] [table size: 4] [resizing: True] size=4 rehash_capacity=8 progress=0.0 storage_set: 0.015 ms (15.200 us)
```

이 명령은 이런 상황을 확인할 때 유용합니다.

- 삽입이 늘어날 때 resizing이 언제 시작되는지
- 요청 처리 시간이 rehash 중에 증가하는지
- active table과 rehash table의 크기가 어떻게 변하는지

### Update Probe Run

`INSPECT STORAGE UPDATE <count>`는 기존 `inspect:run:<index>` 키를 다시 수정합니다.

이 명령은 보통 `RUN` 다음에 사용합니다.

예시:

```text
FLUSHDB
INSPECT STORAGE RESET
INSPECT STORAGE RUN 100
INSPECT STORAGE UPDATE 100
INSPECT STORAGE
```

이 흐름을 통해:

- 삽입 도중 시작된 resizing이
- 이후 수정 요청 동안 끝나는지
- request time이 resizing 전후에 얼마나 달라지는지

를 확인할 수 있습니다.

### Single Request Probe

`PROBE`는 한 번의 요청만 직접 관찰하고 싶을 때 사용합니다.

예시:

```text
PROBE SET demo:key hello
PROBE UPDATE demo:key hello-again
```

## Config Commands

| Command | Syntax | Return | Description |
| --- | --- | --- | --- |
| `CONFIG` | `CONFIG GET <key>` | 평탄한 리스트 또는 에러 문자열 | `CONFIG GET *`로 전체 설정을 조회할 수 있습니다. |
| `CONFIG` | `CONFIG SET <key> <value>` | `OK` 또는 에러 문자열 | 지원되는 persistence 설정 값을 변경합니다. |

### Supported `CONFIG` Keys

- `recovery_policy`
- `fsync_policy`
- `autosave_interval`
- `autorewrite_min_operations`

## Recommended Inspection Flow

rehashing을 보기 쉬운 기본 흐름은 아래와 같습니다.

```text
FLUSHDB
INSPECT STORAGE RESET
INSPECT STORAGE RUN 100
INSPECT STORAGE
INSPECT STORAGE UPDATE 100
INSPECT STORAGE
```

의도:

- `FLUSHDB`로 메모리 상태를 비웁니다
- `RESET`으로 이전 진단 기록을 지웁니다
- `RUN`으로 삽입 요청을 만들어 resizing을 유도합니다
- `UPDATE`로 기존 데이터를 수정하면서 resizing 종료 여부를 봅니다

## Additional Examples

### `SET`

```text
SET user:1 hello
SET session:1 ok EX 60
SET user:1:posts posts EX 60 TAGS user:1 feed
SET user:1:profile profile TAGS user:1
```

### `INFO`

```text
INFO PERSISTENCE
INFO MONGO
```

### `HELP`

```text
HELP
HELP SET
HELP DUMPALL
```

## Error Notes

- 대부분의 명령은 인자 개수가 맞지 않으면 `ERR wrong number of arguments for '<COMMAND>'`를 반환합니다.
- 정수 인자를 파싱하지 못하면 `ERR value is not an integer or out of range`를 반환합니다.
- `SET`, `CONFIG`, `INSPECT`, `PROBE`의 잘못된 옵션 조합은 `ERR syntax error`를 반환할 수 있습니다.
- 등록되지 않은 명령은 `ERR unknown command '<COMMAND>'`로 처리됩니다.
