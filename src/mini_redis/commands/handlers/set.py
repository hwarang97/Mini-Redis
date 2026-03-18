"""SET command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class SetHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) < 2:
            return "ERR wrong number of arguments for 'SET'"

        key = args[0]
        value = args[1]
        ttl_seconds = None
        tags: list[str] | None = None
        index = 2
        while index < len(args):
            token = args[index].upper()
            if token == "EX":
                # EX <seconds> 형태를 읽어서 TTL로 넘긴다.
                # 중복 EX나 값 누락은 syntax error로 처리한다.
                if ttl_seconds is not None or index + 1 >= len(args):
                    return "ERR syntax error"
                try:
                    ttl_seconds = int(args[index + 1])
                except ValueError:
                    return "ERR value is not an integer or out of range"
                index += 2
                continue
            if token == "TAGS":
                # TAGS 뒤에는 다음 옵션(EX/TAGS)이 나오기 전까지를 모두 태그 목록으로 받는다.
                # 예: SET user:1:posts hello EX 60 TAGS user:1 feed
                if tags is not None:
                    return "ERR syntax error"
                tags = []
                index += 1
                while index < len(args) and args[index].upper() not in {"EX", "TAGS"}:
                    tags.append(args[index])
                    index += 1
                if not tags:
                    return "ERR syntax error"
                continue
            return "ERR syntax error"

        return self.redis.set(key, value, ttl_seconds=ttl_seconds, tags=tags)
