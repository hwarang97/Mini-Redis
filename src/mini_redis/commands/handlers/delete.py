"""DELETE command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class DeleteHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) != 1:
            return "ERR wrong number of arguments for 'DELETE'"
        return self.redis.delete(args[0])
