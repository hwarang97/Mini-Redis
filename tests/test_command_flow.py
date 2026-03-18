import time
import unittest
from pathlib import Path

from mini_redis.bootstrap import build_command_manager
from mini_redis.config import APPEND_ONLY_FILE, SNAPSHOT_FILE


class CommandFlowTest(unittest.TestCase):
    def test_basic_command_flow(self) -> None:
        manager = build_command_manager()

        self.assertEqual(manager.execute({"name": "PING", "args": []}), "PONG")
        self.assertEqual(manager.execute({"name": "SET", "args": ["user:1", "hello"]}), "OK")
        self.assertEqual(manager.execute({"name": "EXISTS", "args": ["user:1"]}), 1)
        self.assertEqual(manager.execute({"name": "GET", "args": ["user:1"]}), "hello")
        self.assertEqual(manager.execute({"name": "DELETE", "args": ["user:1"]}), 1)
        self.assertEqual(manager.execute({"name": "EXISTS", "args": ["user:1"]}), 0)
        self.assertIsNone(manager.execute({"name": "GET", "args": ["user:1"]}))

    def test_ttl_commands(self) -> None:
        manager = build_command_manager()

        self.assertEqual(manager.execute({"name": "SET", "args": ["temp", "1"]}), "OK")
        self.assertEqual(manager.execute({"name": "EXPIRE", "args": ["temp", "1"]}), 1)
        ttl = manager.execute({"name": "TTL", "args": ["temp"]})
        self.assertIn(ttl, {0, 1})
        time.sleep(1.1)
        self.assertIsNone(manager.execute({"name": "GET", "args": ["temp"]}))
        self.assertEqual(manager.execute({"name": "TTL", "args": ["temp"]}), -2)

    def test_keys_returns_sorted_live_keys(self) -> None:
        manager = build_command_manager()

        manager.execute({"name": "SET", "args": ["b", "2"]})
        manager.execute({"name": "SET", "args": ["a", "1"]})

        self.assertEqual(manager.execute({"name": "KEYS", "args": []}), ["a", "b"])

    def test_incr_and_mget(self) -> None:
        manager = build_command_manager()

        self.assertEqual(manager.execute({"name": "INCR", "args": ["counter"]}), 1)
        self.assertEqual(manager.execute({"name": "INCR", "args": ["counter"]}), 2)
        manager.execute({"name": "SET", "args": ["x", "10"]})

        self.assertEqual(
            manager.execute({"name": "MGET", "args": ["counter", "x", "missing"]}),
            ["2", "10", None],
        )

    def test_save_and_flushdb(self) -> None:
        manager = build_command_manager()
        manager.execute({"name": "SET", "args": ["persist:key", "value"]})

        snapshot_path = Path(manager.execute({"name": "SAVE", "args": []}))
        self.assertEqual(snapshot_path, SNAPSHOT_FILE)
        self.assertTrue(snapshot_path.exists())
        self.assertEqual(manager.execute({"name": "FLUSHDB", "args": []}), 1)
        self.assertEqual(manager.execute({"name": "KEYS", "args": []}), [])
        self.assertTrue(APPEND_ONLY_FILE.exists())


if __name__ == "__main__":
    unittest.main()
