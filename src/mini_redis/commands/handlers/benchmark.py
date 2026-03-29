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
        operation: str | None = None
        count_index = 1
        if len(args) >= 3:
            try:
                int(args[1])
            except ValueError:
                operation = args[1]
                count_index = 2

        if len(args) <= count_index:
            return "ERR wrong number of arguments for 'BENCHMARK'"

        try:
            operations = int(args[count_index])
        except ValueError:
            return "ERR operations must be an integer"

        keep_data = False
        if len(args) > count_index + 1:
            if args[count_index + 1].upper() != "KEEP":
                return "ERR syntax error"
            keep_data = True
        if len(args) > count_index + 2:
            return "ERR syntax error"

        return self.redis.benchmark(
            target,
            operations,
            operation=operation,
            keep_data=keep_data,
        )
