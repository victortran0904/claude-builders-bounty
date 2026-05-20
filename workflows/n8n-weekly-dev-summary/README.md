# n8n Weekly GitHub Dev Summary

Importable n8n workflow that gathers weekly GitHub activity, asks Claude
`claude-sonnet-4-20250514` for a narrative summary, and posts the result to a
Discord webhook.

## Setup

1. Import `weekly-dev-summary.json` into n8n.
2. Set environment variables: `GITHUB_REPO=owner/repo`, `GITHUB_TOKEN=...`, `ANTHROPIC_API_KEY=...`, `DESTINATION_WEBHOOK_URL=...`, `SUMMARY_LANGUAGE=EN` or `FR`.
3. Open the workflow and run `Manual Test Trigger` once to confirm repo/channel/language values and delivery.
4. Confirm the Discord message was delivered.
5. Activate the workflow; it runs every Friday at 5pm.

## What It Fetches

- Commits from the last seven days
- Closed issues updated since the weekly window began
- Merged pull requests from the weekly window

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `GITHUB_REPO` | yes | Repository in `owner/repo` form |
| `GITHUB_TOKEN` | yes | Token used for GitHub API requests |
| `ANTHROPIC_API_KEY` | yes | Claude API key |
| `DESTINATION_WEBHOOK_URL` | yes | Discord webhook URL |
| `SUMMARY_LANGUAGE` | no | `EN` or `FR`, defaults to `EN` |

Self-hosted n8n instances that block environment-variable reads in Code nodes
must allow env access for this workflow, for example with
`N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.

## Verification Note

The workflow JSON is valid, importable, and smoke-tested with n8n CLI against a
local mock GitHub API, mock Anthropic Messages API, and mock Discord webhook.
The same workflow uses the real GitHub, Anthropic, and Discord endpoints by
default when the optional test-only base URL variables are not set.

See `successful-execution.png` for the successful n8n execution proof. Full
live execution requires private GitHub, Anthropic, and Discord credentials,
which are intentionally not committed.
