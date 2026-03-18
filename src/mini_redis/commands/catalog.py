"""Command help catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandHelpSpec:
    name: str
    usage: str
    summary: str


COMMAND_HELP_SPECS = (
    CommandHelpSpec("BGSAVE", "BGSAVE", "queue a background snapshot save"),
    CommandHelpSpec("BGREWRITEAOF", "BGREWRITEAOF", "queue a background AOF rewrite"),
    CommandHelpSpec("CONFIG", "CONFIG GET * | CONFIG SET <key> <value>", "read or update runtime config"),
    CommandHelpSpec("DELETE", "DELETE <key>", "remove a key"),
    CommandHelpSpec("DUMPALL", "DUMPALL", "show all live keys with values, ttl, and tags"),
    CommandHelpSpec("EXISTS", "EXISTS <key>", "check whether a key exists"),
    CommandHelpSpec("EXPIRE", "EXPIRE <key> <seconds>", "set a key expiration in seconds"),
    CommandHelpSpec("FLUSHDB", "FLUSHDB", "remove all keys from the database"),
    CommandHelpSpec("GET", "GET <key>", "read a single value"),
    CommandHelpSpec("HELP", "HELP [command]", "show supported commands or one command summary"),
    CommandHelpSpec("INFO", "INFO PERSISTENCE | INFO MONGO", "show runtime diagnostics"),
    CommandHelpSpec("INCR", "INCR <key>", "increment an integer value"),
    CommandHelpSpec("INVALIDATE", "INVALIDATE <tag>", "remove every key attached to a tag"),
    CommandHelpSpec("KEYS", "KEYS", "list all live keys"),
    CommandHelpSpec("LOAD", "LOAD", "restore state from the snapshot file"),
    CommandHelpSpec("MGET", "MGET <key> [key ...]", "read multiple values at once"),
    CommandHelpSpec("PING", "PING", "check server connectivity"),
    CommandHelpSpec("QUIT", "QUIT", "close the client session"),
    CommandHelpSpec("REPAIRAOF", "REPAIRAOF", "truncate a corrupted AOF tail"),
    CommandHelpSpec("REWRITEAOF", "REWRITEAOF", "rewrite the AOF from current live state"),
    CommandHelpSpec("SAVE", "SAVE", "write a snapshot immediately"),
    CommandHelpSpec(
        "SET",
        "SET <key> <value> [EX <seconds>] [TAGS <tag> ...]",
        "write a value with optional ttl and tags",
    ),
    CommandHelpSpec("TTL", "TTL <key>", "show remaining ttl for a key"),
)

COMMAND_HELP_INDEX = {spec.name: spec for spec in COMMAND_HELP_SPECS}


def list_help_lines() -> list[str]:
    return [_format_help_line(spec) for spec in COMMAND_HELP_SPECS]


def help_line_for(name: str) -> str | None:
    spec = COMMAND_HELP_INDEX.get(name.upper())
    if spec is None:
        return None
    return _format_help_line(spec)


def _format_help_line(spec: CommandHelpSpec) -> str:
    return f"{spec.usage} - {spec.summary}"
