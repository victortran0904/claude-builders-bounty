# Claude Review Agent

`claude-review` is a small CLI for turning a GitHub pull request diff into a
structured Markdown review comment. It is intentionally dependency-free so it can
run in local shells, CI jobs, and Claude Code sessions without package setup.

By default it produces an offline deterministic heuristic review. When
`ANTHROPIC_API_KEY` is set, it calls the Anthropic Messages API to ask Claude for
a richer review and falls back to the heuristic review if that call fails.

## Setup

```bash
chmod +x agents/claude-review/claude-review
export GITHUB_TOKEN="<optional GitHub token for private or rate-limited repos>"
```

To enable Claude-generated reviews, set an Anthropic key in your shell or CI
secret store:

```bash
export ANTHROPIC_API_KEY="<your Anthropic API key>"
export ANTHROPIC_MODEL="claude-sonnet-4-20250514" # optional
```

## Usage

```bash
agents/claude-review/claude-review --pr https://github.com/owner/repo/pull/123
agents/claude-review/claude-review --pr https://github.com/owner/repo/pull/123 --output review.md
agents/claude-review/claude-review --diff-file change.diff --no-anthropic
agents/claude-review/claude-review --pr https://github.com/owner/repo/pull/123 --model claude-sonnet-4-20250514
```

The output always includes:

- Summary of changes in 2-3 sentences
- Identified risks
- Improvement suggestions
- Confidence score: Low, Medium, or High

## GitHub Action

Copy `github-action/claude-review.yml` to `.github/workflows/claude-review.yml`.
The workflow runs on pull requests and uploads a Markdown review artifact.

## Sample Outputs

The `sample-outputs/` directory contains reviews generated from two real public
GitHub pull requests. They are included as acceptance evidence and as examples
of the Markdown format.
