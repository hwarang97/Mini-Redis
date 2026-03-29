"""Persistence 메타데이터 파일 지원.

snapshot이나 AOF 자체는 데이터 복구를 위한 파일이고,
이 파일은 "복구가 어떻게 일어났는지", "현재 설정이 무엇인지",
"마지막 repair/save/rewrite가 언제였는지" 같은 운영 메타정보를 위한 저장소다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PersistenceMetadataStore:
    """Persistence 운영 메타정보를 JSON 파일로 읽고 쓴다."""

    def __init__(self, path: Path) -> None:
        self._path = path
        # metadata 파일도 persistence 파일들과 같은 data 디렉터리 아래에서 관리한다.
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        # 파일이 없으면 첫 실행으로 간주하고 빈 설정으로 시작한다.
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, payload: dict[str, Any]) -> Path:
        # 이 파일은 운영 중 직접 열어볼 가능성이 높아서 사람이 읽기 좋은 JSON 형태를 유지한다.
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return self._path

    @property
    def path(self) -> Path:
        return self._path
