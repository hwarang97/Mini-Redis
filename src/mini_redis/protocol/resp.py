"""RESP-like serialization helpers."""

from __future__ import annotations

import json
from typing import Any

from mini_redis.config import ENCODING
from mini_redis.types import Command


class RespCodec:
    """Serialize commands and responses over the TCP boundary."""

    def encode_command(self, command: Command) -> bytes:
        return (json.dumps(command) + "\n").encode(ENCODING)

    def decode_command(self, payload: bytes) -> Command:
        data = json.loads(payload.decode(ENCODING))
        return {"name": str(data["name"]).upper(), "args": list(data.get("args", []))}

    def encode_response(self, value: Any) -> bytes:
        return (json.dumps({"result": value}) + "\n").encode(ENCODING)

    def decode_response(self, payload: bytes) -> Any:
        data = json.loads(payload.decode(ENCODING))
        return data["result"]

    def format_for_display(self, value: Any) -> str:
        if value is None:
            return "(nil)"
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)
