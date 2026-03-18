"""Command routing entrypoint."""

from __future__ import annotations

from typing import Any
from typing import Protocol

from mini_redis.persistence.manager import RecoveryReport
from mini_redis.commands.queue import CommandQueue
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
        self._queue = CommandQueue()
        self.recovery_report = recovery_report

    def execute(self, command: Command) -> object:
        normalized = self._normalize_command(command)
        return self._queue.run(normalized, self._dispatch)

    def stats(self) -> dict[str, Any]:
        return self._queue.info()

    def _normalize_command(self, command: Command) -> Command:
        return {
            "name": str(command["name"]).upper(),
            "args": [str(arg) for arg in list(command["args"])],
        }

    def _dispatch(self, command: Command) -> object:
        handler = self._handlers.get(command["name"])
        if handler is None:
            return f"ERR unknown command '{command['name']}'"
        return handler.handle(command)
