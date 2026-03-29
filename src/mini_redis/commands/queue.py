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
            # 같은 스레드 안에서 manager.execute(...)가 다시 호출되면,
            # 이미 실행 중인 자기 자신의 뒤에 다시 줄을 서게 되어 교착상태가 생길 수 있다.
            # 이 경우는 "중첩 실행"으로 보고 queue를 다시 타지 않고 바로 execute(...)를 호출한다.
            if (
                self._active is not None
                and self._active.owner_thread_id == current_thread_id
            ):
                nested_dispatch = True
            else:
                # 각 명령은 ticket 하나로 queue에 들어간다.
                # append 순서가 곧 실행 순서가 되므로, 여러 클라이언트가 동시에 들어와도 FIFO가 유지된다.
                ticket = _QueuedCommand(
                    command=command,
                    owner_thread_id=current_thread_id,
                )
                self._entries.append(ticket)
                # 내 ticket이 맨 앞에 오고, 현재 active 실행이 비어 있을 때만 실행권을 얻는다.
                while self._entries[0] is not ticket or self._active is not None:
                    self._condition.wait()
                self._active = ticket

        if nested_dispatch:
            return execute(command)

        try:
            return execute(command)
        finally:
            with self._condition:
                # 실행이 끝난 ticket은 queue의 맨 앞에서 제거하고,
                # 다음 대기 명령이 깨어나 실행권을 가져갈 수 있게 notify_all()을 호출한다.
                finished = self._entries.popleft()
                if finished is not ticket:
                    raise RuntimeError("Command queue state became inconsistent.")
                self._active = None
                self._processed += 1
                self._condition.notify_all()

    def info(self) -> dict[str, Any]:
        with self._condition:
            # active 하나는 "현재 실행 중"이므로 대기열 길이에는 포함하지 않는다.
            queued = len(self._entries) - (1 if self._active is not None else 0)
            return {
                "queued_commands": max(queued, 0),
                "active_command": (
                    None if self._active is None else self._active.command["name"]
                ),
                "processed_commands": self._processed,
            }
