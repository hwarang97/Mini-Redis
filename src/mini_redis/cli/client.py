"""Interactive CLI client."""

from __future__ import annotations

import os
import sys
from textwrap import dedent
from time import perf_counter
from typing import Any
from typing import Callable

from mini_redis.cli.parser import parse_cli_command
from mini_redis.cli.parser import parse_cli_meta_command
from mini_redis.network.tcp_client import TCPClient
from mini_redis.protocol.resp import RespCodec
from mini_redis.types import Command

InputFunc = Callable[[str], str]
OutputFunc = Callable[[str], None]


class CLIClient:
    """Prompt for commands and print server responses."""

    _RESET = "\033[0m"
    _BOLD = "\033[1m"
    _RED = "\033[31m"
    _GREEN = "\033[32m"
    _YELLOW = "\033[33m"
    _CYAN = "\033[36m"
    _ACCENT = "\033[33m"
    _ASCII_ART = dedent(
        """
         __  __ _       _      ____          _ _
        |  \/  (_)_ __ (_)    |  _ \ ___  __| (_)___
        | |\/| | | '_ \| |____| |_) / _ \/ _` | / __|
        | |  | | | | | | |____|  _ <  __/ (_| | \__ \\
        |_|  |_|_|_| |_|_|    |_| \_\___|\__,_|_|___/
        """
    ).strip("\n")

    def __init__(
        self,
        tcp_client: TCPClient,
        codec: RespCodec,
        host: str,
        port: int,
        input_func: InputFunc = input,
        output_func: OutputFunc = print,
        use_color: bool | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._tcp_client = tcp_client
        self._codec = codec
        self._host = host
        self._port = port
        self._input = input_func
        self._output = output_func
        self._clock = clock
        self._prompt_index = 1
        self._exit_requested = False
        self._use_color = (
            sys.stdout.isatty() and "NO_COLOR" not in os.environ
            if use_color is None
            else use_color
        )

    def run(self) -> None:
        self._print_banner()
        self._print_connection_status()
        self._emit("Type .help for presenter shortcuts.")

        while True:
            try:
                raw = self._input(self._build_prompt())
            except EOFError:
                self._emit("")
                break
            except KeyboardInterrupt:
                self._emit("")
                self._emit(self._tone("Interrupted. Type .exit to leave cleanly.", self._YELLOW))
                continue

            try:
                if self._handle_local_input(raw):
                    if self._exit_requested:
                        break
                    self._prompt_index += 1
                    continue
                command = parse_cli_command(raw)
            except ValueError as exc:
                self._emit(self._format_error(f"ERR {exc}"))
                self._prompt_index += 1
                continue

            if command is None:
                continue

            should_continue = self._run_server_command(command)
            self._prompt_index += 1
            if not should_continue:
                break

    def _handle_local_input(self, raw: str) -> bool:
        local_command = parse_cli_meta_command(raw)
        if local_command is None:
            return False

        name = local_command["name"]
        if name in {".help", ".h"}:
            self._print_help()
            return True
        if name == ".demo":
            self._print_demo()
            return True
        if name == ".clear":
            self._emit("\033[2J\033[H" if self._use_color else "\n" * 40)
            return True
        if name in {".exit", ".quit"}:
            self._emit(self._tone("Session closed.", self._YELLOW))
            self._exit_requested = True
            return True

        self._emit(self._format_error(f"ERR unknown local command '{name}'"))
        self._emit("Type .help to see available presenter shortcuts.")
        return True

    def _run_server_command(self, command: Command) -> bool:
        try:
            started = self._clock()
            response = self._tcp_client.send(command)
            elapsed_ms = (self._clock() - started) * 1000
        except OSError as exc:
            self._emit(self._format_error(f"ERR connection failed: {exc}"))
            return command["name"] != "QUIT"

        self._emit(self._render_response(response, elapsed_ms))
        return command["name"] != "QUIT"

    def _print_banner(self) -> None:
        self._emit("")
        for line in self._ASCII_ART.splitlines():
            self._emit(self._tone(line, self._ACCENT))
        self._emit("")
        self._emit(self._tone("=======================================================", self._ACCENT))
        self._emit(self._tone(" Mini Redis Presentation CLI", self._ACCENT, bold=True))
        self._emit(self._tone(" RESP | TTL | Persistence | Invalidation | Mongo Sync", self._ACCENT))
        self._emit(self._tone("=======================================================", self._ACCENT))
        self._emit(f" server : {self._host}:{self._port}")
        self._emit(" focus  : demo-friendly terminal UX with local shortcuts")
        self._emit("")

    def _print_connection_status(self) -> None:
        try:
            response = self._tcp_client.send({"name": "PING", "args": []})
        except OSError as exc:
            self._emit(self._tone(f" status : OFFLINE ({exc})", self._RED, bold=True))
            self._emit(self._tone(" hint   : start mini-redis-server, then retry a command", self._YELLOW))
            self._emit("")
            return

        status = "READY" if response == "PONG" else f"UNEXPECTED ({response})"
        color = self._GREEN if response == "PONG" else self._YELLOW
        self._emit(self._tone(f" status : {status}", color, bold=True))
        self._emit("")

    def _print_help(self) -> None:
        self._emit(self._tone("Presenter Shortcuts", self._ACCENT, bold=True))
        self._emit("  .help   Show this help")
        self._emit("  .demo   Print a recommended live demo sequence")
        self._emit("  .clear  Clear the terminal")
        self._emit("  .exit   Exit the CLI without sending QUIT")
        self._emit("")
        self._emit(self._tone("Tip", self._ACCENT, bold=True))
        self._emit("  Lines starting with # are ignored, so you can annotate your demo script.")
        self._emit("  Use quoted strings for values with spaces, for example:")
        self._emit('    SET user:1 "hello mini redis" TAGS user:1 demo')
        self._emit("")

    def _print_demo(self) -> None:
        self._emit(self._tone("Suggested Demo Flow", self._ACCENT, bold=True))
        self._emit("  # connectivity")
        self._emit("  PING")
        self._emit("  HELP")
        self._emit("  # basic key/value")
        self._emit("  SET user:1 hello")
        self._emit("  GET user:1")
        self._emit("  # ttl + tags")
        self._emit("  SET user:1:session live EX 30 TAGS user:1 demo")
        self._emit("  TTL user:1:session")
        self._emit("  DUMPALL")
        self._emit("  # bulk read")
        self._emit("  MGET user:1 user:1:session missing:key")
        self._emit("  # cache invalidation")
        self._emit("  INVALIDATE user:1")
        self._emit("  # persistence")
        self._emit("  SAVE")
        self._emit("  INFO PERSISTENCE")
        self._emit("  # optional mongo")
        self._emit("  INFO MONGO")
        self._emit("")

    def _build_prompt(self) -> str:
        return self._tone(f"mini-redis[{self._prompt_index:02d}]> ", self._ACCENT, bold=True)

    def _render_response(self, value: Any, elapsed_ms: float) -> str:
        label = "ok"
        color = self._GREEN
        if isinstance(value, str) and value.startswith("ERR "):
            label = "err"
            color = self._RED
        elif isinstance(value, str) and value.startswith("# "):
            label = "info"
            color = self._CYAN
        elif isinstance(value, list):
            label = "list"
            color = self._YELLOW

        header = self._tone(f"[{label} | {elapsed_ms:.1f} ms]", color, bold=True)
        body_lines = self._format_value_lines(value)
        if len(body_lines) == 1:
            return f"{header} {body_lines[0]}"
        return "\n".join([header, *body_lines])

    def _format_value_lines(self, value: Any, indent: str = "") -> list[str]:
        if isinstance(value, list):
            if not value:
                return [f"{indent}(empty list)"]
            lines: list[str] = []
            for index, item in enumerate(value, start=1):
                if isinstance(item, list):
                    lines.append(f"{indent}{index}.")
                    lines.extend(self._format_value_lines(item, indent=f"{indent}   "))
                    continue

                item_lines = self._format_scalar_lines(item)
                if len(item_lines) == 1:
                    lines.append(f"{indent}{index}. {item_lines[0]}")
                    continue
                lines.append(f"{indent}{index}.")
                lines.extend(f"{indent}   {line}" for line in item_lines)
            return lines

        return self._format_scalar_lines(value)

    def _format_scalar_lines(self, value: Any) -> list[str]:
        rendered = self._codec.format_for_display(value).replace("\r\n", "\n")
        return rendered.splitlines() or [rendered]

    def _format_error(self, message: str) -> str:
        return self._tone(message, self._RED, bold=True)

    def _tone(self, text: str, color: str, bold: bool = False) -> str:
        if not self._use_color:
            return text
        prefix = color
        if bold:
            prefix += self._BOLD
        return f"{prefix}{text}{self._RESET}"

    def _emit(self, message: str) -> None:
        self._output(message)
