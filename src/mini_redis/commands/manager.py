"""Command routing entrypoint."""

from __future__ import annotations

from typing import Protocol

from mini_redis.persistence.manager import RecoveryReport
from mini_redis.types import Command


class CommandHandler(Protocol):
    def handle(self, command: Command) -> object:
        ...


class CommandManager:
    """Validate and route commands to per-command handlers."""

    def __init__(
        self,
        handlers: dict[str, CommandHandler],
        recovery_report: RecoveryReport | None = None,
    ) -> None:
        self._handlers = handlers
        self.recovery_report = recovery_report

    def execute(self, command: Command) -> object:
        name = command["name"].upper()
        handler = self._handlers.get(name)
        if handler is None:
            return f"ERR unknown command '{name}'"
        return handler.handle({"name": name, "args": list(command["args"])})
