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


if __name__ == "__main__":
    unittest.main()
