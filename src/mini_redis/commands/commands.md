# Mini Redis Commands

이 문서는 현재 `CommandManager`에 등록된 커맨드를 정리한 문서입니다.

커맨드 이름은 실행 전에 모두 대문자로 정규화되므로 `ping`, `Ping`, `PING`는 동일하게 처리됩니다.

## 기본 커맨드

| 커맨드 | 문법 | 반환값 | 설명 |
| --- | --- | --- | --- |
| `PING` | `PING` | `PONG` | 서버 상태를 확인하는 기본 헬스체크 커맨드입니다. |
| `HELP` | `HELP [command]` | 문자열 또는 문자열 목록 | 전체 커맨드 도움말 목록이나 특정 커맨드 한 줄 설명을 반환합니다. |
| `QUIT` | `QUIT` | `BYE` | CLI 클라이언트를 종료할 때 사용합니다. |
| `SET` | `SET <key> <value> [EX <seconds>] [TAGS <tag...>]` | `OK` | TTL과 invalidation 태그를 선택적으로 함께 설정할 수 있습니다. |
| `GET` | `GET <key>` | `<value>` 또는 `None` | 키가 없거나 만료된 경우 `None`을 반환합니다. |
| `DELETE` | `DELETE <key>` | `1` 또는 `0` | 키를 삭제했으면 `1`, 없어서 삭제하지 못했으면 `0`을 반환합니다. |
| `EXISTS` | `EXISTS <key>` | `1` 또는 `0` | 현재 키가 존재하는지 여부를 반환합니다. |
| `INCR` | `INCR <key>` | 정수 또는 에러 문자열 | 키가 없으면 `1`부터 생성합니다. |
| `MGET` | `MGET <key...>` | 값 목록 | 존재하지 않는 키는 `None`으로 반환됩니다. |
| `KEYS` | `KEYS` | 키 목록 | 목록을 반환하기 전에 만료된 키를 먼저 정리합니다. |
| `DUMPALL` | `DUMPALL` | 문자열 목록 | 살아있는 모든 키의 값, TTL, 태그를 사람이 읽기 쉬운 문자열로 반환합니다. |

## TTL 커맨드

| 커맨드 | 문법 | 반환값 | 설명 |
| --- | --- | --- | --- |
| `EXPIRE` | `EXPIRE <key> <seconds>` | `1` 또는 `0` | 키가 존재하지 않으면 `0`을 반환합니다. |
| `TTL` | `TTL <key>` | 정수 TTL | 남은 초를 반환하며, TTL이 없으면 `-1`, 키가 없으면 `-2`를 반환합니다. |

## Invalidation 커맨드

| 커맨드 | 문법 | 반환값 | 설명 |
| --- | --- | --- | --- |
| `INVALIDATE` | `INVALIDATE <tag>` | 삭제된 키 개수 | 해당 태그에 연결된 키를 모두 제거하고, 제거된 개수를 반환합니다. |

## Persistence 커맨드

| 커맨드 | 문법 | 반환값 | 설명 |
| --- | --- | --- | --- |
| `SAVE` | `SAVE` | 스냅샷 경로 | 즉시 RDB 스타일 스냅샷을 저장합니다. |
| `BGSAVE` | `BGSAVE` | 상태 딕셔너리 | 백그라운드에서 스냅샷 저장을 시작합니다. |
| `LOAD` | `LOAD` | `OK` 또는 에러 문자열 | 스냅샷 파일이 있으면 로드합니다. |
| `REWRITEAOF` | `REWRITEAOF` | AOF 경로 | 현재 살아있는 데이터 기준으로 append-only 로그를 다시 생성합니다. |
| `BGREWRITEAOF` | `BGREWRITEAOF` | 상태 딕셔너리 | 백그라운드에서 AOF 재작성 작업을 시작합니다. |
| `REPAIRAOF` | `REPAIRAOF` | 결과 딕셔너리 | AOF 끝부분의 손상 여부를 검사하고 필요하면 잘라냅니다. |
| `FLUSHDB` | `FLUSHDB` | 삭제된 키 개수 | 모든 키, TTL 메타데이터, invalidation 메타데이터를 비웁니다. |

## 조회/설정 커맨드

| 커맨드 | 문법 | 반환값 | 설명 |
| --- | --- | --- | --- |
| `INFO` | `INFO PERSISTENCE` | 포맷된 문자열 | persistence 메타데이터, 키 개수, 복구 정책, 백그라운드 작업 상태를 포함합니다. |
| `INFO` | `INFO MONGO` | 딕셔너리 | Mongo 동기화 상태와 연결 메타데이터를 포함합니다. |
| `CONFIG` | `CONFIG GET <key>` | 평탄한 리스트 또는 에러 문자열 | `CONFIG GET *`를 사용하면 지원되는 런타임 설정 전체를 조회할 수 있습니다. |
| `CONFIG` | `CONFIG SET <key> <value>` | `OK` 또는 에러 문자열 | 지원되는 런타임 설정 값을 변경합니다. |

## 지원하는 `CONFIG` 키

- `recovery_policy`
- `fsync_policy`
- `autosave_interval`
- `autorewrite_min_operations`

## `SET` 예시

```text
SET user:1 hello
SET session:1 ok EX 60
SET user:1:posts posts EX 60 TAGS user:1 feed
SET user:1:profile profile TAGS user:1
```

## `INFO` 예시

```text
INFO PERSISTENCE
INFO MONGO
```

## `HELP` 예시

```text
HELP
HELP SET
HELP DUMPALL
```

## 에러 동작

- 대부분의 핸들러는 인자 개수가 맞지 않으면 `ERR wrong number of arguments for '<COMMAND>'`를 반환합니다.
- TTL 초처럼 숫자여야 하는 인자를 파싱하지 못하면 `ERR value is not an integer or out of range`를 반환합니다.
- `SET`과 `CONFIG`는 지원하지 않는 옵션 배치에 대해 `ERR syntax error`를 반환합니다.
- 등록되지 않은 커맨드는 `CommandManager`에서 `ERR unknown command '<COMMAND>'`로 거절됩니다.
