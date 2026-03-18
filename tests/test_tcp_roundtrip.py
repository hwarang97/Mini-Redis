import errno
import threading
import time
import unittest

from mini_redis.bootstrap import build_command_manager
from mini_redis.network.tcp_client import TCPClient
from mini_redis.network.tcp_server import TCPServer
from mini_redis.protocol.resp import RespCodec


class TcpRoundTripTest(unittest.TestCase):
    def test_tcp_roundtrip(self) -> None:
        try:
            server = TCPServer(
                host="127.0.0.1",
                port=6391,
                manager=build_command_manager(),
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
            self.assertEqual(client.send({"name": "PING", "args": []}), "PONG")
            self.assertEqual(client.send({"name": "SET", "args": ["smoke", "ok"]}), "OK")
            self.assertEqual(client.send({"name": "GET", "args": ["smoke"]}), "ok")
        finally:
            server.shutdown()
            thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
