import threading
import time
import unittest

from mini_redis.commands.manager import CommandManager


class _BlockingHandler:
    def __init__(
        self,
        started: threading.Event,
        release: threading.Event,
        calls: list[str],
    ) -> None:
        self._started = started
        self._release = release
        self._calls = calls

    def handle(self, command):
        self._calls.append(command["name"])
        self._started.set()
        self._release.wait(timeout=1)
        return "slow-done"


class _RecordingHandler:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def handle(self, command):
        self._calls.append(command["name"])
        return "fast-done"


class CommandManagerQueueTest(unittest.TestCase):
    def test_execute_serializes_concurrent_commands_in_fifo_order(self) -> None:
        started = threading.Event()
        release = threading.Event()
        calls: list[str] = []
        results: list[str] = []
        manager = CommandManager(
            handlers={
                "SLOW": _BlockingHandler(started, release, calls),
                "FAST": _RecordingHandler(calls),
            }
        )

        slow_thread = threading.Thread(
            target=lambda: results.append(
                manager.execute({"name": "slow", "args": []})
            )
        )
        fast_thread = threading.Thread(
            target=lambda: results.append(
                manager.execute({"name": "fast", "args": []})
            )
        )

        slow_thread.start()
        self.assertTrue(started.wait(timeout=1))

        fast_thread.start()

        for _ in range(20):
            stats = manager.stats()
            if (
                stats["active_command"] == "SLOW"
                and stats["queued_commands"] == 1
            ):
                break
            time.sleep(0.01)

        self.assertEqual(manager.stats()["active_command"], "SLOW")
        self.assertEqual(manager.stats()["queued_commands"], 1)
        self.assertEqual(calls, ["SLOW"])

        release.set()
        slow_thread.join(timeout=1)
        fast_thread.join(timeout=1)

        self.assertEqual(calls, ["SLOW", "FAST"])
        self.assertCountEqual(results, ["slow-done", "fast-done"])
        self.assertEqual(manager.stats()["processed_commands"], 2)
        self.assertEqual(manager.stats()["queued_commands"], 0)
        self.assertIsNone(manager.stats()["active_command"])


if __name__ == "__main__":
    unittest.main()
