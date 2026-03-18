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
        if len(args) == 4 and args[2].upper() == "EX":
            ttl_seconds = int(args[3])
        elif len(args) != 2:
            return "ERR syntax error"

        return self.redis.set(key, value, ttl_seconds=ttl_seconds)
