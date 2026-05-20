#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from urllib import parse, request
from urllib.error import HTTPError, URLError


USER_AGENT = "claude-review-agent/0.1"
SECURITY_KEYWORDS = (
    "auth",
    "token",
    "password",
    "secret",
    "permission",
    "oauth",
    "jwt",
    "crypto",
    "encrypt",
)
DEPENDENCY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "pdm.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "Gemfile",
    "Gemfile.lock",
    "composer.json",
    "composer.lock",
}
LOCKFILE_SUFFIXES = (".lock",)
MIGRATION_TOKENS = ("migrations", "alembic", "db/migrate")
CI_TOKENS = (".github/workflows", "circleci", ".gitlab-ci")


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int


def parse_pr_url(url: str) -> PullRequestRef:
    parsed = parse.urlparse(url)
    host = (parsed.netloc or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in {"github.com", "www.github.com"}:
        raise ValueError("URL must be a github.com pull request URL")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or parts[2] != "pull":
        raise ValueError("URL must match /owner/repo/pull/<number>")
    if not parts[3].isdigit():
        raise ValueError("Pull request number must be numeric")

    return PullRequestRef(owner=parts[0], repo=parts[1], number=int(parts[3]))


def _make_headers(token: str | None = None, accept: str = "application/vnd.github+json") -> Dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http_request(url: str, headers: Dict[str, str], method: str = "GET", body: bytes | None = None) -> str:
    req = request.Request(url, headers=headers, method=method, data=body)
    try:
        with request.urlopen(req, timeout=25) as resp:
            encoding = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(encoding, errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error reaching {url}: {exc}") from exc


def fetch_pr_metadata(pr: PullRequestRef, token: str | None = None) -> Dict[str, Any]:
    url = f"https://api.github.com/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}"
    payload = _http_request(url, _make_headers(token))
    return json.loads(payload)


def fetch_pr_diff(pr: PullRequestRef, token: str | None = None) -> str:
    url = f"https://github.com/{pr.owner}/{pr.repo}/pull/{pr.number}.diff"
    return _http_request(url, _make_headers(token, accept="text/x-diff"))


def extract_changed_files(diff_text: str) -> List[str]:
    files: List[str] = []
    seen = set()
    for line in diff_text.splitlines():
        if not line.startswith("diff --git "):
            continue
        match = re.match(r"^diff --git a/(.+?) b/(.+)$", line)
        if not match:
            continue
        left, right = match.groups()
        path = right if right != "/dev/null" else left
        if path not in seen:
            seen.add(path)
            files.append(path)
    return files


def diff_line_stats(diff_text: str) -> Tuple[int, int]:
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _has_test_files(files: List[str]) -> bool:
    for path in files:
        lower = path.lower()
        if re.search(r"(^|/)(test|tests)(/|_|\.|$)", lower) or lower.endswith("_test.py") or lower.endswith(".spec.js"):
            return True
    return False


def analyze_pr(metadata: Dict[str, Any], diff_text: str) -> Dict[str, Any]:
    files = extract_changed_files(diff_text)
    additions, deletions = diff_line_stats(diff_text)
    changed_files = int(metadata.get("changed_files") or len(files))
    additions = int(metadata.get("additions") or additions)
    deletions = int(metadata.get("deletions") or deletions)
    commits = int(metadata.get("commits") or 0)

    lower_diff = diff_text.lower()
    lower_files = [f.lower() for f in files]

    tests_present = _has_test_files(files)
    security_touched = any(keyword in lower_diff for keyword in SECURITY_KEYWORDS)
    ci_touched = any(any(token in path for token in CI_TOKENS) for path in lower_files)
    dependency_touched = any(os.path.basename(path) in DEPENDENCY_FILES for path in lower_files)
    migration_touched = any(any(token in path for token in MIGRATION_TOKENS) for path in lower_files)
    deleted_file_count = diff_text.count("deleted file mode")
    lockfile_count = sum(1 for path in lower_files if path.endswith(LOCKFILE_SUFFIXES) or os.path.basename(path) in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "cargo.lock"})

    total_changed_lines = additions + deletions

    risks: List[str] = []
    if changed_files >= 25 or total_changed_lines >= 1200:
        risks.append("Large PR footprint increases regression risk and reviewer blind spots.")
    if total_changed_lines >= 400:
        risks.append("Substantial code churn may hide edge-case failures.")
    if security_touched:
        risks.append("Security/auth-related code appears in the diff and needs focused review.")
    if migration_touched:
        risks.append("Database migration files changed; rollback and data-compatibility risk should be checked.")
    if dependency_touched:
        risks.append("Dependency manifest or lockfile changes may introduce supply-chain or compatibility risk.")
    if ci_touched:
        risks.append("CI/workflow definitions changed; verify pipeline behavior and permissions.")
    if deleted_file_count > 0:
        risks.append("File deletions detected; ensure removed logic has no runtime references.")
    if not tests_present and total_changed_lines >= 80:
        risks.append("No test files detected despite non-trivial changes.")
    if lockfile_count > 0 and lockfile_count == len(lower_files):
        risks.append("PR appears lockfile-only; verify this was intentionally generated from clean dependency updates.")

    if not risks:
        risks.append("No major red flags from heuristic scan; residual risk remains for runtime behavior and edge cases.")

    suggestions: List[str] = []
    if not tests_present:
        suggestions.append("Add or update automated tests that cover the main changed paths and one failure case.")
    if security_touched:
        suggestions.append("Request a focused security review for auth/secret/permission handling changes.")
    if migration_touched:
        suggestions.append("Document migration rollout and rollback steps, plus compatibility expectations.")
    if dependency_touched:
        suggestions.append("Pin and scan updated dependencies, and include rationale for major version bumps.")
    if ci_touched:
        suggestions.append("Run CI with least-privilege checks for updated workflow files before merge.")
    if changed_files >= 25 or total_changed_lines >= 1200:
        suggestions.append("Consider splitting this PR into smaller, reviewable units.")
    if not suggestions:
        suggestions.append("Run full CI and smoke tests before merge to validate runtime behavior.")

    strong_risk_signals = sum(
        [
            changed_files >= 25,
            total_changed_lines >= 1200,
            security_touched,
            migration_touched,
            ci_touched,
            dependency_touched,
            (not tests_present and total_changed_lines >= 80),
        ]
    )
    if strong_risk_signals >= 3 or total_changed_lines >= 2500:
        confidence = "Low"
    elif strong_risk_signals >= 1 or total_changed_lines >= 500 or changed_files >= 15:
        confidence = "Medium"
    else:
        confidence = "High"

    return {
        "files": files,
        "changed_files": changed_files,
        "additions": additions,
        "deletions": deletions,
        "commits": commits,
        "tests_present": tests_present,
        "risks": risks,
        "suggestions": suggestions,
        "confidence": confidence,
        "total_changed_lines": total_changed_lines,
    }


def build_summary(metadata: Dict[str, Any], analysis: Dict[str, Any]) -> str:
    title = (metadata.get("title") or "Untitled pull request").strip()
    base_ref = (metadata.get("base") or {}).get("ref") or "base"
    head_ref = (metadata.get("head") or {}).get("ref") or "head"
    touched_preview = ", ".join(analysis["files"][:3]) if analysis["files"] else "no parsed file names"
    tests_text = "includes test file changes" if analysis["tests_present"] else "does not include obvious test file changes"

    sentence1 = f"This PR, \"{title}\", proposes merging `{head_ref}` into `{base_ref}`."
    sentence2 = (
        f"It spans {analysis['changed_files']} files with {analysis['additions']} additions and "
        f"{analysis['deletions']} deletions across {analysis['commits']} commits."
    )
    sentence3 = f"Primary touched paths include {touched_preview}, and the diff {tests_text}."
    return " ".join([sentence1, sentence2, sentence3])


def render_markdown(pr: PullRequestRef, metadata: Dict[str, Any], analysis: Dict[str, Any]) -> str:
    summary = build_summary(metadata, analysis)

    risk_lines = "\n".join(f"- {item}" for item in analysis["risks"])
    suggestion_lines = "\n".join(f"- {item}" for item in analysis["suggestions"])

    return "\n".join(
        [
            f"# Claude Review for {pr.owner}/{pr.repo}#{pr.number}",
            "",
            "## Summary of changes",
            summary,
            "",
            "## Identified risks",
            risk_lines,
            "",
            "## Improvement suggestions",
            suggestion_lines,
            "",
            "## Confidence score",
            analysis["confidence"],
        ]
    ) + "\n"


def post_comment(pr: PullRequestRef, token: str, markdown: str) -> Dict[str, Any]:
    if not token:
        raise ValueError("GITHUB_TOKEN is required to post a comment")
    url = f"https://api.github.com/repos/{pr.owner}/{pr.repo}/issues/{pr.number}/comments"
    payload = json.dumps({"body": markdown}).encode("utf-8")
    headers = _make_headers(token)
    headers["Content-Type"] = "application/json"
    response = _http_request(url, headers=headers, method="POST", body=payload)
    return json.loads(response)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review a GitHub pull request and emit structured markdown.")
    parser.add_argument("--pr", required=True, help="GitHub pull request URL, e.g. https://github.com/owner/repo/pull/123")
    parser.add_argument(
        "--post-comment",
        action="store_true",
        help="Post the generated markdown as a PR comment (requires GITHUB_TOKEN).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    try:
        pr = parse_pr_url(args.pr)
    except ValueError as exc:
        print(f"Invalid --pr value: {exc}", file=sys.stderr)
        return 2

    token = os.getenv("GITHUB_TOKEN")

    try:
        metadata = fetch_pr_metadata(pr, token=token)
        diff_text = fetch_pr_diff(pr, token=token)
        analysis = analyze_pr(metadata, diff_text)
        markdown = render_markdown(pr, metadata, analysis)
    except Exception as exc:
        print(f"Failed to review PR: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(markdown)

    if args.post_comment:
        if not token:
            print("--post-comment requires GITHUB_TOKEN", file=sys.stderr)
            return 2
        try:
            response = post_comment(pr, token=token, markdown=markdown)
        except Exception as exc:
            print(f"Failed to post PR comment: {exc}", file=sys.stderr)
            return 1
        comment_url = response.get("html_url") or response.get("url") or "(unknown URL)"
        print(f"Posted comment: {comment_url}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
