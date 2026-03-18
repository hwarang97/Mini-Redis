"""HELP command handler."""

from __future__ import annotations

from mini_redis.commands.catalog import help_line_for
from mini_redis.commands.catalog import list_help_lines
from mini_redis.commands.handlers.base import BaseHandler
from mini_redis.types import Command


class HelpHandler(BaseHandler):
    def handle(self, command: Command) -> object:
        args = command["args"]
        if len(args) > 1:
            return "ERR wrong number of arguments for 'HELP'"
        if not args:
            return list_help_lines()

        line = help_line_for(args[0])
        if line is None:
            return f"ERR unknown command '{args[0].upper()}'"
        return line
