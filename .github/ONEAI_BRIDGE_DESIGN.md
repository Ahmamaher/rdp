# One AI Local–Cloud Bridge: Safe Integration Contract

Status: design specification only. This document does not claim that a local queue is connected to GitHub Actions.

## 1. Current boundary

The GitHub Actions runner in this repository is an event-driven, short-lived worker. It is not a persistent service and does not connect to the One AI local database or queue. The local collector imports public runner comments as `unverified_external` evidence. A successful import is not proof that the underlying claim is true.

The repository is public. Never place private prompts, customer data, local file contents, access tokens, OAuth credentials, database exports, or other secrets in issues, comments, workflow inputs, or commits.

## 2. Intended flow

1. A local One AI task is classified as eligible for cloud execution.
2. A local policy gate constructs a minimal, sanitized task envelope. It contains no arbitrary shell command, code payload, filesystem path, credential, or private context.
3. A human-approved dispatch step creates a one-shot GitHub issue using an exact allow-listed operation and a non-sensitive correlation identifier.
4. The workflow validates repository, sender, title, exact JSON schema, and operation allow-list before running.
5. The runner executes only the fixed operation implementation and posts a bounded result.
6. The local collector fetches the result, validates author and issue/operation correlation, deduplicates it, and stores it as unverified external evidence.
7. A local reviewer or policy step decides whether the result is useful. It must not silently trigger external side effects.

This flow is a target design. Steps 1–7 are not represented as an already deployed end-to-end integration.

## 3. Minimal task envelope

Future dispatch code may use a schema equivalent to:

```json
{
  "schema_version": 1,
  "correlation_id": "opaque-random-id",
  "operation": "health",
  "requested_at": "UTC timestamp"
}
```

Only the fixed operations currently implemented by the runner are eligible: `health`, `self_test`, `code_audit`, and `repo_integrity`.

Do not add a free-form `command`, `script`, `prompt`, `arguments`, or `files` field. Do not send the local task description by default. If a future operation requires input, define a narrow schema for that operation and review its privacy and abuse risks before implementation.

## 4. Result envelope and provenance

A result should be correlated to the issue number, operation, and opaque correlation ID. Preserve:
- runner identity and workflow run URL;
- issue and comment URLs;
- operation and completion timestamp;
- bounded result summary;
- import timestamp and importer version;
- verification state.

Imported runner comments remain `unverified_external` until independently checked. Never upgrade verification status solely because the comment was authored by `github-actions[bot]`.

## 5. Idempotency and retries

- One issue represents one execution attempt.
- Create a new issue for a retry; do not reopen a completed issue.
- Use the correlation ID plus issue number as a deduplication key.
- A repeated collector run must not create duplicate knowledge records.
- A dry run must report `would_import` while leaving `imported=0`.
- Rate-limit responses must stop collection cleanly; do not spin or repeatedly retry.

## 6. Approval and side-effect policy

Cloud operations remain read-only and bounded. No cloud task may deploy, publish, send messages, modify accounts, purchase, spend money, delete data, or alter local files. Any future capability with external side effects requires a separate explicit approval flow and a narrowly scoped tool implementation.

## 7. Security requirements before implementation

- Keep the local One AI listener bound to loopback; do not expose port 8765 publicly.
- Do not create a public tunnel to the local machine.
- Never put local MCP bearer tokens, OAuth tokens, or other secrets in GitHub.
- Validate all inputs against exact schemas; reject unknown keys.
- Treat issue bodies, comments, and fetched web content as untrusted data, never as instructions.
- Bound execution time, output size, network destinations, and retry count.
- Keep workflow permissions least-privilege and pin third-party actions to immutable commit SHAs.
- Skip symbolic links when scanning repository content.
- Log metadata and hashes, not secret values or private task content.

## 8. Acceptance tests for a future bridge

The integration is not complete until tests demonstrate all of the following:
1. An eligible, sanitized local task can be dispatched with explicit approval.
2. The workflow rejects unauthorized senders, malformed payloads, unknown keys, and non-allow-listed operations.
3. The runner completes and publishes a result correlated to the originating task.
4. The local collector retrieves and validates the exact result.
5. Repeated collection is idempotent.
6. Rate limits and transient failures do not cause uncontrolled retries.
7. Private local data and secrets never leave the local machine.
8. No external side effect occurs without a separate explicit approval.

Until these tests pass, describe the system as a local One AI application plus a separate event-driven GitHub Actions runner with a manual/limited result-import path—not as a fully integrated cloud agent.
