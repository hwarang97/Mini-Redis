"""SAVE command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class SaveHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        if command["args"]:
            return "ERR wrong number of arguments for 'SAVE'"
        return self.redis.save()
