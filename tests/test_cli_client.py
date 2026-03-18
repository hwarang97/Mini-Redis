import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from mini_redis.cli.client import CLIClient
from mini_redis.protocol.resp import RespCodec


class _FakeTCPClient:
    def __init__(self) -> None:
        self.commands: list[dict[str, object]] = []

    def send(self, command):
        self.commands.append(command)
        if command["name"] == "PING":
            return "PONG"
        if command["name"] == "SET":
            return "OK"
        if command["name"] == "MGET":
            return ["hello", None, "42"]
        if command["name"] == "INFO":
            return "# Persistence\r\nkey_count:1"
        if command["name"] == "QUIT":
            return "BYE"
        return "OK"


class CLIClientTest(unittest.TestCase):
    def test_run_supports_local_commands_and_formats_server_output(self) -> None:
        outputs: list[str] = []
        raw_inputs = iter([".help", "SET user:1 hello", "MGET user:1 missing counter", ".demo", ".exit"])
        clock_values = iter([0.0, 0.001, 1.0, 1.002])
        client = CLIClient(
            tcp_client=_FakeTCPClient(),
            codec=RespCodec(),
            host="127.0.0.1",
            port=6380,
            input_func=lambda prompt: next(raw_inputs),
            output_func=outputs.append,
            use_color=False,
            clock=lambda: next(clock_values),
        )

        client.run()

        rendered = "\n".join(outputs)
        self.assertIn("__  __ _       _", rendered)
        self.assertIn("Mini Redis Presentation CLI", rendered)
        self.assertIn("status : READY", rendered)
        self.assertIn("Presenter Shortcuts", rendered)
        self.assertIn("[ok | 1.0 ms] OK", rendered)
        self.assertIn("[list | 2.0 ms]", rendered)
        self.assertIn("1. hello", rendered)
        self.assertIn("2. (nil)", rendered)
        self.assertIn("Suggested Demo Flow", rendered)
        self.assertIn("Session closed.", rendered)

    def test_run_reports_parsing_errors_without_crashing(self) -> None:
        outputs: list[str] = []
        raw_inputs = iter(['SET user:1 "oops', ".exit"])
        client = CLIClient(
            tcp_client=_FakeTCPClient(),
            codec=RespCodec(),
            host="127.0.0.1",
            port=6380,
            input_func=lambda prompt: next(raw_inputs),
            output_func=outputs.append,
            use_color=False,
        )

        client.run()

        rendered = "\n".join(outputs)
        self.assertIn("ERR invalid CLI input", rendered)
        self.assertIn("Session closed.", rendered)


class CLIClientProbeModeTest(unittest.TestCase):
    def test_watch_mode_replays_nested_command_multiple_times(self) -> None:
        tcp_client = _FakeTCPClient()
        client = CLIClient(
            tcp_client=tcp_client,
            codec=RespCodec(),
            host="127.0.0.1",
            port=6380,
            use_color=False,
        )

        with patch("mini_redis.cli.client.time.sleep"), io.StringIO() as buffer:
            with redirect_stdout(buffer):
                should_quit = client._run_watch_mode(
                    {"name": "WATCH", "args": ["0.01", "3", "INSPECT", "STORAGE"]}
                )
            output = buffer.getvalue()

        self.assertFalse(should_quit)
        self.assertEqual(
            tcp_client.commands,
            [{"name": "INSPECT", "args": ["STORAGE"]}] * 3,
        )
        self.assertIn("[watch 1/3]", output)
        self.assertIn("OK", output)

    def test_liveset_mode_generates_probe_set_requests(self) -> None:
        tcp_client = _FakeTCPClient()
        client = CLIClient(
            tcp_client=tcp_client,
            codec=RespCodec(),
            host="127.0.0.1",
            port=6380,
            use_color=False,
        )

        with patch("mini_redis.cli.client.time.sleep"), io.StringIO() as buffer:
            with redirect_stdout(buffer):
                client._run_liveset_mode(
                    {"name": "LIVESET", "args": ["3", "0.01", "probe:live:"]}
                )
            output = buffer.getvalue()

        self.assertEqual(
            tcp_client.commands,
            [
                {"name": "PROBE", "args": ["SET", "probe:live:0", "0"]},
                {"name": "PROBE", "args": ["SET", "probe:live:1", "1"]},
                {"name": "PROBE", "args": ["SET", "probe:live:2", "2"]},
            ],
        )
        self.assertIn("OK", output)
