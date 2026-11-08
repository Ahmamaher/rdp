# One AI Cloud Runner

A small, public, zero-secret GitHub Actions runner for **safe, allow-listed maintenance jobs** that ChatGPT can trigger through the connected GitHub integration.

## What it does

- Runs only when the repository owner `Ahmamaher` opens an issue whose title starts with `[ONEAI-RUN]`.
- Accepts a strict JSON task body with exactly one field: `operation`.
- Supports three built-in operations: `health`, `self_test`, and `code_audit`.
- Posts a compact result as an issue comment.
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

Supported operations:

| Operation | Purpose |
|---|---|
| `health` | Report Python/runtime and runner environment information |
| `self_test` | Run the runner's standard-library unit tests |
| `code_audit` | Parse tracked Python source files and report syntax errors |

The workflow is on-demand. It is **not** a permanent server, does not run an LLM, and does not connect to a private One AI control endpoint.

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

ChatGPT can create a task issue through the connected GitHub integration, then read the result comment. One AI remains the local command center and persistent memory/database. This runner is a separate, stateless execution lane; it does not receive One AI's local database or credentials.
