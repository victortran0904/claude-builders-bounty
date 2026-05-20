#!/usr/bin/env python3
"""Claude Code PreToolUse hook that blocks destructive Bash commands."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


LOG_PATH = Path.home() / ".claude" / "hooks" / "blocked.log"
SEPARATORS = {";", "&&", "||", "|"}
WRAPPERS = {"sudo", "command", "builtin", "time", "noglob"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SQL_CLIENTS = {"psql", "mysql", "mariadb", "sqlite3", "sqlcmd", "duckdb", "cockroach"}


@dataclass(frozen=True)
class BlockDecision:
    pattern: str
    reason: str


def read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def shell_tokens(command: str) -> list[str]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return command.split()


def strip_shell_comments(command: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    in_comment = False
    at_word_start = True
    for char in command:
        if in_comment:
            if char in {"\n", "\r"}:
                result.append(char)
                in_comment = False
                at_word_start = True
            continue
        if escaped:
            result.append(char)
            at_word_start = False
            escaped = False
            continue
        if char == "\\" and quote != "'":
            result.append(char)
            escaped = True
            continue
        if char in {"'", '"'}:
            quote = None if quote == char else char if quote is None else quote
            result.append(char)
            at_word_start = False
            continue
        if char == "#" and quote is None and at_word_start:
            in_comment = True
            continue
        result.append(char)
        if quote is None:
            at_word_start = char.isspace() or char in {";", "&", "|", "(", ")"}
        else:
            at_word_start = False
    return "".join(result)


def strip_sql_comments_and_literals(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n\r]*", " ", sql)
    sql = re.sub(r"'(?:''|[^'])*'", "''", sql)
    sql = re.sub(r'"(?:""|[^"])*"', '""', sql)
    return sql


def command_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in SEPARATORS:
            if current:
                segments.append(current)
                current = []
            segments.append([token])
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def basename(token: str) -> str:
    return Path(token).name


def executable_index(segment: list[str]) -> int | None:
    index = 0
    while index < len(segment):
        token = segment[index]
        name = basename(token)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token):
            index += 1
            continue
        if name in WRAPPERS:
            index += 1
            continue
        if name == "env":
            index += 1
            while index < len(segment) and (
                segment[index].startswith("-")
                or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", segment[index])
            ):
                index += 1
            continue
        if name == "timeout":
            index += 1
            while index < len(segment) and segment[index].startswith("-"):
                index += 1
            if index < len(segment) and re.match(r"^\d+(\.\d+)?[smhd]?$", segment[index]):
                index += 1
            continue
        return index
    return None


def is_xargs_command_position(segment: list[str], index: int) -> bool:
    exec_index = executable_index(segment)
    if exec_index is None or basename(segment[exec_index]) != "xargs" or index <= exec_index:
        return False

    option_value_flags = {"-E", "-I", "-L", "-n", "-P", "-s"}
    command_index = exec_index + 1
    while command_index < len(segment):
        arg = segment[command_index]
        if arg == "--":
            command_index += 1
            break
        if not arg.startswith("-") or arg == "-":
            break
        if arg in option_value_flags and command_index + 1 < len(segment):
            command_index += 2
            continue
        command_index += 1
    return command_index == index


def is_execution_position(segment: list[str], index: int) -> bool:
    exec_index = executable_index(segment)
    if exec_index == index:
        return True
    if is_xargs_command_position(segment, index):
        return True
    return index > 0 and segment[index - 1] in {"-exec", "-execdir"}


def has_destructive_rm(tokens: list[str]) -> bool:
    for segment in command_segments(tokens):
        if segment in (["|"], [";"], ["&&"], ["||"]):
            continue
        for index, token in enumerate(segment):
            if basename(token) != "rm" or not is_execution_position(segment, index):
                continue
            has_force = False
            has_recursive = False
            for arg in segment[index + 1 :]:
                if arg == "--":
                    break
                if not arg.startswith("-"):
                    continue
                if arg in {"--force", "--interactive=never"}:
                    has_force = True
                elif arg in {"--recursive", "--dir"}:
                    has_recursive = True
                elif arg.startswith("-") and not arg.startswith("--"):
                    flags = arg.lstrip("-")
                    has_force = has_force or "f" in flags
                    has_recursive = has_recursive or "r" in flags or "R" in flags
            if has_force and has_recursive:
                return True
    return False


def has_forced_git_push(tokens: list[str]) -> bool:
    for segment in command_segments(tokens):
        if segment in (["|"], [";"], ["&&"], ["||"]):
            continue
        for index, token in enumerate(segment):
            if basename(token) != "git" or not is_execution_position(segment, index):
                continue
            rest = segment[index + 1 :]
            push_index = None
            skip_next = False
            for offset, arg in enumerate(rest):
                if skip_next:
                    skip_next = False
                    continue
                if arg in {"-C", "-c", "--git-dir", "--work-tree"}:
                    skip_next = True
                    continue
                if arg == "push":
                    push_index = offset
                    break
            if push_index is None:
                continue
            for arg in rest[push_index + 1 :]:
                if arg in {"-f", "--force", "--force-with-lease"}:
                    return True
                if arg.startswith("--force=") or arg.startswith("--force-with-lease="):
                    return True
                if arg.startswith("+") and len(arg) > 1:
                    return True
    return False


def is_sql_segment(segment: list[str]) -> bool:
    exec_index = executable_index(segment)
    return exec_index is not None and basename(segment[exec_index]) in SQL_CLIENTS


def extract_option_value(args: list[str], option_names: set[str]) -> list[str]:
    values: list[str] = []
    short_options = {option[1:] for option in option_names if re.fullmatch(r"-[A-Za-z]", option)}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in option_names and index + 1 < len(args):
            values.append(args[index + 1])
            index += 2
            continue
        for option_name in option_names:
            if arg.startswith(f"{option_name}="):
                values.append(arg.split("=", 1)[1])
        if arg.startswith("-") and not arg.startswith("--"):
            cluster = arg[1:]
            for short_option in short_options:
                position = cluster.find(short_option)
                if position == -1:
                    continue
                inline_value = cluster[position + 1 :]
                if inline_value:
                    values.append(inline_value)
                elif index + 1 < len(args):
                    values.append(args[index + 1])
                break
        index += 1
    return values


def piped_sql_text(segments: list[list[str]], sql_index: int) -> list[str]:
    if sql_index < 2 or segments[sql_index - 1] != ["|"]:
        return []
    producer = segments[sql_index - 2]
    exec_index = executable_index(producer)
    if exec_index is None:
        return []
    producer_name = basename(producer[exec_index])
    if producer_name in {"echo", "printf"}:
        return [arg for arg in producer[exec_index + 1 :] if not arg.startswith("-")]
    return []


def extract_sql_texts(tokens: list[str]) -> list[str]:
    segments = command_segments(tokens)
    sql_texts: list[str] = []
    for segment_index, segment in enumerate(segments):
        if segment in (["|"], [";"], ["&&"], ["||"]) or not is_sql_segment(segment):
            continue
        exec_index = executable_index(segment)
        if exec_index is None:
            continue
        client_name = basename(segment[exec_index])
        args = segment[exec_index + 1 :]
        if client_name in {"psql", "cockroach"}:
            sql_texts.extend(extract_option_value(args, {"-c", "--command"}))
        elif client_name in {"mysql", "mariadb"}:
            sql_texts.extend(extract_option_value(args, {"-e", "--execute"}))
        elif client_name == "sqlcmd":
            sql_texts.extend(extract_option_value(args, {"-Q", "-q"}))
        elif client_name in {"sqlite3", "duckdb"}:
            sql_texts.extend(arg for arg in args if re.search(r"\b(DROP|TRUNCATE|DELETE)\b", arg, re.IGNORECASE))
        sql_texts.extend(piped_sql_text(segments, segment_index))
    return sql_texts


def has_sql_drop_or_truncate(sql: str) -> BlockDecision | None:
    cleaned = strip_sql_comments_and_literals(sql)
    if re.search(r"\bDROP\s+TABLE\b", cleaned, flags=re.IGNORECASE):
        return BlockDecision("DROP TABLE", "DROP TABLE is blocked because it can destroy schema and data.")
    if re.search(r"\bTRUNCATE(?:\s+TABLE)?\b", cleaned, flags=re.IGNORECASE):
        return BlockDecision("TRUNCATE", "TRUNCATE is blocked because it can erase table contents.")
    return None


def has_delete_without_where(sql: str) -> bool:
    cleaned = strip_sql_comments_and_literals(sql)
    for statement in re.split(r";", cleaned):
        match = re.search(r"\bDELETE\s+FROM\b(?P<body>.*)$", statement, flags=re.IGNORECASE | re.DOTALL)
        if match and not re.search(r"\bWHERE\b", match.group("body"), flags=re.IGNORECASE):
            return True
    return False


def sql_decision(tokens: list[str]) -> BlockDecision | None:
    for sql_text in extract_sql_texts(tokens):
        decision = has_sql_drop_or_truncate(sql_text)
        if decision is not None:
            return decision
        if has_delete_without_where(sql_text):
            return BlockDecision(
                "DELETE FROM without WHERE",
                "DELETE FROM without a WHERE clause is blocked because it can delete every row.",
            )
    return None


def nested_shell_commands(tokens: list[str]) -> list[str]:
    commands: list[str] = []
    for segment in command_segments(tokens):
        if segment in (["|"], [";"], ["&&"], ["||"]):
            continue
        exec_index = executable_index(segment)
        if exec_index is None or basename(segment[exec_index]) not in SHELLS:
            continue
        args = segment[exec_index + 1 :]
        for index, arg in enumerate(args):
            if arg == "-c" and index + 1 < len(args):
                commands.append(args[index + 1])
                break
            if arg.startswith("-") and "c" in arg[1:] and index + 1 < len(args):
                commands.append(args[index + 1])
                break
    return commands


def evaluate(command: str) -> BlockDecision | None:
    command_without_comments = strip_shell_comments(command)
    tokens = shell_tokens(command_without_comments)
    if has_destructive_rm(tokens):
        return BlockDecision(
            "rm -rf",
            "Recursive forced deletion is blocked. Use a narrower remove command or ask for explicit approval.",
        )
    if has_forced_git_push(tokens):
        return BlockDecision(
            "git push --force",
            "Forced git pushes are blocked because they can overwrite remote history.",
        )
    decision = sql_decision(tokens)
    if decision is not None:
        return decision
    for nested_command in nested_shell_commands(tokens):
        decision = evaluate(nested_command)
        if decision is not None:
            return decision
    return None


def log_block(payload: dict, command: str, decision: BlockDecision) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "attempted_command": command,
        "project_path": payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "unknown",
        "pattern": decision.pattern,
        "reason": decision.reason,
    }
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True) + "\n")


def deny(decision: BlockDecision) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{decision.pattern}: {decision.reason}",
        }
    }
    print(json.dumps(output))


def main() -> int:
    payload = read_payload()
    if payload.get("hook_event_name") not in {None, "PreToolUse"}:
        return 0
    if payload.get("tool_name") not in {None, "Bash"}:
        return 0
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    command = tool_input.get("command") or payload.get("command") or ""
    if not isinstance(command, str) or not command.strip():
        return 0
    decision = evaluate(command)
    if decision is None:
        return 0
    try:
        log_block(payload, command, decision)
    except OSError:
        pass
    deny(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
