# INVALIDATION.md

## `invalidation/`의 역할

`invalidation/`은 태그 기반 캐시 무효화 정보를 관리하는 계층입니다.

이 프로젝트에서 invalidation은 "태그 하나에 연결된 여러 key를 한 번에 찾아 정리하는 기능"을 뜻합니다. 실제 key 삭제는 Redis 엔진이 담당하고, 이 디렉터리는 어떤 태그가 어떤 key들과 연결되어 있는지 빠르게 찾을 수 있게 인덱스를 유지하는 역할에 집중합니다.

현재 포함된 핵심 파일은 아래와 같습니다.

- `manager.py`

## 왜 별도 매니저가 필요한가

일반 key-value 저장만 있으면 `GET key`, `SET key value`처럼 key 기준으로 접근하면 됩니다. 하지만 invalidation은 반대 방향 조회가 필요합니다.

예를 들어:

- `user:1:profile`
- `user:1:posts`
- `user:1:settings`

이 세 key가 모두 `user:1` 태그를 갖고 있다면, `INVALIDATE user:1` 요청이 들어왔을 때 태그 하나만 보고 연결된 key들을 즉시 찾아야 합니다.

저장소 전체를 매번 전수 탐색하면 비효율적이기 때문에, `InvalidationManager`가 별도의 역방향 인덱스를 유지합니다.

## 핵심 자료구조

`InvalidationManager`는 두 개의 딕셔너리를 함께 유지합니다.

### 1. `_tag_map`

태그에서 key 집합으로 가는 인덱스입니다.

```python
{
    "user:1": {"user:1:profile", "user:1:posts"},
    "demo": {"user:1:profile", "feed:home"},
}
```

이 구조 덕분에 `INVALIDATE user:1` 같은 요청이 들어왔을 때 관련 key들을 바로 찾을 수 있습니다.

### 2. `_key_tags`

key에서 태그 집합으로 가는 역인덱스입니다.

```python
{
    "user:1:profile": {"user:1", "demo"},
    "feed:home": {"demo"},
}
```

이 구조는 key가 삭제되거나 TTL 만료로 사라질 때, 그 key가 속해 있던 모든 태그에서 흔적을 정리하는 데 필요합니다.

즉:

- `_tag_map`은 "태그로 key 찾기"
- `_key_tags`는 "key 제거 시 태그 정리하기"

를 담당합니다.

## 주요 메서드 설명

### `set_tags(key, tags)`

특정 key에 연결된 태그를 갱신합니다.

이 메서드는 단순히 태그를 추가만 하지 않고, 이전 상태와 새 상태를 비교해서:

- 제거된 태그는 인덱스에서 떼고
- 새로 추가된 태그는 인덱스에 붙이고
- 최종적으로 key의 태그 목록을 최신 상태로 맞춥니다.

빈 문자열이나 중복 태그는 정규화 과정에서 정리됩니다.

### `clear_key(key)`

key가 삭제되었을 때 해당 key가 속해 있던 모든 태그 연결을 제거합니다.

이 메서드가 없으면 `_tag_map` 안에 이미 없는 key가 남아서 stale state가 생길 수 있습니다.

### `invalidate(tag)`

주어진 태그에 연결된 key 목록을 반환하고, 동시에 invalidation 인덱스에서도 그 연결을 정리합니다.

중요한 점은 여기서 "실제 storage 삭제"를 하지 않는다는 점입니다. 이 메서드는 어떤 key들이 invalidation 대상인지 계산하고 인덱스를 정리하는 역할만 담당합니다.

실제 key 삭제는 이 결과를 받은 상위 계층이 처리합니다.

### `tags_for_key(key)`

특정 key가 현재 어떤 태그들을 갖고 있는지 조회합니다.

디버깅이나 상태 확인에 유용합니다.

### `export()`

현재 태그 인덱스를 snapshot 저장에 적합한 형태로 내보냅니다.

내부에서는 `set[str]`를 쓰지만, snapshot 직렬화에는 정렬된 `list[str]`가 더 안전하고 일관적입니다.

### `load_tag_map(values)`

snapshot에서 읽어온 태그 상태를 다시 메모리 인덱스로 복원합니다.

복원 시에는 기존 상태를 먼저 비운 뒤, `_tag_map`과 `_key_tags`를 함께 다시 구성해서 두 인덱스가 항상 같은 상태를 가리키게 만듭니다.

### `clear_all()`

전체 DB 초기화나 복원 작업 전에 invalidation 상태를 완전히 비울 때 사용합니다.

### `_detach(tag, key)`

내부 헬퍼 메서드입니다.

특정 태그 집합에서 key 하나를 제거하고, 그 태그에 더 이상 key가 남아 있지 않으면 태그 엔트리 자체도 삭제합니다. 덕분에 export 결과와 메모리 상태를 깔끔하게 유지할 수 있습니다.

