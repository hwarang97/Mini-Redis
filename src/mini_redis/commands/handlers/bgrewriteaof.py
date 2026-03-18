"""BGREWRITEAOF command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class BGRewriteAOFHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        if command["args"]:
            return "ERR wrong number of arguments for 'BGREWRITEAOF'"
        return self.redis.bgrewriteaof()
