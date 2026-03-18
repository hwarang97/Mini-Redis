"""MGET command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class MGetHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if not args:
            return "ERR wrong number of arguments for 'MGET'"
        return self.redis.mget(args)
