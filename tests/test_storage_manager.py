import unittest

from mini_redis.storage.manager import StorageManager


class StorageManagerTest(unittest.TestCase):
    def test_incremental_rehash_preserves_all_values(self) -> None:
        # Enough writes should start rehashing without losing readable keys.
        storage = StorageManager()
        for index in range(4):
            storage.set(f"key:{index}", f"value:{index}")

        self.assertIsNotNone(storage._rehash_table)
        self.assertEqual(
            storage.items(),
            {f"key:{index}": f"value:{index}" for index in range(4)},
        )

    def test_update_during_rehash_keeps_latest_value_once(self) -> None:
        # Updating mid-rehash should replace the value, not duplicate the key.
        storage = StorageManager()
        for index in range(4):
            storage.set(f"key:{index}", f"value:{index}")

        storage.set("key:1", "updated")

        self.assertEqual(storage.get("key:1"), "updated")
        self.assertEqual(storage.keys(), ["key:0", "key:1", "key:2", "key:3"])

    def test_rehash_completes_as_operations_continue(self) -> None:
        # Each storage operation advances a small part of the rehash work.
        storage = StorageManager()
        for index in range(8):
            storage.set(f"key:{index}", f"value:{index}")

        for index in range(16):
            storage.exists(f"key:{index}")

        self.assertIsNone(storage._rehash_table)
        self.assertEqual(storage.get("key:7"), "value:7")

    def test_inspect_reports_rehash_state_and_table_contents(self) -> None:
        storage = StorageManager()
        for index in range(4):
            storage.set(f"key:{index}", f"value:{index}")

        payload = storage.inspect(include_table=True)

        self.assertTrue(payload["is_rehashing"])
        self.assertEqual(payload["size"], 4)
        self.assertGreater(payload["rehash_starts"], 0)
        self.assertIn("latency", payload)
        self.assertIn("table", payload)
        self.assertEqual(payload["items"]["key:3"], "value:3")

    def test_inspect_tracks_recent_operation_latency_samples(self) -> None:
        storage = StorageManager()

        storage.set("alpha", "1")
        storage.get("alpha")
        payload = storage.inspect()

        self.assertEqual(payload["latency"]["samples"], 2)
        self.assertIsNotNone(payload["latency"]["last_us"])
        self.assertEqual(payload["recent_operations"][-1]["operation"], "get")


if __name__ == "__main__":
    unittest.main()
