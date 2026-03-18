import time
import unittest

from mini_redis.storage.manager import StorageManager
from mini_redis.storage.ttl import TTLManager


class TTLManagerTest(unittest.TestCase):
    def test_purge_if_expired_removes_value_from_storage(self) -> None:
        # Lazy expiration should clean up the key when it is touched after expiry.
        storage = StorageManager()
        ttl = TTLManager()

        storage.set("session", "alive")
        ttl.set_expiration("session", 1)

        time.sleep(1.1)
        ttl.purge_if_expired("session", storage)

        self.assertFalse(storage.exists("session"))
        self.assertEqual(ttl.ttl("session", storage), -2)

    def test_ttl_without_expiration_reports_persistent_key(self) -> None:
        # Keys without TTL metadata should stay readable and report -1.
        storage = StorageManager()
        ttl = TTLManager()

        storage.set("profile", "ok")

        self.assertEqual(ttl.ttl("profile", storage), -1)
        self.assertEqual(storage.get("profile"), "ok")


if __name__ == "__main__":
    unittest.main()
