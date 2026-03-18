"""FIFO command execution queue."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition
from threading import get_ident
from typing import Any

from mini_redis.types import Command


@dataclass(slots=True)
class _QueuedCommand:
    command: Command
    owner_thread_id: int


class CommandQueue:
    """Serialize concurrent command execution in FIFO order."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._entries: deque[_QueuedCommand] = deque()
        self._active: _QueuedCommand | None = None
        self._processed = 0

    def run(
        self,
        command: Command,
        execute: Callable[[Command], object],
    ) -> object:
        nested_dispatch = False
        ticket: _QueuedCommand | None = None
        current_thread_id = get_ident()

        with self._condition:
            # Nested manager.execute(...) from the same thread would otherwise
            # queue behind the command it is already running and deadlock.
            if (
                self._active is not None
                and self._active.owner_thread_id == current_thread_id
            ):
                nested_dispatch = True
            else:
                ticket = _QueuedCommand(
                    command=command,
                    owner_thread_id=current_thread_id,
                )
                self._entries.append(ticket)
                while self._entries[0] is not ticket or self._active is not None:
                    self._condition.wait()
                self._active = ticket

        if nested_dispatch:
            return execute(command)

        try:
            return execute(command)
        finally:
            with self._condition:
                finished = self._entries.popleft()
                if finished is not ticket:
                    raise RuntimeError("Command queue state became inconsistent.")
                self._active = None
                self._processed += 1
                self._condition.notify_all()

    def info(self) -> dict[str, Any]:
        with self._condition:
            queued = len(self._entries) - (1 if self._active is not None else 0)
            return {
                "queued_commands": max(queued, 0),
                "active_command": (
                    None if self._active is None else self._active.command["name"]
                ),
                "processed_commands": self._processed,
            }
