"""AOF(Append Only File) 입출력 지원.

이 파일은 "명령 로그를 파일 끝에 계속 추가로 기록한다"는 AOF 방식만 전담한다.
상위 계층에서는 어떤 명령을 기록할지만 결정하고, 여기서는:

1. 파일에 한 줄씩 안전하게 append 하기
2. fsync 정책(always/everysec/no)에 맞춰 디스크 반영 강도 조절하기
3. 파일을 다시 읽어서 복구 가능한 엔트리 목록 만들기
4. 손상된 꼬리(tail)를 잘라내거나 현재 상태 기준으로 다시 쓰기

를 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class AOFReadResult:
    """AOF를 읽은 결과를 상위 계층으로 전달하기 위한 구조체.

    entries:
        정상적으로 파싱된 엔트리들만 담는다.
    corruption_detected:
        중간에 깨진 JSON이나 잘못된 구조를 만났는지 여부.
    ignored_entries:
        손상 지점 이후 복구에서 버려진 엔트리 수.
    corrupted_line:
        처음으로 손상이 감지된 줄 번호. 손상이 없으면 None.
    """
    entries: list[dict[str, Any]]
    corruption_detected: bool
    ignored_entries: int
    corrupted_line: int | None


class AOFWriter:
    """AOF 파일 자체를 다루는 저수준 객체.

    PersistenceManager는 "언제 기록할지"를 결정하고,
    AOFWriter는 "어떻게 파일에 기록하고 읽을지"를 담당한다.
    """

    def __init__(self, path: Path, fsync_policy: str = "everysec") -> None:
        self._path = path
        # AOF는 항상 같은 경로를 바라보므로, 생성 시점에 부모 디렉터리를 보장한다.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fsync_policy = fsync_policy
        # everysec 정책에서 "마지막으로 fsync한 시점"을 기억하기 위한 값이다.
        self._last_fsync_at = monotonic()

    def append(self, operation: str, args: list[object]) -> None:
        # AOF는 사람이 직접 읽기보다 기계가 다시 재생하는 로그이므로,
        # 명령 하나를 JSON 한 줄로 고정해 append 한다.
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"op": operation, "args": args}) + "\n")
            # write 이후 flush는 우선 파이썬 버퍼를 비우는 역할이다.
            handle.flush()
            # 이후 fsync 정책에 따라 실제 OS 버퍼까지 얼마나 강하게 밀어낼지 결정한다.
            # always:
            #   매 기록마다 디스크 반영을 강제한다. 가장 안전하지만 느리다.
            # everysec:
            #   대략 1초에 한 번 디스크 반영을 강제한다. 일반적인 절충안이다.
            # no:
            #   OS에 맡긴다. 가장 빠르지만 비정상 종료 시 유실 위험이 크다.
            if self._fsync_policy == "always":
                os.fsync(handle.fileno())
                self._last_fsync_at = monotonic()
            elif self._fsync_policy == "everysec" and monotonic() - self._last_fsync_at >= 1:
                os.fsync(handle.fileno())
                self._last_fsync_at = monotonic()

    def read_entries(self) -> AOFReadResult:
        # 파일이 없으면 "복구할 AOF가 없음"을 의미하므로 빈 결과를 돌려준다.
        if not self._path.exists():
            return AOFReadResult(
                entries=[],
                corruption_detected=False,
                ignored_entries=0,
                corrupted_line=None,
            )

        entries: list[dict[str, Any]] = []
        corruption_detected = False
        ignored_entries = 0
        corrupted_line: int | None = None
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    # 빈 줄은 무시한다. 복구를 깨뜨릴 정보가 아니기 때문이다.
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    # AOF는 앞부분이 정상이고 뒷부분만 깨지는 경우가 흔하다.
                    # 따라서 첫 손상 지점까지만 복구 대상으로 보고, 이후는 버린다.
                    corruption_detected = True
                    corrupted_line = line_number
                    ignored_entries += 1
                    ignored_entries += sum(1 for remaining in handle if remaining.strip())
                    break

                if not isinstance(payload, dict) or "op" not in payload:
                    # JSON이더라도 우리가 기대하는 AOF 엔트리 스키마가 아니면 손상으로 본다.
                    corruption_detected = True
                    corrupted_line = line_number
                    ignored_entries += 1
                    ignored_entries += sum(1 for remaining in handle if remaining.strip())
                    break

                # 정상 엔트리만 순서대로 누적한다. 복구는 이 순서를 그대로 재생한다.
                entries.append(payload)

        return AOFReadResult(
            entries=entries,
            corruption_detected=corruption_detected,
            ignored_entries=ignored_entries,
            corrupted_line=corrupted_line,
        )

    def rewrite(self, entries: list[dict[str, Any]]) -> Path:
        # rewrite는 기존 로그를 "현재 상태를 표현하는 최소 로그"로 덮어쓰는 작업이다.
        with self._path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")
        return self._path

    def repair(self) -> dict[str, Any]:
        # repair는 현재 파일을 읽어서 손상 여부를 판단한 뒤,
        # 손상된 tail이 있으면 정상 prefix만 남기고 잘라낸다.
        result = self.read_entries()
        if not self._path.exists():
            return {
                "path": str(self._path),
                "repaired": False,
                "corruption_detected": False,
                "ignored_entries": 0,
                "corrupted_line": None,
            }

        if result.corruption_detected:
            # 복구 전략은 "가능한 앞부분은 살리고, 뒤의 깨진 부분은 버린다"이다.
            self.rewrite(result.entries)

        return {
            "path": str(self._path),
            "repaired": result.corruption_detected,
            "corruption_detected": result.corruption_detected,
            "ignored_entries": result.ignored_entries,
            "corrupted_line": result.corrupted_line,
        }

    def set_fsync_policy(self, policy: str) -> None:
        # CONFIG SET 같은 상위 명령이 런타임에 정책을 바꿀 수 있게 한다.
        self._fsync_policy = policy

    @property
    def fsync_policy(self) -> str:
        return self._fsync_policy

    @property
    def path(self) -> Path:
        return self._path
