"""KEYS command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class KeysHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        if command["args"]:
            return "ERR wrong number of arguments for 'KEYS'"
        return self.redis.keys()
