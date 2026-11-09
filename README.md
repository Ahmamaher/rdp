# One AI Cloud Runner

A small, public, zero-secret GitHub Actions runner for **safe, allow-listed maintenance jobs** that ChatGPT can trigger through the connected GitHub integration.

## What it does

- Runs only when the repository owner `Ahmamaher` opens an issue whose title starts with `[ONEAI-RUN]`.
- Each issue is a one-shot task. Create a new issue for each run; reopening an old issue does not launch another job.
- Accepts either the legacy strict JSON body `{"operation":"health"}` or the exact version-1 envelope with `schema_version`, `correlation_id`, `operation`, and timezone-aware `requested_at`.
- Supports four fixed operations: `health`, `self_test`, `code_audit`, and `repo_integrity`.
- Posts a compact result as an issue comment, including the workflow run URL, run ID, and attempt when running in GitHub Actions.
- Uses Python's standard library only. No model API key, external service secret, Docker, or paid API is required.

## Trigger a task

Create an issue with title:

```text
[ONEAI-RUN] health
```

and body:

```json
{"operation":"health"}
```

New version-1 requests may instead use this exact envelope (the correlation ID is echoed in the result comment):

```json
{"schema_version":1,"correlation_id":"task_1234567890","operation":"health","requested_at":"2026-11-09T04:05:00Z"}
```

The correlation ID must be 12–64 letters, digits, underscores, or hyphens. `requested_at` must include a timezone and be no more than 10 minutes old when the issue is opened (5 seconds of clock-skew tolerance; future timestamps are rejected). Unknown keys are rejected. Legacy one-key requests remain supported for compatibility but do not carry freshness metadata.

Supported operations:

| Operation | Purpose |
|---|---|
| `health` | Report Python/runtime and runner environment information |
| `self_test` | Exercise authorization, legacy and version-1 JSON schemas, correlation ID and timezone validation, and operation allow-list checks |
| `code_audit` | Parse Python source files and report syntax errors |
| `repo_integrity` | Check for sensitive file names and high-confidence credential patterns without printing secret values |

The task workflow runs standard-library unit tests (including versioned-envelope validation) and a Python syntax check before each operation. Diagnostic findings in `code_audit` or `repo_integrity` are posted as comments and also make the workflow fail, so problems cannot be reported as a successful run. Source and integrity scans skip symbolic links to avoid following paths outside the checked-out repository. The issue-triggered worker is on-demand. It is **not** a permanent server, does not run an LLM, and does not connect to a private One AI control endpoint.

## Security boundaries

- This repository is public. **Never put private files, customer data, passwords, tokens, OAuth credentials, private URLs, or confidential prompts in an issue.**
- The job is gated at the workflow level and again in Python to the exact owner login `Ahmamaher`.
- Only fixed built-in operations are accepted. Issue text is never executed as a shell command or Python code.
- Workflow permissions are limited to repository contents read and issue comments write.
- The only token used is GitHub's short-lived, job-scoped `GITHUB_TOKEN`; no custom secrets are configured.
- The runner makes no deployment, publishing, messaging, purchasing, deletion, or account-permission changes.
- Results are public issue comments and contain diagnostic metadata only.

## Cost and availability

GitHub states that standard GitHub-hosted runner usage is free for public repositories. This runner is event-driven and stops when each job finishes. It is not guaranteed 24/7 compute and is not a replacement for a protected, persistent One AI server.

## ChatGPT + One AI usage

ChatGPT can create a task issue through the connected GitHub integration, then read the result comment. The task body must contain only a public, non-sensitive operation name. One AI remains the local command center and persistent memory/database. This runner is a separate, stateless execution lane; it does not receive One AI's local database or credentials, and it is not a direct automatic queue bridge. The correlation ID is a tracking field only; local dispatch, result validation, and database import are still separate integration work.