## 명령 흐름에서의 위치

invalidation은 독립 기능처럼 보이지만, 실제로는 전체 명령 흐름 안에 들어 있습니다.

```text
CLI
  -> TCP Client
  -> TCP Server
  -> CommandManager
  -> Command Handler
  -> Redis 엔진
  -> InvalidationManager
```

중요한 경계는 아래와 같습니다.

- CLI는 invalidation 인덱스를 직접 만지지 않습니다.
- TCP 계층은 invalidation 규칙을 모릅니다.
- `CommandManager`는 명령 라우팅만 담당합니다.
- 실제 invalidation 정책 연결은 Redis 엔진과 핸들러 계층에서 일어납니다.
- `InvalidationManager`는 태그 인덱스 유지에만 집중합니다.

즉, 이 디렉터리는 "실행 진입점"이 아니라 "태그 관계를 관리하는 내부 컴포넌트"입니다.

## 언제 인덱스를 갱신해야 하나

태그 인덱스는 key 상태가 바뀌는 순간 함께 갱신되어야 합니다.

대표적인 경우:

- `SET ... TAGS ...`로 태그가 새로 지정될 때
- 기존 key의 태그 구성이 바뀔 때
- key가 `DELETE`로 삭제될 때
- key가 TTL 만료로 사라질 때
- `INVALIDATE tag`로 관련 key 묶음을 제거할 때
- `FLUSHDB` 또는 snapshot 복원으로 전체 상태가 갈아엎어질 때

이 중 하나라도 빠지면 `_tag_map`과 실제 storage 상태가 어긋날 수 있습니다.

## 설계 포인트

### 1. 저장소와 invalidation 책임 분리

`InvalidationManager`는 value 자체를 저장하지 않습니다. value 저장은 storage/Redis 엔진 쪽 책임이고, 여기서는 "어떤 key가 어떤 태그에 속하는가"만 관리합니다.

### 2. 양방향 인덱스 일관성 유지

`_tag_map`만 유지하거나 `_key_tags`만 유지하면 한쪽 방향 정리는 쉬워도 다른 방향 정리가 불편해집니다. 두 인덱스를 동시에 유지해야 삭제와 무효화가 모두 단순해집니다.

### 3. stale state 방지

무효화 기능에서 가장 흔한 버그는 이미 삭제된 key가 태그 인덱스에 남는 것입니다. 이 파일의 메서드들은 key 제거 시 역방향으로 정리하는 흐름을 중심에 두고 설계되어 있습니다.

### 4. snapshot 친화적 구조

런타임에서는 `set`이 효율적이지만, 저장/복원 시에는 정렬된 `list`가 더 예측 가능합니다. 그래서 export/load 경계에서 자료형을 변환합니다.

## 예시 시나리오

### 태그 등록

```text
SET user:1:profile hello TAGS user:1 demo
SET user:1:posts world TAGS user:1
```

내부적으로는 대략 아래와 같은 상태가 됩니다.

```python
_tag_map = {
    "demo": {"user:1:profile"},
    "user:1": {"user:1:profile", "user:1:posts"},
}

_key_tags = {
    "user:1:profile": {"demo", "user:1"},
    "user:1:posts": {"user:1"},
}
```

### 태그 무효화

```text
INVALIDATE user:1
```

그러면 invalidation 인덱스는:

- `user:1`에 연결된 key 목록을 찾고
- 그 key들을 정리 대상으로 반환하고
- 내부 태그 연결도 함께 지웁니다.

실제 key/value 삭제는 그 결과를 받은 상위 계층이 처리합니다.

## 이 디렉터리에서 지켜야 할 경계

이 폴더의 코드를 확장할 때는 아래 원칙을 지키는 것이 좋습니다.

- command parsing 로직을 넣지 않습니다.
- RESP 인코딩/디코딩 로직을 넣지 않습니다.
- TCP 연결 처리 로직을 넣지 않습니다.
- Redis 전체 엔진 책임을 끌어오지 않습니다.
- 태그 관계 추적과 정리에 집중합니다.

즉, `invalidation/`은 "태그 인덱스 관리자"로 남아야 합니다.

## 정리

`InvalidationManager`는 태그 기반 캐시 무효화를 가능하게 하는 내부 인덱스 계층입니다.

핵심은 아래 두 가지입니다.

- 태그로 key를 빠르게 찾는다.
- key가 사라질 때 태그 흔적도 빠르게 정리한다.

이 두 방향을 동시에 안정적으로 처리하기 위해 `_tag_map`과 `_key_tags`를 함께 유지하고, snapshot 저장/복원과도 자연스럽게 연결되도록 설계되어 있습니다.
