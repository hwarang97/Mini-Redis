import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mini_redis.bootstrap import build_command_manager


class _CommandFlowFakeAdmin:
    def command(self, name: str) -> None:
        return None


class _CommandFlowFakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, str]] = {}

    def update_one(
        self,
        criteria: dict[str, str],
        payload: dict[str, dict[str, str]],
        upsert: bool = False,
    ) -> None:
        key = criteria["_id"]
        value = payload["$set"]["value"]
        if upsert or key in self.documents:
            self.documents[key] = {"_id": key, "value": value}

    def delete_one(self, criteria: dict[str, str]) -> None:
        self.documents.pop(criteria["_id"], None)

    def delete_many(self, criteria: dict[str, str]) -> None:
        self.documents.clear()


class _CommandFlowFakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, _CommandFlowFakeCollection] = {}

    def __getitem__(self, name: str) -> _CommandFlowFakeCollection:
        if name not in self.collections:
            self.collections[name] = _CommandFlowFakeCollection()
        return self.collections[name]


class _CommandFlowFakeMongoClient:
    def __init__(self, uri: str, serverSelectionTimeoutMS: int) -> None:
        self.uri = uri
        self.server_selection_timeout_ms = serverSelectionTimeoutMS
        self.admin = _CommandFlowFakeAdmin()
        self.databases: dict[str, _CommandFlowFakeDatabase] = {}

    def __getitem__(self, name: str) -> _CommandFlowFakeDatabase:
        if name not in self.databases:
            self.databases[name] = _CommandFlowFakeDatabase()
        return self.databases[name]


class CommandFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.appendonly_path = base / "appendonly.aof"
        self.snapshot_path = base / "dump.rdb.json"
        self.metadata_path = base / "persistence.meta.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build_manager(self):
        return build_command_manager(
            appendonly_path=self.appendonly_path,
            snapshot_path=self.snapshot_path,
            metadata_path=self.metadata_path,
        )

    def test_basic_command_flow(self) -> None:
        manager = self.build_manager()
        self.assertIsNotNone(manager.recovery_report)
        self.assertFalse(manager.recovery_report.snapshot_loaded)
        self.assertEqual(manager.recovery_report.replayed_entries, 0)
        self.assertFalse(manager.recovery_report.aof_corruption_detected)
        self.assertEqual(manager.recovery_report.ignored_aof_entries, 0)

        self.assertEqual(manager.execute({"name": "PING", "args": []}), "PONG")
        self.assertEqual(manager.execute({"name": "SET", "args": ["user:1", "hello"]}), "OK")
        self.assertEqual(manager.execute({"name": "EXISTS", "args": ["user:1"]}), 1)
        self.assertEqual(manager.execute({"name": "GET", "args": ["user:1"]}), "hello")
        self.assertEqual(manager.execute({"name": "DELETE", "args": ["user:1"]}), 1)
        self.assertEqual(manager.execute({"name": "EXISTS", "args": ["user:1"]}), 0)
        self.assertIsNone(manager.execute({"name": "GET", "args": ["user:1"]}))

    def test_ttl_commands(self) -> None:
        manager = self.build_manager()

        self.assertEqual(manager.execute({"name": "SET", "args": ["temp", "1"]}), "OK")
        self.assertEqual(manager.execute({"name": "EXPIRE", "args": ["temp", "1"]}), 1)
        ttl = manager.execute({"name": "TTL", "args": ["temp"]})
        self.assertIn(ttl, {0, 1})
        time.sleep(1.1)
        self.assertIsNone(manager.execute({"name": "GET", "args": ["temp"]}))
        self.assertEqual(manager.execute({"name": "TTL", "args": ["temp"]}), -2)

    def test_keys_returns_sorted_live_keys(self) -> None:
        manager = self.build_manager()

        manager.execute({"name": "SET", "args": ["b", "2"]})
        manager.execute({"name": "SET", "args": ["a", "1"]})

        self.assertEqual(manager.execute({"name": "KEYS", "args": []}), ["a", "b"])

    def test_help_lists_supported_commands(self) -> None:
        manager = self.build_manager()

        help_lines = manager.execute({"name": "HELP", "args": []})
        self.assertIn("HELP [command] - show supported commands or one command summary", help_lines)
        self.assertIn(
            "DUMPALL - show all live keys with values, ttl, and tags",
            help_lines,
        )

        self.assertEqual(
            manager.execute({"name": "HELP", "args": ["get"]}),
            "GET <key> - read a single value",
        )

    def test_dumpall_returns_live_values_ttl_and_tags(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["profile", "hello", "TAGS", "user:1", "demo"]})
        manager.execute({"name": "SET", "args": ["session", "live", "EX", "30", "TAGS", "user:1"]})

        lines = manager.execute({"name": "DUMPALL", "args": []})

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "key=profile value=hello ttl=persistent tags=demo,user:1")
        self.assertIn("key=session value=live ttl=", lines[1])
        self.assertTrue(lines[1].endswith("tags=user:1"))

    def test_incr_and_mget(self) -> None:
        manager = self.build_manager()

        self.assertEqual(manager.execute({"name": "INCR", "args": ["counter"]}), 1)
        self.assertEqual(manager.execute({"name": "INCR", "args": ["counter"]}), 2)
        manager.execute({"name": "SET", "args": ["x", "10"]})

        self.assertEqual(
            manager.execute({"name": "MGET", "args": ["counter", "x", "missing"]}),
            ["2", "10", None],
        )

    def test_invalidate_removes_all_keys_for_a_tag(self) -> None:
        manager = self.build_manager()

        manager.execute({"name": "SET", "args": ["user:1:profile", "profile", "TAGS", "user:1"]})
        manager.execute(
            {"name": "SET", "args": ["user:1:posts", "posts", "EX", "60", "TAGS", "user:1"]}
        )
        manager.execute({"name": "SET", "args": ["user:1:followers", "followers", "TAGS", "user:1"]})
        manager.execute({"name": "SET", "args": ["user:2:profile", "profile", "TAGS", "user:2"]})

        self.assertEqual(manager.execute({"name": "INVALIDATE", "args": ["user:1"]}), 3)
        self.assertIsNone(manager.execute({"name": "GET", "args": ["user:1:profile"]}))
        self.assertIsNone(manager.execute({"name": "GET", "args": ["user:1:posts"]}))
        self.assertIsNone(manager.execute({"name": "GET", "args": ["user:1:followers"]}))
        self.assertEqual(manager.execute({"name": "GET", "args": ["user:2:profile"]}), "profile")

    def test_expired_tagged_key_is_removed_from_invalidation_index(self) -> None:
        manager = self.build_manager()

        manager.execute({"name": "SET", "args": ["session:1", "ok", "EX", "1", "TAGS", "user:1"]})
        time.sleep(1.1)

        self.assertIsNone(manager.execute({"name": "GET", "args": ["session:1"]}))
        self.assertEqual(manager.execute({"name": "INVALIDATE", "args": ["user:1"]}), 0)

    def test_info_persistence_reports_runtime_state(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["alpha", "1"]})
        manager.execute({"name": "SAVE", "args": []})

        info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
        self.assertIn("# Persistence", info)
        self.assertIn("key_count:1", info)
        self.assertIn("snapshot_exists:True", info)
        self.assertIn("metadata_exists:True", info)
        self.assertIn("metadata.last_action:save", info)
        self.assertIn("metadata.schema_version:2", info)
        self.assertIn("recovery_policy:best-effort", info)
        self.assertIn("config.fsync_policy:everysec", info)

    def test_inspect_storage_reports_rehash_state_and_items(self) -> None:
        manager = self.build_manager()
        for index in range(4):
            manager.execute({"name": "SET", "args": [f"key:{index}", f"value:{index}"]})

        payload = manager.execute({"name": "INSPECT", "args": ["STORAGE", "FULL"]})

        self.assertIn("# Storage", payload)
        self.assertIn("is_rehashing:True", payload)
        self.assertIn("items.key:3:value:3", payload)

    def test_inspect_storage_reset_clears_recent_diagnostics(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["alpha", "1"]})

        self.assertEqual(manager.execute({"name": "INSPECT", "args": ["STORAGE", "RESET"]}), "OK")
        payload = manager.execute({"name": "INSPECT", "args": ["STORAGE"]})

        self.assertIn("# Storage", payload)
        self.assertIn("[table size:", payload)
        self.assertIn("[resizing:", payload)

    def test_inspect_storage_run_generates_synthetic_write_summary(self) -> None:
        manager = self.build_manager()

        payload = manager.execute({"name": "INSPECT", "args": ["STORAGE", "RUN", "5"]})

        self.assertIn("# Storage Insert Run", payload)
        self.assertIn("[request:", payload)
        self.assertIn("[table size:", payload)
        self.assertIn("[resizing:", payload)
        self.assertNotIn("recent_operations.", payload)

    def test_inspect_storage_update_runs_against_existing_probe_keys(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "INSPECT", "args": ["STORAGE", "RUN", "5"]})

        payload = manager.execute({"name": "INSPECT", "args": ["STORAGE", "UPDATE", "5"]})

        self.assertIn("# Storage Update Run", payload)
        self.assertIn("[request:", payload)
        self.assertIn("[table size:", payload)
        self.assertIn("[resizing:", payload)

    def test_benchmark_redis_reports_latency_summary(self) -> None:
        manager = self.build_manager()

        payload = manager.execute({"name": "BENCHMARK", "args": ["REDIS", "8", "KEEP"]})

        self.assertIn("# Benchmark", payload)
        self.assertIn("target:redis", payload)
        self.assertIn("storage.latency.max_us:", payload)
        self.assertIn("storage.is_rehashing:", payload)

    def test_probe_set_reports_request_latency_and_resize_state(self) -> None:
        manager = self.build_manager()

        payload = manager.execute({"name": "PROBE", "args": ["SET", "probe:key", "1"]})

        self.assertIn("[request:", payload)
        self.assertIn("[table size:", payload)
        self.assertIn("[resizing:", payload)
        self.assertIn("size=", payload)

    def test_probe_update_reports_request_latency_for_existing_key(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["probe:key", "1"]})

        payload = manager.execute({"name": "PROBE", "args": ["UPDATE", "probe:key", "2"]})

        self.assertIn("[request:", payload)
        self.assertIn("[table size:", payload)
        self.assertIn("[resizing:", payload)
        self.assertEqual(manager.execute({"name": "GET", "args": ["probe:key"]}), "2")

    def test_save_and_flushdb(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["persist:key", "value"]})

        snapshot_path = Path(manager.execute({"name": "SAVE", "args": []}))
        self.assertEqual(snapshot_path, self.snapshot_path)
        self.assertTrue(snapshot_path.exists())
        self.assertTrue(self.metadata_path.exists())
        self.assertEqual(manager.execute({"name": "FLUSHDB", "args": []}), 1)
        self.assertEqual(manager.execute({"name": "KEYS", "args": []}), [])
        self.assertTrue(self.appendonly_path.exists())

    def test_load_restores_snapshot_without_replaying_newer_aof_entries(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["persist:key", "value"]})
        manager.execute({"name": "SAVE", "args": []})
        manager.execute({"name": "SET", "args": ["persist:key", "new-value"]})

        self.assertEqual(manager.execute({"name": "LOAD", "args": []}), "OK")
        self.assertEqual(
            manager.execute({"name": "GET", "args": ["persist:key"]}),
            "value",
        )

    def test_restore_replays_only_aof_entries_after_snapshot(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["count", "5"]})
        manager.execute({"name": "SAVE", "args": []})
        manager.execute({"name": "INCR", "args": ["count"]})
        manager.execute({"name": "SET", "args": ["name", "mini-redis"]})

        restored = self.build_manager()
        self.assertTrue(restored.recovery_report.snapshot_loaded)
        self.assertEqual(restored.recovery_report.replayed_entries, 2)
        self.assertEqual(restored.execute({"name": "GET", "args": ["count"]}), "6")
        self.assertEqual(
            restored.execute({"name": "GET", "args": ["name"]}),
            "mini-redis",
        )

    def test_restore_replays_expire_after_snapshot(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["session", "ok"]})
        manager.execute({"name": "SAVE", "args": []})
        manager.execute({"name": "EXPIRE", "args": ["session", "1"]})

        restored = self.build_manager()
        ttl = restored.execute({"name": "TTL", "args": ["session"]})
        self.assertIn(ttl, {0, 1})

    def test_restore_keeps_tag_map_from_snapshot_and_aof_tail(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["user:1:profile", "profile", "TAGS", "user:1"]})
        manager.execute({"name": "SAVE", "args": []})
        manager.execute({"name": "SET", "args": ["user:1:posts", "posts", "TAGS", "user:1"]})

        restored = self.build_manager()
        self.assertEqual(restored.execute({"name": "INVALIDATE", "args": ["user:1"]}), 2)
        self.assertIsNone(restored.execute({"name": "GET", "args": ["user:1:profile"]}))
        self.assertIsNone(restored.execute({"name": "GET", "args": ["user:1:posts"]}))

    def test_restore_replays_invalidate_from_aof(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["user:1:profile", "profile", "TAGS", "user:1"]})
        manager.execute({"name": "INVALIDATE", "args": ["user:1"]})

        restored = self.build_manager()
        self.assertIsNone(restored.execute({"name": "GET", "args": ["user:1:profile"]}))

    def test_rewrite_aof_compacts_current_state(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["name", "redis"]})
        manager.execute({"name": "INCR", "args": ["counter"]})
        manager.execute({"name": "EXPIRE", "args": ["name", "30"]})

        rewritten_path = Path(manager.execute({"name": "REWRITEAOF", "args": []}))
        self.assertEqual(rewritten_path, self.appendonly_path)
        lines = rewritten_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(any('"op": "SET"' in line for line in lines))

    def test_restore_ignores_corrupted_aof_tail(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["safe", "value"]})
        self.appendonly_path.write_text(
            self.appendonly_path.read_text(encoding="utf-8") + '{"op": "SET", "args": ["broken"]\n',
            encoding="utf-8",
        )

        restored = self.build_manager()
        self.assertTrue(restored.recovery_report.aof_corruption_detected)
        self.assertEqual(restored.recovery_report.ignored_aof_entries, 1)
        self.assertIsNotNone(restored.recovery_report.corrupted_aof_line)
        self.assertEqual(restored.execute({"name": "GET", "args": ["safe"]}), "value")

    def test_repair_aof_truncates_corrupted_tail(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["safe", "value"]})
        original = self.appendonly_path.read_text(encoding="utf-8")
        self.appendonly_path.write_text(original + '{"bad": \n', encoding="utf-8")

        result = manager.execute({"name": "REPAIRAOF", "args": []})
        self.assertTrue(result["repaired"])
        self.assertTrue(result["corruption_detected"])
        self.assertEqual(result["ignored_entries"], 1)
        self.assertEqual(self.appendonly_path.read_text(encoding="utf-8"), original)
        info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
        self.assertIn("metadata.last_action:repair_aof", info)
        self.assertIn("metadata.last_repair.ignored_entries:1", info)

    def test_restore_persists_recovery_metadata_file(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["safe", "value"]})

        restored = self.build_manager()
        self.assertTrue(self.metadata_path.exists())
        info = restored.execute({"name": "INFO", "args": ["PERSISTENCE"]})
        self.assertIn("metadata.last_action:restore", info)

    def test_repair_aof_is_noop_for_clean_file(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["safe", "value"]})

        result = manager.execute({"name": "REPAIRAOF", "args": []})
        self.assertFalse(result["repaired"])
        self.assertFalse(result["corruption_detected"])

    def test_bgsave_completes_and_updates_metadata(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["safe", "value"]})
        result = manager.execute({"name": "BGSAVE", "args": []})
        self.assertTrue(result["queued"])

        for _ in range(20):
            info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
            if "background_tasks.bgsave.status:completed" in info:
                break
            time.sleep(0.05)

        info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
        self.assertIn("background_tasks.bgsave.status:completed", info)
        self.assertTrue(self.snapshot_path.exists())

    def test_bgrewriteaof_completes(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["safe", "value"]})
        result = manager.execute({"name": "BGREWRITEAOF", "args": []})
        self.assertTrue(result["queued"])

        for _ in range(20):
            info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
            if "background_tasks.bgrewriteaof.status:completed" in info:
                break
            time.sleep(0.05)

        info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
        self.assertIn("background_tasks.bgrewriteaof.status:completed", info)
        self.assertTrue(self.appendonly_path.exists())

    def test_config_get_and_set_updates_runtime_persistence_settings(self) -> None:
        manager = self.build_manager()
        self.assertEqual(
            manager.execute({"name": "CONFIG", "args": ["GET", "fsync_policy"]}),
            ["fsync_policy", "everysec"],
        )
        self.assertEqual(
            manager.execute({"name": "CONFIG", "args": ["SET", "fsync_policy", "always"]}),
            "OK",
        )
        self.assertEqual(
            manager.execute({"name": "CONFIG", "args": ["SET", "autorewrite_min_operations", "5"]}),
            "OK",
        )
        config = manager.execute({"name": "CONFIG", "args": ["GET", "*"]})
        self.assertIn("fsync_policy", config)
        self.assertIn("always", config)
        self.assertIn("autorewrite_min_operations", config)
        self.assertIn("5", config)

    def test_autorewrite_threshold_schedules_background_task(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "CONFIG", "args": ["SET", "autorewrite_min_operations", "1"]})
        manager.execute({"name": "SET", "args": ["safe", "value"]})

        for _ in range(20):
            info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
            if "background_tasks.bgrewriteaof.status:completed" in info:
                break
            time.sleep(0.05)

        info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
        self.assertIn("background_tasks.bgrewriteaof.status:completed", info)

    def test_autosave_interval_schedules_background_save(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "CONFIG", "args": ["SET", "autosave_interval", "1"]})
        time.sleep(1.1)
        manager.execute({"name": "SET", "args": ["safe", "value"]})

        for _ in range(20):
            info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
            if "background_tasks.bgsave.status:completed" in info:
                break
            time.sleep(0.05)

        info = manager.execute({"name": "INFO", "args": ["PERSISTENCE"]})
        self.assertIn("background_tasks.bgsave.status:completed", info)

    def test_aof_only_policy_ignores_snapshot(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["persist:key", "value"]})
        manager.execute({"name": "SAVE", "args": []})
        self.appendonly_path.unlink(missing_ok=True)

        restored = build_command_manager(
            appendonly_path=self.appendonly_path,
            snapshot_path=self.snapshot_path,
            metadata_path=self.metadata_path,
            recovery_policy="aof-only",
        )
        self.assertFalse(restored.recovery_report.snapshot_loaded)
        self.assertIsNone(restored.execute({"name": "GET", "args": ["persist:key"]}))

    def test_strict_policy_fails_on_corrupted_aof(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["safe", "value"]})
        self.appendonly_path.write_text(
            self.appendonly_path.read_text(encoding="utf-8") + '{"bad": \n',
            encoding="utf-8",
        )

        with self.assertRaises(ValueError):
            build_command_manager(
                appendonly_path=self.appendonly_path,
                snapshot_path=self.snapshot_path,
                metadata_path=self.metadata_path,
                recovery_policy="strict",
            )

    def test_keys_sweeps_expired_entries_before_listing(self) -> None:
        # This makes sure a full key listing purges expired entries before returning.
        manager = self.build_manager()

        manager.execute({"name": "SET", "args": ["live", "1"]})
        manager.execute({"name": "SET", "args": ["soon:gone", "1", "EX", "1"]})

        time.sleep(1.1)

        self.assertEqual(manager.execute({"name": "KEYS", "args": []}), ["live"])

    def test_set_reports_mongo_write_time_when_mongo_sync_is_enabled(self) -> None:
        manager = build_command_manager(
            appendonly_path=self.appendonly_path,
            snapshot_path=self.snapshot_path,
            metadata_path=self.metadata_path,
            mongo_enabled=True,
            mongo_uri="mongodb://127.0.0.1:27017",
            mongo_db="mini_redis",
            mongo_collection="kv_store",
            mongo_client_factory=lambda uri, serverSelectionTimeoutMS: _CommandFlowFakeMongoClient(
                uri,
                serverSelectionTimeoutMS,
            ),
        )

        result = manager.execute({"name": "SET", "args": ["user:1", "hello"]})

        self.assertTrue(str(result).startswith("OK mongo_write="))
        self.assertEqual(manager.execute({"name": "GET", "args": ["user:1"]}), "hello")


if __name__ == "__main__":
    unittest.main()
