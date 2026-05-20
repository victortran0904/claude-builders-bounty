# Destructive Bash Guard

Claude Code `PreToolUse` hook that blocks destructive Bash commands before they run.

## Installation

```bash
git clone https://github.com/claude-builders-bounty/claude-builders-bounty.git
python3 claude-builders-bounty/hooks/pre-tool-use/install.py
```

The installer copies `destructive-bash-guard.py` to `~/.claude/hooks/` and adds a `PreToolUse` matcher for the `Bash` tool in `~/.claude/settings.json`.

## Blocked Commands

- Recursive forced removal, including `rm -rf`, `rm -fr`, and `rm --recursive --force`
- `git push --force`, `git push -f`, and `git push --force-with-lease`
- SQL run through common SQL clients that contains `DROP TABLE`, `TRUNCATE`, or `DELETE FROM` without a `WHERE` clause

Blocked attempts are appended as JSON lines to `~/.claude/hooks/blocked.log` with a UTC timestamp, attempted command, project path, matched pattern, and reason.

Safe commands produce no output and do not interfere with normal Bash execution.

## Hook Response

The hook uses Claude Code's structured `PreToolUse` response:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "..."
  }
}
```

This blocks only the dangerous Bash tool call and gives Claude a clear reason to choose a safer command.
