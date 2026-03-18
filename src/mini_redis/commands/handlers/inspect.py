"""INSPECT command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class InspectHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if not args:
            return "ERR wrong number of arguments for 'INSPECT'"

        section = args[0].upper()
        if section != "STORAGE":
            return "ERR unsupported INSPECT section"

        if len(args) == 1:
            return self.redis.inspect_storage(include_table=False)

        mode = args[1].upper()
        if mode == "FULL":
            if len(args) != 2:
                return "ERR syntax error"
            return self.redis.inspect_storage(include_table=True)
        if mode == "RESET":
            if len(args) != 2:
                return "ERR syntax error"
            return self.redis.reset_storage_diagnostics()
        if mode == "RUN":
            if len(args) != 3:
                return "ERR syntax error"
            try:
                operations = int(args[2])
            except ValueError:
                return "ERR operations must be an integer"
            return self.redis.run_storage_probe(operations)
        if mode == "UPDATE":
            if len(args) != 3:
                return "ERR syntax error"
            try:
                operations = int(args[2])
            except ValueError:
                return "ERR operations must be an integer"
            return self.redis.run_storage_probe(operations, mode="update")
        return "ERR syntax error"
