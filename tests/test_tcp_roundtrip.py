import errno
import socket
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mini_redis.bootstrap import build_command_manager
from mini_redis.network.tcp_client import TCPClient
from mini_redis.network.tcp_server import TCPServer
from mini_redis.network.timing import TIMING_MARKER
from mini_redis.network.timing import unwrap_timed_response
from mini_redis.protocol.resp import RespCodec


class TcpRoundTripTest(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / "data"
        temp_root.mkdir(exist_ok=True)
        self.temp_dir = TemporaryDirectory(dir=temp_root)
        base = Path(self.temp_dir.name)
        self.appendonly_path = base / "appendonly.aof"
        self.snapshot_path = base / "dump.rdb.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_tcp_roundtrip(self) -> None:
        try:
            server = TCPServer(
                host="127.0.0.1",
                port=6391,
                manager=build_command_manager(
                    appendonly_path=self.appendonly_path,
                    snapshot_path=self.snapshot_path,
                ),
                codec=RespCodec(),
            )
        except PermissionError as exc:
            if exc.errno == errno.EPERM:
                self.skipTest("sandbox blocks local TCP bind")
            raise

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)

        try:
            client = TCPClient("127.0.0.1", 6391, RespCodec())
            ping = client.send_timed({"name": "PING", "args": []})
            self.assertEqual(ping.value, "PONG")
            self.assertIsNotNone(ping.server_time_ms)
            self.assertEqual(client.send({"name": "SET", "args": ["smoke", "ok"]}), "OK")
            self.assertEqual(client.send({"name": "GET", "args": ["smoke"]}), "ok")
        finally:
            server.shutdown()
            thread.join(timeout=1)

    def test_server_accepts_multiline_resp_frames(self) -> None:
        try:
            server = TCPServer(
                host="127.0.0.1",
                port=6392,
                manager=build_command_manager(
                    appendonly_path=self.appendonly_path,
                    snapshot_path=self.snapshot_path,
                ),
                codec=RespCodec(),
            )
        except PermissionError as exc:
            if exc.errno == errno.EPERM:
                self.skipTest("sandbox blocks local TCP bind")
            raise

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)

        codec = RespCodec()
        try:
            with socket.create_connection(("127.0.0.1", 6392)) as conn:
                conn.sendall(codec.encode_command({"name": "SET", "args": ["resp:key", "value"]}))
                with conn.makefile("rb") as stream:
                    payload = codec.decode_response_stream(stream)
                    self.assertEqual(payload[0], TIMING_MARKER)
                    self.assertEqual(unwrap_timed_response(payload)[0], "OK")

            with socket.create_connection(("127.0.0.1", 6392)) as conn:
                payload = codec.encode_command({"name": "GET", "args": ["resp:key"]})
                midpoint = len(payload) // 2
                conn.sendall(payload[:midpoint])
                conn.sendall(payload[midpoint:])
                with conn.makefile("rb") as stream:
                    response = codec.decode_response_stream(stream)
                    self.assertEqual(unwrap_timed_response(response)[0], "value")
        finally:
            server.shutdown()
            thread.join(timeout=1)

    def test_server_keeps_connection_open_for_multiple_commands(self) -> None:
        try:
            server = TCPServer(
                host="127.0.0.1",
                port=6393,
                manager=build_command_manager(
                    appendonly_path=self.appendonly_path,
                    snapshot_path=self.snapshot_path,
                ),
                codec=RespCodec(),
            )
        except PermissionError as exc:
            if exc.errno == errno.EPERM:
                self.skipTest("sandbox blocks local TCP bind")
            raise

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)

        codec = RespCodec()
        try:
            with socket.create_connection(("127.0.0.1", 6393)) as conn:
                with conn.makefile("rb") as stream:
                    conn.sendall(codec.encode_command({"name": "PING", "args": []}))
                    self.assertEqual(
                        unwrap_timed_response(codec.decode_response_stream(stream))[0],
                        "PONG",
                    )

                    conn.sendall(codec.encode_command({"name": "GET", "args": ["missing"]}))
                    self.assertIsNone(
                        unwrap_timed_response(codec.decode_response_stream(stream))[0]
                    )
        finally:
            server.shutdown()
            thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
