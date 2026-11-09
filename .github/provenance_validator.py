"""Pure snapshot validator for One AI GitHub runner provenance.

Validates independently fetched API snapshots; it performs no network access.
The caller must fetch only from the fixed GitHub host/repository, use bounded
timeouts, and map temporary fetch failures to pending_verification.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re

EXPECTED_REPOSITORY = "Ahmamaher/rdp"
EXPECTED_WORKFLOW_PATH = ".github/workflows/oneai-safe-runner.yml"
EXPECTED_WORKFLOW_ID = 411544924
EXPECTED_ACTOR = "Ahmamaher"
EXPECTED_COMMENT_AUTHOR = "github-actions[bot]"
EXPECTED_JOB_NAME = "run-allowlisted-task"
ALLOWED_OPERATIONS = {"health", "self_test", "code_audit", "repo_integrity"}
CORRELATION_RE = re.compile(r"[A-Za-z0-9_-]{12,64}")
RUN_URL_RE = re.compile(r"https://github\.com/Ahmamaher/rdp/actions/runs/([0-9]+)\Z")


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"invalid_{field}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timezone_missing_{field}")
    return parsed.astimezone(timezone.utc)


def _one(pattern: str, body: str, field: str):
    matches = re.findall(pattern, body, flags=re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"missing_or_duplicate_{field}")
    return matches[0]


def validate_provenance(
    *, repository_full_name: str, issue: dict, comment: dict,
    run: dict, jobs: list, freshness_seconds: int = 600,
    clock_skew_seconds: int = 5,
) -> dict:
    """Return a verified/rejected result with individual checks."""
    checks: dict[str, bool] = {}
    reasons: list[str] = []

    def reject(reason: str, check: str) -> dict:
        checks[check] = False
        reasons.append(reason)
        return {"status": "rejected", "checks": checks, "reasons": reasons}

    try:
        if repository_full_name != EXPECTED_REPOSITORY:
            return reject("repository_not_allowlisted", "repository")
        checks["repository"] = True

        number = issue.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            return reject("invalid_issue_number", "issue_identity")
        if not isinstance(issue.get("title"), str) or not issue["title"].startswith("[ONEAI-RUN]"):
            return reject("invalid_issue_title", "issue_identity")
        if (issue.get("user") or {}).get("login") != EXPECTED_ACTOR:
            return reject("invalid_issue_author", "issue_identity")
        checks["issue_identity"] = True

        payload = json.loads(issue.get("body") or "")
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "correlation_id", "operation", "requested_at"
        }:
            return reject("invalid_task_envelope", "task_envelope")
        if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
            return reject("invalid_schema_version", "task_envelope")
        correlation_id = payload.get("correlation_id")
        operation = payload.get("operation")
        if not isinstance(correlation_id, str) or not CORRELATION_RE.fullmatch(correlation_id):
            return reject("invalid_correlation_id", "task_envelope")
        if not isinstance(operation, str) or operation not in ALLOWED_OPERATIONS:
            return reject("operation_not_allowlisted", "task_envelope")
        requested_at = _time(payload.get("requested_at"), "requested_at")
        issue_created = _time(issue.get("created_at"), "issue_created_at")
        checks["task_envelope"] = True

        comment_body = comment.get("body")
        if not isinstance(comment_body, str):
            return reject("invalid_comment_body", "comment_identity")
        if (comment.get("user") or {}).get("login") != EXPECTED_COMMENT_AUTHOR:
            return reject("invalid_comment_author", "comment_identity")
        expected_issue_url = f"https://api.github.com/repos/{EXPECTED_REPOSITORY}/issues/{number}"
        if comment.get("issue_url") != expected_issue_url:
            return reject("comment_issue_mismatch", "comment_identity")

        comment_operation = _one(r"^\*\*Operation:\*\* ([a-z_]+)$", comment_body, "operation")
        comment_correlation = _one(r"^\*\*Correlation ID:\*\* `([A-Za-z0-9_-]+)`$", comment_body, "correlation_id")
        comment_run_url = _one(r"^\*\*Workflow run:\*\* (https://[^\s]+)$", comment_body, "run_url")
        run_line = _one(r"^\*\*Run ID / attempt:\*\* `([0-9]+)` / `([0-9]+)`$", comment_body, "run_id_attempt")
        if comment_operation != operation or comment_correlation != correlation_id:
            return reject("task_comment_correlation_mismatch", "task_correlation")
        checks["comment_identity"] = True
        checks["task_correlation"] = True

        run_id_text, attempt_text = run_line
        run_id, attempt = int(run_id_text), int(attempt_text)
        url_match = RUN_URL_RE.fullmatch(comment_run_url)
        if not url_match or int(url_match.group(1)) != run_id:
            return reject("noncanonical_or_mismatched_run_url", "run_url")
        checks["run_url"] = True

        if run.get("id") != run_id:
            return reject("run_id_mismatch", "workflow_run")
        if (run.get("repository") or {}).get("full_name") != EXPECTED_REPOSITORY:
            return reject("run_repository_mismatch", "workflow_run")
        if run.get("path") != EXPECTED_WORKFLOW_PATH or run.get("workflow_id") != EXPECTED_WORKFLOW_ID:
            return reject("workflow_identity_mismatch", "workflow_run")
        if run.get("event") != "issues" or run.get("status") != "completed" or run.get("conclusion") != "success":
            return reject("workflow_not_successful", "workflow_run")
        if (run.get("actor") or {}).get("login") != EXPECTED_ACTOR:
            return reject("workflow_actor_mismatch", "workflow_run")
        if (run.get("triggering_actor") or {}).get("login") != EXPECTED_ACTOR:
            return reject("workflow_trigger_actor_mismatch", "workflow_run")
        if run.get("run_attempt") != attempt:
            return reject("run_attempt_mismatch", "workflow_run")
        checks["workflow_run"] = True

        matching_jobs = [
            job for job in jobs
            if job.get("name") == EXPECTED_JOB_NAME
            and job.get("status") == "completed"
            and job.get("conclusion") == "success"
        ]
        if len(matching_jobs) != 1:
            return reject("expected_runner_job_not_successful_or_ambiguous", "workflow_job")
        checks["workflow_job"] = True

        run_started = _time(run.get("run_started_at"), "run_started_at")
        run_completed = _time(run.get("updated_at"), "run_completed_at")
        comment_created = _time(comment.get("created_at"), "comment_created_at")
        tolerance = max(0, int(clock_skew_seconds))
        if issue_created.timestamp() > run_started.timestamp() + tolerance:
            return reject("issue_created_after_run_start", "timeline")
        if run_started.timestamp() > comment_created.timestamp() + tolerance:
            return reject("comment_precedes_run_start", "timeline")
        if comment_created.timestamp() > run_completed.timestamp() + tolerance:
            return reject("comment_after_run_completion", "timeline")
        if requested_at.timestamp() > issue_created.timestamp() + tolerance:
            return reject("request_time_after_issue_creation", "freshness")
        age = (issue_created - requested_at).total_seconds()
        if age < -tolerance or age > max(0, int(freshness_seconds)):
            return reject("request_outside_freshness_window", "freshness")
        checks["timeline"] = True
        checks["freshness"] = True
        return {"status": "verified", "checks": checks, "reasons": []}
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
        return reject("malformed_or_incomplete_snapshot", "snapshot_shape")
