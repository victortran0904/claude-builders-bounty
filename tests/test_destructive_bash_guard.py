import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "hooks" / "pre-tool-use" / "destructive-bash-guard.py"
INSTALLER = REPO_ROOT / "hooks" / "pre-tool-use" / "install.py"


def load_hook_module():
    spec = importlib.util.spec_from_file_location("destructive_bash_guard", HOOK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_hook(home: Path, command: str, tool_name: str = "Bash", hook_event_name: str = "PreToolUse"):
    payload = {
        "session_id": "test-session",
        "transcript_path": str(home / "transcript.jsonl"),
        "cwd": str(home / "project"),
        "hook_event_name": hook_event_name,
        "tool_name": tool_name,
        "tool_input": {"command": command},
    }
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def run_hook_with_payload(home: Path, payload: dict):
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


class DestructiveBashGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def log_path(self) -> Path:
        return self.home / ".claude" / "hooks" / "blocked.log"

    def assert_allowed(self, command: str):
        result = run_hook(self.home, command)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertFalse(self.log_path().exists())

    def assert_denied(self, command: str, pattern: str):
        result = run_hook(self.home, command)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        output = json.loads(result.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "PreToolUse")
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn(pattern, hook_output["permissionDecisionReason"])

        log_record = json.loads(self.log_path().read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(log_record["attempted_command"], command)
        self.assertEqual(log_record["project_path"], str(self.home / "project"))
        self.assertEqual(log_record["pattern"], pattern)
        self.assertIn("timestamp", log_record)

    def test_allows_normal_bash_command(self):
        self.assert_allowed("git status --short")

    def test_blocks_recursive_forced_rm_forms(self):
        for command in [
            "rm -rf build",
            "rm -fr build",
            "sudo rm --recursive --force build",
            "find build -type f -exec rm -rf {} ;",
        ]:
            with self.subTest(command=command):
                self.assert_denied(command, "rm -rf")
                self.log_path().unlink()

    def test_blocks_nested_bash_login_command_rm_rf(self):
        self.assert_denied("bash -lc 'rm -rf /tmp/project'", "rm -rf")

    def test_blocks_rm_rf_around_compact_and_separator(self):
        for command in [
            "echo ok&&rm -rf build",
            "rm -rf build&&echo ok",
            "echo ok&rm -rf build",
        ]:
            with self.subTest(command=command):
                self.assert_denied(command, "rm -rf")
                self.log_path().unlink()

    def test_blocks_xargs_rm_rf_with_xargs_option(self):
        self.assert_denied("printf '%s\\0' target | xargs -0 rm -rf", "rm -rf")

    def test_does_not_block_text_that_mentions_rm_rf(self):
        self.assert_allowed("echo 'rm -rf build'")

    def test_ignores_shell_comments_that_mention_rm_rf(self):
        for command in [
            "# rm -rf /",
            "git status # rm -rf /",
            "echo safe # rm -rf /",
        ]:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_preserves_quoted_hash_characters(self):
        hook = load_hook_module()
        for command in [
            "echo '# rm -rf /'",
            'printf "%s\\n" "# git push --force origin main"',
        ]:
            with self.subTest(command=command):
                self.assertEqual(hook.strip_shell_comments(command), command)
                self.assert_allowed(command)

    def test_blocks_forced_git_push_forms(self):
        for command in [
            "git push --force origin main",
            "git -C repo push -f origin main",
            "sudo git push --force-with-lease origin main",
        ]:
            with self.subTest(command=command):
                self.assert_denied(command, "git push --force")
                self.log_path().unlink()

    def test_blocks_plus_refspec_forced_git_push(self):
        self.assert_denied("git push origin +main", "git push --force")

    def test_does_not_block_text_that_mentions_force_push(self):
        self.assert_allowed("printf '%s\\n' 'git push --force origin main'")

    def test_blocks_dangerous_sql_through_sql_clients(self):
        cases = [
            ("psql -c 'DROP TABLE users'", "DROP TABLE"),
            ("mysql -e 'TRUNCATE sessions'", "TRUNCATE"),
            ("sqlite3 app.db 'DELETE FROM accounts'", "DELETE FROM without WHERE"),
            ("echo 'DROP TABLE users' | psql", "DROP TABLE"),
        ]
        for command, pattern in cases:
            with self.subTest(command=command):
                self.assert_denied(command, pattern)
                self.log_path().unlink()

    def test_blocks_psql_compact_command_option_drop_table(self):
        self.assert_denied("psql -XAtc 'DROP TABLE users'", "DROP TABLE")

    def test_allows_sql_with_where_clause(self):
        self.assert_allowed("psql -c 'DELETE FROM accounts WHERE id = 1'")

    def test_sql_comments_do_not_hide_missing_where_clause(self):
        self.assert_denied("psql -c 'DELETE FROM accounts -- WHERE id = 1'", "DELETE FROM without WHERE")

    def test_does_not_block_plain_text_sql_examples(self):
        self.assert_allowed("echo 'DROP TABLE users'")

    def test_ignores_non_bash_tools(self):
        result = run_hook(self.home, "rm -rf build", tool_name="Read")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.log_path().exists())

    def test_ignores_other_hook_events(self):
        result = run_hook(self.home, "rm -rf build", hook_event_name="PostToolUse")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.log_path().exists())

    def test_accepts_camel_case_payload_keys(self):
        result = run_hook_with_payload(
            self.home,
            {
                "session_id": "test-session",
                "transcript_path": str(self.home / "transcript.jsonl"),
                "cwd": str(self.home / "project"),
                "hookEventName": "PreToolUse",
                "toolName": "Bash",
                "toolInput": {"command": "rm -rf build"},
            },
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        output = json.loads(result.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertTrue(self.log_path().exists())

    def test_installer_merges_bash_hook_without_overwriting_existing_settings(self):
        settings_path = self.home / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(
            json.dumps(
                {
                    "model": "sonnet",
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Read",
                                "hooks": [{"type": "command", "command": "echo read"}],
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["HOME"] = str(self.home)

        result = subprocess.run(
            [sys.executable, str(INSTALLER)],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        installed_hook = self.home / ".claude" / "hooks" / "destructive-bash-guard.py"
        self.assertTrue(installed_hook.exists())
        self.assertTrue(os.access(installed_hook, os.X_OK))

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(settings["model"], "sonnet")
        matchers = settings["hooks"]["PreToolUse"]
        self.assertTrue(any(matcher.get("matcher") == "Read" for matcher in matchers))
        bash_matchers = [matcher for matcher in matchers if matcher.get("matcher") == "Bash"]
        self.assertEqual(len(bash_matchers), 1)
        self.assertIn(str(installed_hook), bash_matchers[0]["hooks"][0]["command"])

    def test_installer_normalizes_unexpected_hook_settings_types(self):
        settings_path = self.home / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": {
                            "matcher": "Bash",
                            "hooks": {"type": "command", "command": "echo old"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["HOME"] = str(self.home)

        result = subprocess.run(
            [sys.executable, str(INSTALLER)],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        matchers = settings["hooks"]["PreToolUse"]
        self.assertIsInstance(matchers, list)
        bash_matchers = [matcher for matcher in matchers if matcher.get("matcher") == "Bash"]
        self.assertEqual(len(bash_matchers), 1)
        self.assertIn("destructive-bash-guard.py", bash_matchers[0]["hooks"][0]["command"])

    def test_logging_failure_does_not_prevent_denial(self):
        hook = load_hook_module()
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf build"},
            "cwd": str(self.home / "project"),
        }

        with (
            mock.patch("sys.stdin", io.StringIO(json.dumps(payload))),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            mock.patch.object(hook, "log_block", side_effect=OSError("disk full")),
        ):
            self.assertEqual(hook.main(), 0)

        output = json.loads(stdout.getvalue())
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "PreToolUse")
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("rm -rf", hook_output["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
