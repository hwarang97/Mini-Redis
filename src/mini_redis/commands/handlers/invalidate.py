"""INVALIDATE command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class InvalidateHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) != 1:
            return "ERR wrong number of arguments for 'INVALIDATE'"
        # handler는 인자 개수 검증만 하고,
        # 실제 tag 기반 삭제 로직은 Redis -> InvalidationManager 흐름으로 넘긴다.
        return self.redis.invalidate(args[0])
