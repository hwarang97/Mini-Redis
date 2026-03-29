"""Persistence 상위 조정 계층.

이 파일은 persistence 관련 기능을 실제로 "엮는" 중심 레이어다.
하위 모듈들이 각각:

- aof.py: AOF 파일 입출력
- rdb.py: snapshot 파일 입출력
- meta.py: 운영 메타데이터 파일 관리

를 맡고 있다면, 여기서는:

1. 부팅 시 어떤 순서로 복구할지 결정하고
2. snapshot + AOF를 함께 재생하고
3. metadata를 갱신하고
4. background save/rewrite 작업을 스케줄링하고
5. runtime config를 관리한다.

즉 persistence 기능의 "오케스트레이션"을 담당하는 파일이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from threading import Thread
from time import time
from typing import TYPE_CHECKING
from typing import Any

from mini_redis.persistence.aof import AOFReadResult
from mini_redis.persistence.aof import AOFWriter
from mini_redis.persistence.meta import PersistenceMetadataStore
from mini_redis.persistence.rdb import RDBSnapshotStore

if TYPE_CHECKING:
    from mini_redis.engine.redis import Redis


@dataclass(frozen=True)
class RecoveryReport:
    """부팅 복구 결과를 요약한 값 객체."""
    snapshot_loaded: bool
    replayed_entries: int
    recovered_keys: int
    aof_corruption_detected: bool
    ignored_aof_entries: int
    corrupted_aof_line: int | None


@dataclass(frozen=True)
class BackgroundTaskState:
    """백그라운드 persistence 작업의 현재 상태."""
    name: str
    status: str
    detail: str | None = None


class PersistenceManager:
    """AOF, snapshot, metadata, background task를 함께 조정한다."""

    def __init__(
        self,
        aof_writer: AOFWriter,
        snapshot_store: RDBSnapshotStore,
        metadata_store: PersistenceMetadataStore,
        recovery_policy: str,
    ) -> None:
        self._operation_log: list[tuple[object, ...]] = []
        self._aof_writer = aof_writer
        self._snapshot_store = snapshot_store
        self._metadata_store = metadata_store
        # metadata 파일이 있으면 이전 실행의 설정/시간 정보를 복원해서 이어간다.
        self._metadata = self._metadata_store.load()
        self._recovery_policy = recovery_policy
        self._task_lock = Lock()
        self._tasks: dict[str, BackgroundTaskState] = {}
        # 실제 save/rewrite 동작은 Redis 엔진이 갖고 있으므로,
        # 여기서는 콜백만 등록받아 백그라운드 스케줄링에 사용한다.
        self._save_hook: Any = None
        self._rewrite_hook: Any = None
        # autosave/autorewrite는 metadata에 남은 이전 설정을 기준으로 이어갈 수 있다.
        self._autosave_interval = int(self._metadata.get("autosave_interval", 0))
        self._autorewrite_min_operations = int(
            self._metadata.get("autorewrite_min_operations", 0)
        )
        self._last_save_at = float(self._metadata.get("last_save_at", time()))
        self._last_rewrite_at = float(self._metadata.get("last_rewrite_at", time()))
        self._last_rewrite_operation_length = int(
            self._metadata.get("last_rewrite_operation_length", 0)
        )
        self._aof_writer.set_fsync_policy(
            str(self._metadata.get("fsync_policy", self._aof_writer.fsync_policy))
        )
        self._last_recovery_report = RecoveryReport(
            snapshot_loaded=False,
            replayed_entries=0,
            recovered_keys=0,
            aof_corruption_detected=False,
            ignored_aof_entries=0,
            corrupted_aof_line=None,
        )

    def append(self, operation: str, *args: object) -> None:
        # operation_log는 snapshot 저장 시점과 AOF offset 계산에 사용된다.
        self._operation_log.append((operation, *args))
        self._aof_writer.append(operation, list(args))
        # 쓰기 이후에는 autosave/autorewrite 조건을 즉시 확인한다.
        self._maybe_schedule_tasks()

    def save_snapshot(self, payload: dict[str, Any]) -> Path:
        return self._snapshot_store.save(payload)

    def restore(self, redis: "Redis") -> RecoveryReport:
        # 복구를 시작할 때는 메모리 상태와 operation_log를 먼저 비운다.
        redis.reset_state()
        self._operation_log = []
        snapshot = self._snapshot_store.load()
        aof_result = self._aof_writer.read_entries()
        aof_offset = 0
        snapshot_loaded = False

        # recovery_policy에 따라 snapshot을 먼저 신뢰할지 결정한다.
        # best-effort / snapshot-first / strict 는 snapshot을 우선 반영한다.
        if self._recovery_policy in {"snapshot-first", "best-effort", "strict"} and snapshot is not None:
            redis.restore_snapshot(snapshot)
            self._operation_log = [
                tuple(entry) for entry in snapshot.get("operation_log", [])
            ]
            # snapshot에 저장된 aof_offset 이후의 tail만 replay 해야 중복 적용이 없다.
            aof_offset = int(snapshot.get("aof_offset", len(self._operation_log)))
            snapshot_loaded = True

        if self._recovery_policy == "aof-only":
            # aof-only는 snapshot을 무시하고 로그만으로 재구성한다.
            redis.reset_state()
            self._operation_log = []
            aof_offset = 0
            snapshot_loaded = False

        if self._recovery_policy == "strict" and aof_result.corruption_detected:
            # strict는 "조금이라도 손상되면 기동 실패" 정책이다.
            raise ValueError(
                f"AOF corruption detected at line {aof_result.corrupted_line}"
            )

        replayed_entries = 0
        # snapshot 이후의 AOF tail만 재생해서 최종 상태를 맞춘다.
        for entry in aof_result.entries[aof_offset:]:
            operation = str(entry["op"])
            args = list(entry.get("args", []))
            redis.replay_operation(operation, args)
            self._operation_log.append((operation, *args))
            replayed_entries += 1

        report = RecoveryReport(
            snapshot_loaded=snapshot_loaded,
            replayed_entries=replayed_entries,
            recovered_keys=redis.key_count(),
            aof_corruption_detected=aof_result.corruption_detected,
            ignored_aof_entries=aof_result.ignored_entries,
            corrupted_aof_line=aof_result.corrupted_line,
        )
        self._last_recovery_report = report
        self._write_metadata(
            last_action="restore",
            report=report,
        )
        return report

    def load_snapshot(self, redis: "Redis") -> bool:
        # LOAD 명령은 부팅 복구와 달리 "현재 메모리 상태를 snapshot으로 되돌린다"는 의미다.
        snapshot = self._snapshot_store.load()
        if snapshot is None:
            return False

        redis.reset_state()
        redis.restore_snapshot(snapshot)
        self._operation_log = [
            tuple(entry) for entry in snapshot.get("operation_log", [])
        ]
        self._write_metadata(last_action="load")
        return True

    def rewrite_aof(self, state_entries: list[dict[str, Any]]) -> Path:
        # rewrite 이후에는 기준점이 바뀌므로 마지막 rewrite 시각과 길이를 함께 저장한다.
        path = self._aof_writer.rewrite(state_entries)
        self._last_rewrite_at = time()
        self._last_rewrite_operation_length = len(self._operation_log)
        self._write_metadata(last_action="rewrite_aof")
        return path

    def repair_aof(self) -> dict[str, Any]:
        # repair는 파일을 잘라내는 작업이므로, 성공 후에는 손상 상태를 초기화해서 기록한다.
        result = self._aof_writer.repair()
        if result["repaired"]:
            self._last_recovery_report = RecoveryReport(
                snapshot_loaded=self._last_recovery_report.snapshot_loaded,
                replayed_entries=self._last_recovery_report.replayed_entries,
                recovered_keys=self._last_recovery_report.recovered_keys,
                aof_corruption_detected=False,
                ignored_aof_entries=0,
                corrupted_aof_line=None,
            )
        self._write_metadata(last_action="repair_aof", repair=result)
        return result

    def record_snapshot_save(self) -> None:
        # 실제 snapshot 파일 저장 직후 호출되어 metadata의 기준 시각을 갱신한다.
        self._last_save_at = time()
        self._write_metadata(last_action="save")

    def register_background_hooks(self, save_fn: Any, rewrite_fn: Any) -> None:
        # PersistenceManager는 "언제 돌릴지"만 알고,
        # Redis 엔진은 "무엇을 저장할지"를 안다. 그래서 콜백으로 연결한다.
        self._save_hook = save_fn
        self._rewrite_hook = rewrite_fn

    def get_config(self, key: str) -> dict[str, Any] | str:
        # CONFIG GET * 형태를 지원하기 위해 현재 유효한 설정 맵을 먼저 만든다.
        config = self._config_map()
        if key == "*":
            return config
        if key not in config:
            return "ERR unknown config key"
        return {key: config[key]}

    def set_config(self, key: str, value: str) -> str:
        # 런타임에서 변경 가능한 persistence 관련 설정만 이 경로로 허용한다.
        if key == "recovery_policy":
            if value not in {"best-effort", "snapshot-first", "aof-only", "strict"}:
                return "ERR invalid recovery policy"
            self._recovery_policy = value
        elif key == "fsync_policy":
            if value not in {"always", "everysec", "no"}:
                return "ERR invalid fsync policy"
            self._aof_writer.set_fsync_policy(value)
        elif key == "autosave_interval":
            interval = int(value)
            if interval < 0:
                return "ERR autosave_interval must be >= 0"
            self._autosave_interval = interval
        elif key == "autorewrite_min_operations":
            threshold = int(value)
            if threshold < 0:
                return "ERR autorewrite_min_operations must be >= 0"
            self._autorewrite_min_operations = threshold
        else:
            return "ERR unknown config key"

        self._write_metadata(last_action="config_set")
        return "OK"

    def start_background_save(self, save_fn: Any) -> dict[str, Any]:
        return self._start_task("bgsave", save_fn)

    def start_background_rewrite(self, rewrite_fn: Any) -> dict[str, Any]:
        return self._start_task("bgrewriteaof", rewrite_fn)

    def info(self) -> dict[str, Any]:
        # INFO PERSISTENCE는 파일 상태 + runtime config + 마지막 복구 결과를 한 번에 보여준다.
        aof_path = self._aof_writer._path
        snapshot_path = self._snapshot_store._path
        metadata_path = self._metadata_store.path
        return {
            "aof_path": str(aof_path),
            "aof_exists": aof_path.exists(),
            "aof_size": aof_path.stat().st_size if aof_path.exists() else 0,
            "snapshot_path": str(snapshot_path),
            "snapshot_exists": snapshot_path.exists(),
            "snapshot_size": snapshot_path.stat().st_size if snapshot_path.exists() else 0,
            "metadata_path": str(metadata_path),
            "metadata_exists": metadata_path.exists(),
            "operation_log_length": len(self._operation_log),
            "recovery_policy": self._recovery_policy,
            "background_tasks": {
                name: {"status": state.status, "detail": state.detail}
                for name, state in self._tasks.items()
            },
            "config": self._config_map(),
            "metadata": dict(self._metadata),
            "last_recovery": {
                "snapshot_loaded": self._last_recovery_report.snapshot_loaded,
                "replayed_entries": self._last_recovery_report.replayed_entries,
                "recovered_keys": self._last_recovery_report.recovered_keys,
                "aof_corruption_detected": self._last_recovery_report.aof_corruption_detected,
                "ignored_aof_entries": self._last_recovery_report.ignored_aof_entries,
                "corrupted_aof_line": self._last_recovery_report.corrupted_aof_line,
            },
        }

    @property
    def operation_log(self) -> list[tuple[object, ...]]:
        return list(self._operation_log)

    @property
    def last_recovery_report(self) -> RecoveryReport:
        return self._last_recovery_report

    def _write_metadata(
        self,
        *,
        last_action: str,
        report: RecoveryReport | None = None,
        repair: dict[str, Any] | None = None,
    ) -> None:
        active_report = report or self._last_recovery_report
        # 운영 중에 persistence가 어떤 상태였는지 재시작 후에도 볼 수 있게
        # 핵심 정보만 압축해서 metadata 파일로 남긴다.
        self._metadata = {
            "schema_version": 2,
            "last_action": last_action,
            "updated_at": int(time()),
            "recovery_policy": self._recovery_policy,
            "fsync_policy": self._aof_writer.fsync_policy,
            "autosave_interval": self._autosave_interval,
            "autorewrite_min_operations": self._autorewrite_min_operations,
            "last_save_at": self._last_save_at,
            "last_rewrite_at": self._last_rewrite_at,
            "last_rewrite_operation_length": self._last_rewrite_operation_length,
            "operation_log_length": len(self._operation_log),
            "snapshot_exists": self._snapshot_store._path.exists(),
            "aof_exists": self._aof_writer._path.exists(),
            "last_recovery": {
                "snapshot_loaded": active_report.snapshot_loaded,
                "replayed_entries": active_report.replayed_entries,
                "recovered_keys": active_report.recovered_keys,
                "aof_corruption_detected": active_report.aof_corruption_detected,
                "ignored_aof_entries": active_report.ignored_aof_entries,
                "corrupted_aof_line": active_report.corrupted_aof_line,
            },
        }
        if repair is not None:
            self._metadata["last_repair"] = dict(repair)
        self._metadata["background_tasks"] = {
            name: {"status": state.status, "detail": state.detail}
            for name, state in self._tasks.items()
        }
        self._metadata_store.save(self._metadata)

    def _start_task(self, name: str, fn: Any) -> dict[str, Any]:
        with self._task_lock:
            current = self._tasks.get(name)
            if current is not None and current.status == "running":
                # 같은 종류의 작업이 이미 돌고 있으면 중복 실행하지 않는다.
                return {"queued": False, "task": name, "status": "already-running"}
            self._tasks[name] = BackgroundTaskState(name=name, status="running")
            self._write_metadata(last_action=name)

        def runner() -> None:
            # 백그라운드 작업도 foreground 작업과 같은 metadata surface를 업데이트한다.
            try:
                detail = str(fn())
                state = BackgroundTaskState(name=name, status="completed", detail=detail)
            except Exception as exc:
                state = BackgroundTaskState(name=name, status="failed", detail=str(exc))
            with self._task_lock:
                self._tasks[name] = state
                self._write_metadata(last_action=name)

        Thread(target=runner, daemon=True).start()
        return {"queued": True, "task": name, "status": "running"}

    def _config_map(self) -> dict[str, Any]:
        return {
            "recovery_policy": self._recovery_policy,
            "fsync_policy": self._aof_writer.fsync_policy,
            "autosave_interval": self._autosave_interval,
            "autorewrite_min_operations": self._autorewrite_min_operations,
        }

    def _maybe_schedule_tasks(self) -> None:
        now = time()
        # autosave는 "마지막 저장 후 얼마나 지났는가"를 보고,
        # autorewrite는 "rewrite 이후 로그가 얼마나 더 쌓였는가"를 본다.
        if (
            self._autosave_interval > 0
            and self._save_hook is not None
            and now - self._last_save_at >= self._autosave_interval
        ):
            self._start_task("bgsave", self._save_hook)
        if (
            self._autorewrite_min_operations > 0
            and self._rewrite_hook is not None
            and len(self._operation_log) - self._last_rewrite_operation_length
            >= self._autorewrite_min_operations
        ):
            self._start_task("bgrewriteaof", self._rewrite_hook)
