"""Base helpers for command handlers."""

from __future__ import annotations

from mini_redis.engine.redis import Redis
from mini_redis.types import Command


class BaseHandler:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def handle(self, command: Command) -> object:
        raise NotImplementedError
