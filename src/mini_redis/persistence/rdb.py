"""Snapshot(RDB 유사) 파일 지원.

이 프로젝트에서 snapshot은 "현재 메모리 상태를 한 번에 저장한 기준점" 역할을 한다.
AOF가 명령 히스토리라면, snapshot은 특정 시점의 완성 상태에 가깝다.
복구 시에는 snapshot을 먼저 로드하고, 그 이후 AOF tail만 재생해서 최종 상태를 맞춘다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RDBSnapshotStore:
    """Redis 엔진의 현재 상태를 snapshot 파일로 저장하고 다시 읽는다."""

    def __init__(self, path: Path) -> None:
        self._path = path
        # snapshot도 persistence 디렉터리 아래에서 고정 경로로 관리한다.
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, payload: dict[str, Any]) -> Path:
        # payload에는 storage, ttl, operation_log, aof_offset 등이 들어간다.
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return self._path

    def load(self) -> dict[str, Any] | None:
        # snapshot 파일이 아직 없으면 복구 가능한 snapshot이 없다는 의미다.
        if not self._path.exists():
            return None

        with self._path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
