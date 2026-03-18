"""CONFIG command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class ConfigHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) < 2:
            return "ERR wrong number of arguments for 'CONFIG'"

        action = args[0].upper()
        if action == "GET" and len(args) == 2:
            return self.redis.config_get(args[1])
        if action == "SET" and len(args) == 3:
            return self.redis.config_set(args[1], args[2])
        return "ERR syntax error"
