import contextlib
import importlib.util
import importlib.machinery
import io
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "claude-review"


def load_module():
    loader = importlib.machinery.SourceFileLoader("claude_review", str(SCRIPT))
    spec = importlib.util.spec_from_loader("claude_review", loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ClaudeReviewTest(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_parse_pr_url(self):
        ref = self.mod.parse_pr_url("https://github.com/owner/repo/pull/123")
        self.assertEqual(ref.owner, "owner")
        self.assertEqual(ref.repo, "repo")
        self.assertEqual(ref.number, "123")

    def test_render_review_has_required_sections(self):
        diff = """diff --git a/app/auth.ts b/app/auth.ts
--- a/app/auth.ts
+++ b/app/auth.ts
@@ -1,2 +1,4 @@
+const token = "secret-token-value";
+eval(input);
 export const ok = true;
"""
        files = self.mod.parse_diff(diff)
        review = self.mod.render_review("https://github.com/owner/repo/pull/1", files)
        self.assertIn("### Summary", review)
        self.assertIn("### Identified Risks", review)
        self.assertIn("### Improvement Suggestions", review)
        self.assertIn("### Confidence Score:", review)
        self.assertIn("hard-coded secret", review)
        self.assertIn("dynamic code execution", review)

    def test_generate_anthropic_review_uses_messages_api(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "## Claude PR Review\n\n"
                                    "### Summary\n\nAPI review\n\n"
                                    "### Identified Risks\n\n- None\n\n"
                                    "### Improvement Suggestions\n\n- None\n\n"
                                    "### Confidence Score: High"
                                ),
                            }
                        ]
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        diff = "diff --git a/app.py b/app.py\n@@ -1 +1 @@\n+print('hello')\n"
        heuristic = "## Claude PR Review\n\n### Summary\n\nHeuristic"

        with mock.patch.object(self.mod.urllib.request, "urlopen", fake_urlopen):
            review = self.mod.generate_anthropic_review(
                "local diff",
                diff,
                heuristic,
                api_key="test-api-key",
                model="claude-test-model",
                base_url="https://anthropic.example",
                max_tokens=321,
                max_diff_chars=1000,
            )

        self.assertIn("API review", review)
        self.assertEqual(captured["timeout"], 60)
        request = captured["request"]
        headers = {key.lower(): value for key, value in request.header_items()}
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://anthropic.example/v1/messages")
        self.assertEqual(headers["x-api-key"], "test-api-key")
        self.assertEqual(headers["anthropic-version"], self.mod.ANTHROPIC_VERSION)
        self.assertEqual(body["model"], "claude-test-model")
        self.assertEqual(body["max_tokens"], 321)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertIn("Deterministic heuristic baseline", body["messages"][0]["content"])
        self.assertIn(diff, body["messages"][0]["content"])

    def test_main_without_anthropic_key_uses_offline_heuristic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            diff_path = Path(temp_dir) / "change.diff"
            diff_path.write_text("diff --git a/app.py b/app.py\n@@ -1 +1 @@\n+print('hello')\n", encoding="utf-8")

            def fail_urlopen(*args, **kwargs):
                raise AssertionError("network should not be used without ANTHROPIC_API_KEY")

            stdout = io.StringIO()
            with mock.patch.dict(self.mod.os.environ, {}, clear=True), mock.patch.object(
                self.mod.urllib.request, "urlopen", fail_urlopen
            ), contextlib.redirect_stdout(stdout):
                exit_code = self.mod.main(["--diff-file", str(diff_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("## Claude PR Review", stdout.getvalue())
        self.assertIn("No obvious high-risk patterns", stdout.getvalue())

    def test_main_falls_back_to_heuristic_when_anthropic_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            diff_path = Path(temp_dir) / "change.diff"
            diff_path.write_text("diff --git a/app.py b/app.py\n@@ -1 +1 @@\n+print('hello')\n", encoding="utf-8")

            def fail_urlopen(*args, **kwargs):
                raise self.mod.urllib.error.URLError("offline")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.dict(self.mod.os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True), mock.patch.object(
                self.mod.urllib.request, "urlopen", fail_urlopen
            ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = self.mod.main(["--diff-file", str(diff_path), "--model", "claude-test-model"])

        self.assertEqual(exit_code, 0)
        self.assertIn("## Claude PR Review", stdout.getvalue())
        self.assertIn("using heuristic fallback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
