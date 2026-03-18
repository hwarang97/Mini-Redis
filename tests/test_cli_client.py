import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from mini_redis.cli.client import CLIClient
from mini_redis.protocol.resp import RespCodec


class _FakeTCPClient:
    def __init__(self) -> None:
        self.commands = []

    def send(self, command):
        self.commands.append(command)
        return "OK"


class CLIClientWatchModeTest(unittest.TestCase):
    def test_watch_mode_replays_nested_command_multiple_times(self) -> None:
        tcp_client = _FakeTCPClient()
        client = CLIClient(tcp_client=tcp_client, codec=RespCodec())

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
        client = CLIClient(tcp_client=tcp_client, codec=RespCodec())

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


if __name__ == "__main__":
    unittest.main()
