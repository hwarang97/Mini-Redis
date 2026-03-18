"""BENCHMARK command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class BenchmarkHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) < 2:
            return "ERR wrong number of arguments for 'BENCHMARK'"

        target = args[0]
        try:
            operations = int(args[1])
        except ValueError:
            return "ERR operations must be an integer"

        keep_data = False
        if len(args) >= 3:
            if args[2].upper() != "KEEP":
                return "ERR syntax error"
            keep_data = True
        if len(args) > 3:
            return "ERR syntax error"

        return self.redis.benchmark(target, operations, keep_data=keep_data)
