import unittest

from mini_redis.cli.client import CLIClient
from mini_redis.network.tcp_client import TimedResponse
from mini_redis.protocol.resp import RespCodec


class _FakeTCPClient:
    def __init__(self) -> None:
        self.commands: list[dict[str, object]] = []

    def send(self, command):
        return self.send_timed(command).value

    def send_timed(self, command):
        self.commands.append(command)
        if command["name"] == "PING":
            return TimedResponse(value="PONG", server_time_ms=0.041)
        if command["name"] == "SET":
            return TimedResponse(value="OK", server_time_ms=0.052)
        if command["name"] == "MGET":
            return TimedResponse(value=["hello", None, "42"], server_time_ms=0.083)
        if command["name"] == "INFO":
            return TimedResponse(value="# Persistence\r\nkey_count:1", server_time_ms=0.091)
        if command["name"] == "QUIT":
            return TimedResponse(value="BYE", server_time_ms=0.033)
        return TimedResponse(
            value=f"ERR unexpected command '{command['name']}'",
            server_time_ms=0.025,
        )


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
        self.assertIn("[ok | server 0.052 ms | round-trip 1.0 ms] OK", rendered)
        self.assertIn("[list | server 0.083 ms | round-trip 2.0 ms]", rendered)
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


if __name__ == "__main__":
    unittest.main()
