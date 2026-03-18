"""GET command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class GetHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) != 1:
            return "ERR wrong number of arguments for 'GET'"
        return self.redis.get(args[0])
