#!/usr/bin/env python3
"""Install the destructive Bash guard for Claude Code."""

from __future__ import annotations

import json
import shlex
import shutil
import stat
from pathlib import Path


SOURCE_HOOK = Path(__file__).with_name("destructive-bash-guard.py")
CLAUDE_DIR = Path.home() / ".claude"
HOOKS_DIR = CLAUDE_DIR / "hooks"
TARGET_HOOK = HOOKS_DIR / "destructive-bash-guard.py"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    with SETTINGS_PATH.open(encoding="utf-8") as settings_file:
        data = json.load(settings_file)
    return data if isinstance(data, dict) else {}


def write_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as settings_file:
        json.dump(settings, settings_file, indent=2)
        settings_file.write("\n")


def install_hook() -> None:
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_HOOK, TARGET_HOOK)
    TARGET_HOOK.chmod(TARGET_HOOK.stat().st_mode | stat.S_IXUSR)


def merge_settings(settings: dict) -> dict:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks

    pre_tool_use = hooks.get("PreToolUse")
    if not isinstance(pre_tool_use, list):
        pre_tool_use = []
        hooks["PreToolUse"] = pre_tool_use

    command = shlex.quote(str(TARGET_HOOK))

    for matcher in pre_tool_use:
        if not isinstance(matcher, dict):
            continue
        if matcher.get("matcher") != "Bash":
            continue
        matcher_hooks = matcher.get("hooks")
        if not isinstance(matcher_hooks, list):
            matcher_hooks = []
            matcher["hooks"] = matcher_hooks
        if not any(
            isinstance(hook, dict)
            and hook.get("type") == "command"
            and hook.get("command") == command
            for hook in matcher_hooks
        ):
            matcher_hooks.append({"type": "command", "command": command})
        return settings

    pre_tool_use.append(
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": command}],
        }
    )
    return settings


def main() -> int:
    install_hook()
    settings = merge_settings(load_settings())
    write_settings(settings)
    print(f"Installed {TARGET_HOOK}")
    print(f"Updated {SETTINGS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
