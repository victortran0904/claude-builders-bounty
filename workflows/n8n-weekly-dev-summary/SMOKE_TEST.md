# n8n Smoke Test

The workflow was imported into a real local n8n CLI instance and executed with
mock HTTP endpoints for GitHub, Anthropic, and Discord so no private credentials
were exposed.

```bash
n8n import:workflow --input=workflows/n8n-weekly-dev-summary/weekly-dev-summary.json

N8N_BLOCK_ENV_ACCESS_IN_NODE=false \
GITHUB_REPO=test/repo \
GITHUB_TOKEN='<mock>' \
ANTHROPIC_API_KEY='<mock>' \
ANTHROPIC_BASE_URL=http://127.0.0.1:7357 \
GITHUB_API_BASE_URL=http://127.0.0.1:7357 \
DESTINATION_WEBHOOK_URL=http://127.0.0.1:7357/discord \
SUMMARY_LANGUAGE=EN \
n8n execute --id=weekly-dev-summary-claude
```

Result:

```text
Execution was successful
status: success
finished: true
triggerNode: Manual Test Trigger
lastNodeExecuted: Send Discord Webhook
```

The smoke test exercised the full workflow path: config, commits, closed issues,
merged PRs, Claude prompt construction, Anthropic Messages API call, Discord
message formatting, and webhook delivery. Production use leaves
`ANTHROPIC_BASE_URL` and `GITHUB_API_BASE_URL` unset so the workflow calls the
real APIs.
