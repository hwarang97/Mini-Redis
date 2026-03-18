import unittest
from pathlib import Path
from shutil import rmtree

from mini_redis.bootstrap import build_command_manager
from mini_redis.storage.benchmark import StorageBenchmarkSuite
from mini_redis.storage.mongo_adapter import MongoAdapter
from mini_redis.storage.mongo_manager import MongoManager


class FakeAdmin:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def command(self, name: str) -> None:
        self.commands.append(name)


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, str]] = {}

    def update_one(self, criteria: dict[str, str], payload: dict[str, dict[str, str]], upsert: bool = False) -> None:
        key = criteria["_id"]
        value = payload["$set"]["value"]
        if upsert or key in self.documents:
            self.documents[key] = {"_id": key, "value": value}

    def delete_one(self, criteria: dict[str, str]) -> None:
        self.documents.pop(criteria["_id"], None)

    def delete_many(self, criteria: dict[str, str]) -> None:
        self.documents.clear()


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


class FakeMongoClient:
    last_instance = None

    def __init__(self, uri: str, serverSelectionTimeoutMS: int) -> None:
        self.uri = uri
        self.server_selection_timeout_ms = serverSelectionTimeoutMS
        self.admin = FakeAdmin()
        self.databases: dict[str, FakeDatabase] = {}
        FakeMongoClient.last_instance = self

    def __getitem__(self, name: str) -> FakeDatabase:
        if name not in self.databases:
            self.databases[name] = FakeDatabase()
        return self.databases[name]


class FailingMongoClient(FakeMongoClient):
    def __init__(self, uri: str, serverSelectionTimeoutMS: int) -> None:
        super().__init__(uri, serverSelectionTimeoutMS)
        raise RuntimeError("ping failed")


class FakeMongoAdapter:
    def __init__(self) -> None:
        self.enabled = True
        self.calls: list[tuple[str, str | None]] = []

    def upsert(self, key: str, value: str) -> None:
        self.calls.append(("upsert", key))

    def delete(self, key: str) -> None:
        self.calls.append(("delete", key))

    def clear(self) -> None:
        self.calls.append(("clear", None))

    def info(self) -> dict[str, object]:
        return {
            "enabled": True,
            "connected": True,
            "uri": "mongodb://fake",
            "database": "mini_redis",
            "collection": "kv_store",
            "operation_count": len(self.calls),
            "last_operation": self.calls[-1] if self.calls else None,
        }


class MongoIntegrationTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        rmtree(Path("data/test-mongo-info"), ignore_errors=True)

    def test_adapter_connects_and_writes_to_mongo_collection(self) -> None:
        adapter = MongoAdapter(
            enabled=True,
            uri="mongodb://127.0.0.1:27017",
            database="mini_redis",
            collection="kv_store",
            client_factory=FakeMongoClient,
        )

        adapter.maybe_sync("user:1", "hello")
        adapter.delete("user:1")
        adapter.upsert("user:2", "world")

        info = adapter.info()
        client = FakeMongoClient.last_instance
        collection = client["mini_redis"]["kv_store"]

        self.assertTrue(info["enabled"])
        self.assertTrue(info["connected"])
        self.assertEqual(info["database"], "mini_redis")
        self.assertEqual(info["collection"], "kv_store")
        self.assertEqual(info["operation_count"], 3)
        self.assertEqual(info["queued_operations"], 3)
        self.assertEqual(collection.documents, {"user:2": {"_id": "user:2", "value": "world"}})
        self.assertEqual(client.admin.commands, ["ping"])

    def test_adapter_raises_clear_error_when_connection_fails(self) -> None:
        with self.assertRaises(RuntimeError):
            MongoAdapter(
                enabled=True,
                uri="mongodb://127.0.0.1:27017",
                database="mini_redis",
                collection="kv_store",
                client_factory=FailingMongoClient,
            )

    def test_manager_delegates_to_adapter_boundary(self) -> None:
        adapter = FakeMongoAdapter()
        manager = MongoManager(adapter)

        manager.maybe_sync("user:1", "hello")
        manager.delete_key("user:1")
        manager.clear()

        self.assertEqual(
            adapter.calls,
            [("upsert", "user:1"), ("delete", "user:1"), ("clear", None)],
        )
        self.assertEqual(manager.info()["operation_count"], 3)

    def test_redis_commands_do_not_auto_sync_to_mongo(self) -> None:
        base = Path("data/test-mongo-info")
        base.mkdir(parents=True, exist_ok=True)
        appendonly_path = base / "appendonly.aof"
        snapshot_path = base / "dump.rdb.json"
        metadata_path = base / "persistence.meta.json"
        for path in (appendonly_path, snapshot_path, metadata_path):
            path.unlink(missing_ok=True)

        manager = build_command_manager(
            appendonly_path=appendonly_path,
            snapshot_path=snapshot_path,
            metadata_path=metadata_path,
            mongo_enabled=True,
            mongo_uri="mongodb://127.0.0.1:27017",
            mongo_db="mini_redis",
            mongo_collection="kv_store",
            mongo_client_factory=FakeMongoClient,
        )

        self.assertEqual(
            manager.execute({"name": "SET", "args": ["user:1", "hello"]}),
            "OK",
        )

        info = manager.execute({"name": "INFO", "args": ["MONGO"]})
        self.assertIn("# Mongo", info)
        self.assertIn("operation_count:0", info)
        self.assertIn("key_count:1", info)

    def test_benchmark_suite_measures_redis_and_mongo_separately(self) -> None:
        from mini_redis.storage.manager import StorageManager

        suite = StorageBenchmarkSuite()
        storage = StorageManager()
        mongo = MongoManager(FakeMongoAdapter())

        redis_result = suite.benchmark_redis_set(storage, 5)
        mongo_result = suite.benchmark_mongo_write(mongo, 5)

        self.assertEqual(redis_result.target, "redis")
        self.assertEqual(redis_result.operation, "set")
        self.assertEqual(redis_result.operations, 5)
        self.assertEqual(mongo_result.target, "mongo")
        self.assertEqual(mongo_result.operation, "write")
        self.assertEqual(mongo_result.operations, 5)

    def test_benchmark_suite_measures_hybrid_storage_and_mongo_together(self) -> None:
        from mini_redis.storage.manager import StorageManager

        suite = StorageBenchmarkSuite()
        storage = StorageManager()
        mongo = MongoManager(FakeMongoAdapter())

        result = suite.benchmark_hybrid_write(storage, mongo, 5, keep_data=True)

        self.assertEqual(result.target, "hybrid")
        self.assertEqual(result.operation, "write")
        self.assertEqual(result.operations, 5)
        self.assertTrue(result.details["storage"]["size"] >= 5)
        self.assertEqual(result.details["mongo"]["operation_count"], 5)

    def test_build_manager_exposes_mongo_info_section(self) -> None:
        base = Path("data/test-mongo-info")
        base.mkdir(parents=True, exist_ok=True)
        appendonly_path = base / "appendonly.aof"
        snapshot_path = base / "dump.rdb.json"
        metadata_path = base / "persistence.meta.json"
        for path in (appendonly_path, snapshot_path, metadata_path):
            path.unlink(missing_ok=True)

        manager = build_command_manager(
            appendonly_path=appendonly_path,
            snapshot_path=snapshot_path,
            metadata_path=metadata_path,
            mongo_enabled=True,
            mongo_uri="mongodb://127.0.0.1:27017",
            mongo_db="mini_redis",
            mongo_collection="kv_store",
            mongo_client_factory=FakeMongoClient,
        )

        info = manager.execute({"name": "INFO", "args": ["MONGO"]})

        self.assertIn("# Mongo", info)
        self.assertIn("enabled:True", info)
        self.assertIn("connected:True", info)
        self.assertIn("database:mini_redis", info)
        self.assertIn("collection:kv_store", info)
        self.assertIn("operation_count:0", info)


if __name__ == "__main__":
    unittest.main()
