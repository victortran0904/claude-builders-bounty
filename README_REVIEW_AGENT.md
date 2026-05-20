# Claude Review Agent (Issue #4)

This bounty implementation adds a small Python CLI that reviews a public GitHub PR and emits structured Markdown.

## Files

- `scripts/claude_review.py`: core logic (URL parsing, fetch, heuristics, markdown generation, optional post-comment)
- `./claude-review`: executable wrapper
- `tests/test_claude_review.py`: offline unit tests
- `samples/*.md`: generated sample outputs from real public PR URLs

## Requirements

- Python 3.9+
- Optional `GITHUB_TOKEN` env var for higher rate limits and for `--post-comment`

No third-party Python dependencies are required.

## Usage

Run review and print Markdown to stdout:

```bash
./claude-review --pr https://github.com/owner/repo/pull/123
```

Use a token (optional for public PR fetches, recommended for rate limits):

```bash
export GITHUB_TOKEN=ghp_xxx
./claude-review --pr https://github.com/owner/repo/pull/123
```

Post comment back to GitHub (explicit opt-in only):

```bash
./claude-review --pr https://github.com/owner/repo/pull/123 --post-comment
```

`--post-comment` is gated by both the flag and `GITHUB_TOKEN`.

## Heuristics

The reviewer uses lightweight heuristics from metadata + diff:

- PR size (files, additions, deletions)
- Tests present/absent
- Security/auth-related keywords
- CI/workflow file changes
- Dependency and lockfile changes
- Migration file changes
- File deletions

It outputs:

- Summary of changes (3 concise sentences)
- Identified risks (bullet list)
- Improvement suggestions (bullet list)
- Confidence score (`Low`, `Medium`, `High`)

## Tests

Run:

```bash
python3 -m unittest -v tests/test_claude_review.py
```

Tests are fully offline and cover:

- URL parsing validation
- Diff/risk heuristics
- Markdown section structure

## Notes

- Public PR fetches work without a token via GitHub public endpoints.
- Do not run `--post-comment` in local verification unless you intentionally want to publish a comment.
