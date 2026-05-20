import unittest

from scripts.claude_review import analyze_pr, parse_pr_url, render_markdown


class ParsePrUrlTests(unittest.TestCase):
    def test_valid_pr_url(self):
        ref = parse_pr_url("https://github.com/owner/repo/pull/123")
        self.assertEqual(ref.owner, "owner")
        self.assertEqual(ref.repo, "repo")
        self.assertEqual(ref.number, 123)

    def test_valid_pr_url_with_trailing_segments(self):
        ref = parse_pr_url("https://github.com/owner/repo/pull/42/files#diff-abc")
        self.assertEqual(ref.owner, "owner")
        self.assertEqual(ref.repo, "repo")
        self.assertEqual(ref.number, 42)

    def test_invalid_pr_urls(self):
        invalid_urls = [
            "https://gitlab.com/owner/repo/pull/1",
            "https://github.com/owner/repo/issues/1",
            "https://github.com/owner/repo/pull/not-a-number",
            "https://github.com/owner/repo",
        ]
        for url in invalid_urls:
            with self.assertRaises(ValueError):
                parse_pr_url(url)


class HeuristicTests(unittest.TestCase):
    def test_risk_heuristics_flag_security_and_missing_tests(self):
        metadata = {
            "title": "Harden auth middleware",
            "changed_files": 4,
            "additions": 180,
            "deletions": 40,
            "commits": 2,
            "base": {"ref": "main"},
            "head": {"ref": "feature/auth-hardening"},
        }
        diff_text = "\n".join(
            [
                "diff --git a/src/auth.py b/src/auth.py",
                "--- a/src/auth.py",
                "+++ b/src/auth.py",
                "+token = request.headers.get('Authorization')",
                "+if not token:",
                "+    raise ValueError('missing token')",
                "-legacy_auth = True",
                "diff --git a/src/permissions.py b/src/permissions.py",
                "--- a/src/permissions.py",
                "+++ b/src/permissions.py",
                "+SECRET_NAME = 'API_SECRET'",
                "+def check_permission(user):",
                "+    return user.is_admin",
            ]
        )

        analysis = analyze_pr(metadata, diff_text)
        risks_joined = " ".join(analysis["risks"])
        self.assertIn("Security/auth-related code", risks_joined)
        self.assertIn("No test files detected", risks_joined)
        self.assertIn(analysis["confidence"], {"Low", "Medium", "High"})


class MarkdownStructureTests(unittest.TestCase):
    def test_markdown_contains_required_sections(self):
        from scripts.claude_review import PullRequestRef

        pr = PullRequestRef(owner="owner", repo="repo", number=123)
        metadata = {
            "title": "Add feature",
            "changed_files": 2,
            "additions": 10,
            "deletions": 3,
            "commits": 1,
            "base": {"ref": "main"},
            "head": {"ref": "feature"},
        }
        diff_text = "\n".join(
            [
                "diff --git a/tests/test_feature.py b/tests/test_feature.py",
                "--- a/tests/test_feature.py",
                "+++ b/tests/test_feature.py",
                "+def test_feature():",
                "+    assert True",
            ]
        )
        analysis = analyze_pr(metadata, diff_text)
        markdown = render_markdown(pr, metadata, analysis)

        self.assertIn("## Summary of changes", markdown)
        self.assertIn("## Identified risks", markdown)
        self.assertIn("## Improvement suggestions", markdown)
        self.assertIn("## Confidence score", markdown)
        self.assertRegex(markdown, r"\n(Low|Medium|High)\n")


if __name__ == "__main__":
    unittest.main()
