# One AI Local–Cloud Bridge: Safe Integration Contract

Status: partial implementation. A pure snapshot provenance validator and adversarial unit tests now exist in this public repository. The local One AI importer has not yet been wired to independently fetch and validate GitHub resources, and no local-to-cloud task queue is connected. This document does not claim an end-to-end bridge.

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

A result should be correlated to the issue number, operation, and opaque correlation ID. The runner now includes the GitHub Actions workflow run URL, run ID, and run attempt in its result comment when those environment values are present. A future local validator must independently fetch the referenced run and confirm repository, workflow identity, issue event, conclusion, and run ID before accepting provenance. Preserve:
- runner identity and workflow run URL, run ID, and attempt;
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


## 9. Independent provenance verification contract

The local importer must not trust provenance fields copied from an issue comment. It must fetch the referenced GitHub resources independently, using a fixed repository allow-list and bounded HTTP timeouts.

For a candidate result associated with issue N and run R, verify all of the following before changing its state to `verified`:

1. **Issue identity:** fetch `GET /repos/Ahmamaher/rdp/issues/N`; require the exact repository, expected `[ONEAI-RUN]` title prefix, sender login `Ahmamaher`, and a valid version-1 task envelope.
2. **Comment identity:** fetch the issue comments; select the exact comment URL/ID; require author `github-actions[bot]`, and require its issue URL to point to issue N.
3. **Task correlation:** parse the issue body and result comment as data. Require exact equality for operation and correlation ID. Reject missing or duplicated conflicting metadata.
4. **Workflow run identity:** fetch `GET /repos/Ahmamaher/rdp/actions/runs/R`; require `id == R`, repository `Ahmamaher/rdp`, workflow path `.github/workflows/oneai-safe-runner.yml`, expected workflow ID, event `issues`, status `completed`, conclusion `success`, actor/triggering actor `Ahmamaher`, and `run_attempt` equal to the comment value.
5. **Run URL:** reconstruct the canonical URL from the fixed GitHub host, repository, and numeric run ID; compare it exactly with the comment URL. Do not fetch arbitrary hosts supplied by the comment.
6. **Temporal consistency:** parse all timestamps as timezone-aware UTC values. Require issue creation <= workflow run start <= comment creation <= workflow run completion, allowing only a small documented clock-skew tolerance. The runner posts its result comment from inside the job, before the workflow run can reach its terminal completed state. Require `requested_at` not to be after issue creation and not older than the configured dispatch freshness window. A stale request must be rejected or quarantined, not silently accepted.
7. **Workflow execution:** fetch the run's jobs endpoint and require the expected runner job to be completed successfully. Preserve job and step summaries as evidence; do not treat an arbitrary successful job as proof of the expected operation.
8. **Safe failure:** network errors, 403/rate limits, missing fields, malformed JSON, mismatches, or timeouts leave the record `pending_verification` or `unverified_external`. Never fall back to trusting the comment. Never retry in a tight loop.

Use a small explicit state machine: `unverified_external -> pending_verification -> verified`; any mismatch transitions to `rejected`. A temporary API/rate-limit failure is not a mismatch and must not transition to `rejected`. Keep the original raw evidence and a structured list of checks, but never persist credentials or response headers.

### Observed verification fixture (2026-11-09)

Issue #23, run #42552642615, and comment #6730995975 were fetched independently. The run record confirmed repository `Ahmamaher/rdp`, workflow path `.github/workflows/oneai-safe-runner.yml`, event `issues`, completed/success, actor `Ahmamaher`, and attempt 1. The jobs endpoint showed the expected `run-allowlisted-task` job and its test, syntax, and execution steps completed successfully. The issue body and comment agreed on operation `self_test` and correlation ID `task_provenance_20261109`.

**Important fixture failure:** the issue body recorded `requested_at=2026-11-09T04:18:00+02:00` (02:18:00Z), while the issue was created at 02:45:10Z. This is a 27-minute-old request at dispatch. The run itself succeeded, but the fixture must fail a strict 10-minute dispatch-freshness rule. Therefore this example proves the independent GitHub API lookup path and cross-resource correlation, not a fully passing production provenance validation. Keep it unverified until a fresh, correctly timestamped fixture passes the complete validator.


### Validator implementation and test coverage (2026-11-09)\n\nThe repository now contains `.github/provenance_validator.py`, a network-free validator for independently fetched issue, exact comment, workflow-run, and jobs snapshots. It checks the allow-listed repository, workflow identity, sender/trigger actor, operation allow-list, correlation ID, exact comment ID and canonical URL, run attempt, expected runner job, required successful runner steps, timeline ordering, and the 10-minute dispatch freshness window. `.github/test_provenance_validator.py` includes a positive fixture and rejection tests for stale requests, wrong repository/workflow, failed job/step, comment ID mismatch, correlation mismatch, noncanonical run URL, and comment timing. Both CI workflows run unittest discovery across `.github/test_*.py`; syntax checks include the validator and its tests.\n\nThis is a tested pure validation component, not a network client or local importer integration. The caller must independently fetch the issue, exact comment, run, and jobs from the fixed GitHub API endpoints, then pass the snapshots to the validator. Transient fetch failures must remain `pending_verification`, not `rejected`.\n\n### Positive freshness/provenance fixture (2026-11-09)

Issue #24 was created at 2026-11-09T03:33:48Z with a version-1 envelope containing operation `self_test`, correlation ID `freshprov_20261109`, and `requested_at=2026-11-09T05:33:00+02:00` (03:33:00Z). The referenced workflow run #42557086084 was independently fetched and confirmed: repository `Ahmamaher/rdp`, workflow path `.github/workflows/oneai-safe-runner.yml`, event `issues`, actor `Ahmamaher`, status `completed`, conclusion `success`, and attempt 1. Its job #128965130702 (`run-allowlisted-task`) completed successfully; the runner unit tests, syntax check, and fixed-operation execution steps all succeeded. The issue comment #6731589908 was independently fetched and authored by `github-actions[bot]`; its issue URL points to issue #24 and it contains the exact operation, correlation ID, canonical run URL, numeric run ID, and attempt. The timeline is consistent: request 03:33:00Z <= issue creation 03:33:48Z <= run start 03:33:51Z <= comment creation 03:33:56Z <= job completion 03:34:00Z <= workflow updated/completed at 03:34:01Z. This ordering reflects the actual architecture: the comment is emitted during the runner job, then the job and workflow finish. Request age at issue creation is 48 seconds, within the 10-minute freshness window. This is a clean positive fixture for identity, correlation, successful job, and freshness checks. It is still a documented test fixture, not evidence that the local One AI importer has implemented or passed this validator.
