import errno
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mini_redis.bootstrap import build_command_manager
from mini_redis.network.tcp_client import TCPClient
from mini_redis.network.tcp_server import TCPServer
from mini_redis.protocol.resp import RespCodec


class InspectTcpRoundTripTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.appendonly_path = base / "appendonly.aof"
        self.snapshot_path = base / "dump.rdb.json"
        self.metadata_path = base / "persistence.meta.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_inspect_storage_run_roundtrips_over_tcp(self) -> None:
        try:
            server = TCPServer(
                host="127.0.0.1",
                port=6394,
                manager=build_command_manager(
                    appendonly_path=self.appendonly_path,
                    snapshot_path=self.snapshot_path,
                    metadata_path=self.metadata_path,
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
            client = TCPClient("127.0.0.1", 6394, RespCodec())
            payload = client.send({"name": "INSPECT", "args": ["STORAGE", "RUN", "5"]})
            self.assertIn("# Storage Insert Run", payload)
            self.assertIn("[request:", payload)
            self.assertIn("[resizing:", payload)
        finally:
            server.shutdown()
            thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
