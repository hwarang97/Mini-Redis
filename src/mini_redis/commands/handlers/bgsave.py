"""BGSAVE command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class BGSaveHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        if command["args"]:
            return "ERR wrong number of arguments for 'BGSAVE'"
        return self.redis.bgsave()
