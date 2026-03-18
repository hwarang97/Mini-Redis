"""Tag-based invalidation index."""

from __future__ import annotations

from collections.abc import Iterable


class InvalidationManager:
    """Track tag-to-key relationships for bulk cache invalidation."""

    def __init__(self) -> None:
        # tag_map:
        #   "user:1" -> {"user:1:profile", "user:1:posts"}
        # 처럼 태그 하나가 어떤 key들을 대표하는지 빠르게 찾기 위한 인덱스다.
        self._tag_map: dict[str, set[str]] = {}
        # key_tags:
        #   "user:1:profile" -> {"user:1"}
        # 처럼 특정 key가 어떤 태그들에 속하는지 역방향으로 추적한다.
        # key 삭제/만료 시 tag_map에서 자기 흔적을 지울 때 사용한다.
        self._key_tags: dict[str, set[str]] = {}

    def set_tags(self, key: str, tags: Iterable[str]) -> None:
        # 빈 문자열이나 중복 태그를 정리해서 인덱스에 넣을 최종 태그 집합을 만든다.
        normalized = {str(tag) for tag in tags if str(tag)}
        previous = set(self._key_tags.get(key, set()))

        # 이전에는 붙어 있었지만 이번 저장에서는 빠진 태그는 연결을 끊는다.
        for removed_tag in previous - normalized:
            self._detach(removed_tag, key)

        # 새로 추가된 태그만 tag_map에 연결하면 불필요한 중복 연산을 줄일 수 있다.
        for added_tag in normalized - previous:
            self._tag_map.setdefault(added_tag, set()).add(key)

        if normalized:
            # 역방향 인덱스도 같이 보관해야 이후 delete/expire에서 정리를 빠르게 할 수 있다.
            self._key_tags[key] = normalized
        else:
            # 태그 없는 key는 invalidation 대상이 아니므로 역방향 정보도 제거한다.
            self._key_tags.pop(key, None)

    def clear_key(self, key: str) -> None:
        # key가 사라질 때는 자신이 속한 모든 태그에서 흔적을 지워야
        # tag_map이 stale state를 들고 있지 않게 된다.
        for tag in list(self._key_tags.get(key, set())):
            self._detach(tag, key)
        self._key_tags.pop(key, None)

    def invalidate(self, tag: str) -> list[str]:
        # 실제 삭제는 Redis 오케스트레이터가 담당하고,
        # 여기서는 "이 태그에 걸린 key 목록 조회 + 인덱스 정리"만 책임진다.
        keys = sorted(self._tag_map.get(tag, set()))
        for key in keys:
            self.clear_key(key)
        return keys

    def tags_for_key(self, key: str) -> list[str]:
        return sorted(self._key_tags.get(key, set()))

    def export(self) -> dict[str, list[str]]:
        # snapshot에는 set을 바로 저장할 수 없어서 정렬된 list 형태로 내보낸다.
        return {
            tag: sorted(keys)
            for tag, keys in sorted(self._tag_map.items())
            if keys
        }

    def load_tag_map(self, values: dict[str, object]) -> None:
        # snapshot 복구 시 tag_map과 key_tags를 동시에 다시 구성한다.
        # 두 인덱스는 항상 같은 상태를 가리켜야 하므로 부분 갱신 대신 전체 재구성을 택했다.
        self.clear_all()
        for raw_tag, raw_keys in values.items():
            tag = str(raw_tag)
            if not isinstance(raw_keys, list):
                continue
            for raw_key in raw_keys:
                key = str(raw_key)
                self._tag_map.setdefault(tag, set()).add(key)
                self._key_tags.setdefault(key, set()).add(tag)

    def clear_all(self) -> None:
        # FLUSHDB / restore 전에 이전 인덱스를 완전히 비울 때 사용한다.
        self._tag_map.clear()
        self._key_tags.clear()

    def _detach(self, tag: str, key: str) -> None:
        # 태그 집합에서 key를 제거한 뒤 비어 있으면 태그 엔트리도 제거해서
        # export 결과와 런타임 상태를 깔끔하게 유지한다.
        keys = self._tag_map.get(tag)
        if keys is None:
            return
        keys.discard(key)
        if not keys:
            self._tag_map.pop(tag, None)
