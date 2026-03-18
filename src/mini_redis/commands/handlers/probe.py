"""PROBE command handler."""

from __future__ import annotations

from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class ProbeHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) < 3:
            return "ERR wrong number of arguments for 'PROBE'"

        subcommand = args[0].upper()
        if subcommand not in {"SET", "UPDATE"}:
            return "ERR unsupported PROBE subcommand"

        key = args[1]
        value = args[2]
        ttl_seconds = None
        tags: list[str] | None = None
        if subcommand == "UPDATE":
            if len(args) != 3:
                return "ERR syntax error"
            return self.redis.probe_update(key, value)

        index = 3
        while index < len(args):
            token = args[index].upper()
            if token == "EX":
                if ttl_seconds is not None or index + 1 >= len(args):
                    return "ERR syntax error"
                try:
                    ttl_seconds = int(args[index + 1])
                except ValueError:
                    return "ERR value is not an integer or out of range"
                index += 2
                continue
            if token == "TAGS":
                if tags is not None:
                    return "ERR syntax error"
                tags = []
                index += 1
                while index < len(args) and args[index].upper() not in {"EX", "TAGS"}:
                    tags.append(args[index])
                    index += 1
                if not tags:
                    return "ERR syntax error"
                continue
            return "ERR syntax error"

        return self.redis.probe_set(key, value, ttl_seconds=ttl_seconds, tags=tags)
