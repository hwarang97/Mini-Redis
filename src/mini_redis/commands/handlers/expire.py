"""EXPIRE command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class ExpireHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) != 2:
            return "ERR wrong number of arguments for 'EXPIRE'"
        try:
            ttl_seconds = int(args[1])
        except ValueError:
            return "ERR value is not an integer or out of range"
        return self.redis.expire(args[0], ttl_seconds)
