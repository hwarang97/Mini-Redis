"""INFO command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class InfoHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) != 1:
            return "ERR wrong number of arguments for 'INFO'"

        section = args[0].upper()
        if section != "PERSISTENCE":
            return "ERR unsupported INFO section"

        return self.redis.info(section)
