"""TTL command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class TTLHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) != 1:
            return "ERR wrong number of arguments for 'TTL'"
        return self.redis.ttl(args[0])
