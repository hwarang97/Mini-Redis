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
        # 네트워크 요청은 모두 이 execute(...)로 들어오고,
        # 여기서 명령을 정규화한 뒤 CommandQueue에 넘겨 FIFO 순서로 실행한다.
        # 그래서 transport 계층은 병렬 요청을 받아도, 실제 명령 실행 순서는 queue가 통제한다.
        normalized = self._normalize_command(command)
        return self._queue.run(normalized, self._dispatch)

    def stats(self) -> dict[str, Any]:
        return self._queue.info()

    def _normalize_command(self, command: Command) -> Command:
        # command name과 args를 문자열 기준으로 한 번 더 정리해 두면
        # queue 안에 들어가는 데이터 형태가 항상 일정해져서 logging, metrics, replay에도 유리하다.
        return {
            "name": str(command["name"]).upper(),
            "args": [str(arg) for arg in list(command["args"])],
        }

    def _dispatch(self, command: Command) -> object:
        handler = self._handlers.get(command["name"])
        if handler is None:
            return f"ERR unknown command '{command['name']}'"
        # 실제 비즈니스 로직 호출은 queue 바깥이 아니라 이 dispatch 경계 안에서만 일어나도록 유지한다.
        # 이렇게 해야 "queue -> handler 실행" 흐름이 한눈에 보이고, 실행 경로도 추적하기 쉬워진다.
        return handler.handle(command)
