"""Interactive CLI client."""

from __future__ import annotations

import time

from mini_redis.cli.parser import parse_cli_command
from mini_redis.network.tcp_client import TCPClient
from mini_redis.protocol.resp import RespCodec


class CLIClient:
    """Prompt for commands and print server responses."""

    def __init__(self, tcp_client: TCPClient, codec: RespCodec) -> None:
        self._tcp_client = tcp_client
        self._codec = codec

    def run(self) -> None:
        print("Mini Redis CLI. Type QUIT to exit.")
        while True:
            try:
                raw = input("mini-redis> ")
            except EOFError:
                print()
                break

            command = parse_cli_command(raw)
            if command is None:
                continue

            if command["name"] == "WATCH":
                should_quit = self._run_watch_mode(command)
                if should_quit:
                    break
                continue

            if command["name"] == "LIVESET":
                self._run_liveset_mode(command)
                continue

            response = self._tcp_client.send(command)
            rendered = self._codec.format_for_display(response)
            print(rendered)

            if command["name"] == "QUIT":
                break

    def _run_watch_mode(self, command) -> bool:
        args = list(command["args"])
        if not args:
            print("ERR wrong number of arguments for 'WATCH'")
            return False

        interval_seconds = 0.5
        iterations = 10
        index = 0

        if index < len(args):
            try:
                interval_seconds = float(args[index])
                index += 1
            except ValueError:
                pass

        if index < len(args):
            try:
                iterations = int(args[index])
                index += 1
            except ValueError:
                pass

        if index >= len(args):
            print("ERR WATCH requires a nested command")
            return False

        nested_command = {"name": args[index].upper(), "args": args[index + 1 :]}
        for iteration in range(1, iterations + 1):
            response = self._tcp_client.send(nested_command)
            rendered = self._codec.format_for_display(response)
            print(f"[watch {iteration}/{iterations}]")
            print(rendered)
            if nested_command["name"] == "QUIT":
                return True
            if iteration != iterations:
                time.sleep(interval_seconds)
        return False

    def _run_liveset_mode(self, command) -> None:
        args = list(command["args"])
        if not args:
            print("ERR wrong number of arguments for 'LIVESET'")
            return

        try:
            count = int(args[0])
        except ValueError:
            print("ERR LIVESET count must be an integer")
            return

        interval_seconds = 0.0
        key_prefix = "live:set:"
        if len(args) >= 2:
            try:
                interval_seconds = float(args[1])
            except ValueError:
                key_prefix = args[1]
        if len(args) >= 3:
            key_prefix = args[2]
        if len(args) > 3:
            print("ERR syntax error")
            return

        for index in range(count):
            generated_key = f"{key_prefix}{index}"
            generated_value = str(index)
            response = self._tcp_client.send(
                {
                    "name": "PROBE",
                    "args": ["SET", generated_key, generated_value],
                }
            )
            print(response)
            if interval_seconds > 0 and index + 1 != count:
                time.sleep(interval_seconds)
