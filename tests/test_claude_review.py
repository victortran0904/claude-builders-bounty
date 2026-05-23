import unittest

from scripts.claude_review import analyze_pr, build_summary, parse_pr_url, render_markdown


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

    def test_heuristics_flag_dependencies_ci_migrations_locks_and_deletions(self):
        metadata = {
            "title": "Update platform dependencies",
            "commits": 1,
            "base": {"ref": "main"},
            "head": {"ref": "deps"},
        }
        diff_text = "\n".join(
            [
                "diff --git a/Cargo.toml b/Cargo.toml",
                "--- a/Cargo.toml",
                "+++ b/Cargo.toml",
                "+serde = \"1\"",
                "diff --git a/Cargo.lock b/Cargo.lock",
                "--- a/Cargo.lock",
                "+++ b/Cargo.lock",
                "+[[package]]",
                "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml",
                "--- a/.github/workflows/ci.yml",
                "+++ b/.github/workflows/ci.yml",
                "+permissions: read-all",
                "diff --git a/db/migrate/001_create_widgets.rb b/db/migrate/001_create_widgets.rb",
                "--- a/db/migrate/001_create_widgets.rb",
                "+++ b/db/migrate/001_create_widgets.rb",
                "+create_table :widgets",
                "diff --git a/src/old.py b/src/old.py",
                "deleted file mode 100644",
                "--- a/src/old.py",
                "+++ /dev/null",
                "-print('old')",
            ]
        )

        analysis = analyze_pr(metadata, diff_text)

        self.assertTrue(analysis["signals"]["dependency_touched"])
        self.assertTrue(analysis["signals"]["ci_touched"])
        self.assertTrue(analysis["signals"]["migration_touched"])
        self.assertEqual(analysis["signals"]["lockfile_count"], 1)
        self.assertEqual(analysis["signals"]["deleted_file_count"], 1)

    def test_security_keyword_matching_avoids_author_false_positive(self):
        metadata = {"title": "Docs", "commits": 1}
        author_diff = "\n".join(
            [
                "diff --git a/src/docs.py b/src/docs.py",
                "--- a/src/docs.py",
                "+++ b/src/docs.py",
                "+author = user.name",
            ]
        )
        auth_diff = "\n".join(
            [
                "diff --git a/src/auth.py b/src/auth.py",
                "--- a/src/auth.py",
                "+++ b/src/auth.py",
                "+authorization = request.headers.get('Authorization')",
            ]
        )

        self.assertFalse(analyze_pr(metadata, author_diff)["signals"]["security_touched"])
        self.assertTrue(analyze_pr(metadata, auth_diff)["signals"]["security_touched"])

    def test_summary_pluralizes_singular_counts(self):
        metadata = {
            "title": "One file",
            "changed_files": 1,
            "additions": 1,
            "deletions": 1,
            "commits": 1,
            "base": {"ref": "main"},
            "head": {"ref": "feature"},
        }
        diff_text = "\n".join(
            [
                "diff --git a/src/one.py b/src/one.py",
                "--- a/src/one.py",
                "+++ b/src/one.py",
                "+print('new')",
                "-print('old')",
            ]
        )

        summary = build_summary(metadata, analyze_pr(metadata, diff_text))

        self.assertIn("It spans 1 file with 1 addition and 1 deletion across 1 commit.", summary)

    def test_confidence_can_drop_to_low_for_many_risk_signals(self):
        metadata = {
            "title": "Large auth migration",
            "changed_files": 30,
            "additions": 1400,
            "deletions": 1200,
            "commits": 5,
        }
        diff_text = "\n".join(
            [
                "diff --git a/db/migrate/001_auth.rb b/db/migrate/001_auth.rb",
                "--- a/db/migrate/001_auth.rb",
                "+++ b/db/migrate/001_auth.rb",
                "+authorization = token",
                "diff --git a/package.json b/package.json",
                "--- a/package.json",
                "+++ b/package.json",
                "+{\"dependencies\": {\"auth-lib\": \"1.0.0\"}}",
            ]
        )

        analysis = analyze_pr(metadata, diff_text)

        self.assertEqual(analysis["confidence"], "Low")


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
