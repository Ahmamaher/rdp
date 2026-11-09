#!/usr/bin/env python3
"""Owner-gated, allow-listed GitHub issue task runner. Standard library only."""
from __future__ import annotations
import ast
from datetime import datetime
import json
import os
import pathlib
import platform
import re
import sys
import urllib.request

OWNER = "Ahmamaher"
REQUEST_MAX_AGE_SECONDS = 600
REQUEST_CLOCK_SKEW_SECONDS = 5
ALLOWED = {"health", "self_test", "code_audit", "repo_integrity"}
IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
SENSITIVE_NAMES = {".env", "mcp_bridge.token", "vault.key", "credentials.json", "id_rsa", "id_ed25519", "secrets.json"}
SENSITIVE_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".pem", ".p12", ".pfx", ".key"}


def is_sensitive_path(path: pathlib.Path) -> bool:
    name = path.name.lower()
    if name in {".env.example", ".env.sample", ".env.template"}:
        return False
    if name in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
        return True
    if name.startswith(".env.") or name in {"credentials", "secrets", "token", "mcp_bridge.token"}:
        return True
    return False
SECRET_PATTERNS = (
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("OpenAI-style API key", re.compile("s" + r"k-[A-Za-z0-9]{20,}")),
    ("Google OAuth token", re.compile(r"ya29\.[A-Za-z0-9_-]{20,}")),
    ("private-key marker", re.compile(re.escape("BEGIN " + "PRIVATE " + "KEY"))),
)


def parse_event(event: dict) -> tuple[int, str, str | None]:
    issue = event.get("issue") or {}
    sender = event.get("sender") or {}
    if sender.get("login") != OWNER:
        raise ValueError("Rejected: only the repository owner may trigger tasks.")
    if not str(issue.get("title", "")).startswith("[ONEAI-RUN]"):
        raise ValueError("Rejected: issue title must start with [ONEAI-RUN].")
    raw = issue.get("body") or ""
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Rejected: issue body must contain valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Rejected: task payload must be a JSON object.")
    if set(payload) == {"operation"}:
        correlation_id = None  # Backward compatibility for existing one-shot issues.
    elif set(payload) == {"schema_version", "correlation_id", "operation", "requested_at"}:
        if payload["schema_version"] != 1 or isinstance(payload["schema_version"], bool):
            raise ValueError("Rejected: unsupported task schema version.")
        correlation_id = payload["correlation_id"]
        if not isinstance(correlation_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{12,64}", correlation_id):
            raise ValueError("Rejected: invalid correlation_id.")
        requested_at = payload["requested_at"]
        if not isinstance(requested_at, str):
            raise ValueError("Rejected: requested_at must be an ISO-8601 timestamp.")
        try:
            parsed_time = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Rejected: requested_at must be an ISO-8601 timestamp.") from exc
        if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
            raise ValueError("Rejected: requested_at must include a timezone.")
        request_age = (datetime.now(parsed_time.tzinfo) - parsed_time).total_seconds()
        if request_age < -REQUEST_CLOCK_SKEW_SECONDS:
            raise ValueError("Rejected: requested_at is in the future.")
        if request_age > REQUEST_MAX_AGE_SECONDS:
            raise ValueError("Rejected: task request is stale.")
    else:
        raise ValueError('Body must use either {"operation":"..."} or the exact version-1 task envelope.')
    operation = payload["operation"]
    if not isinstance(operation, str) or operation not in ALLOWED:
        raise ValueError(f"Unsupported operation. Allowed: {', '.join(sorted(ALLOWED))}")
    number = issue.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("Missing or invalid issue number.")
    return number, operation, correlation_id


def health() -> str:
    return (
        "Health check passed.\n"
        f"- Python: {platform.python_version()}\n"
        f"- OS: {platform.system()} {platform.release()}\n"
        "- Dependencies: Python standard library only\n"
        "- Execution: completed; no persistent worker started"
    )


def self_test() -> str:
    valid = {"sender": {"login": OWNER}, "issue": {"number": 1, "title": "[ONEAI-RUN] test", "body": '{"operation":"health"}'}}
    if parse_event(valid) != (1, "health", None):
        raise AssertionError("Valid owner request was not accepted.")
    rejected = [
        {"sender": {"login": "untrusted"}, "issue": valid["issue"]},
        {"sender": {"login": OWNER}, "issue": {"number": 2, "title": "ordinary issue", "body": '{"operation":"health"}'}},
        {"sender": {"login": OWNER}, "issue": {"number": 3, "title": "[ONEAI-RUN]", "body": '{"operation":"arbitrary"}'}},
        {"sender": {"login": OWNER}, "issue": {"number": 4, "title": "[ONEAI-RUN]", "body": '{"operation":"health","extra":true}'}},
        {"sender": {"login": OWNER}, "issue": {"number": 5, "title": "[ONEAI-RUN]", "body": '{"operation":7}'}},
        {"sender": {"login": OWNER}, "issue": {"number": 0, "title": "[ONEAI-RUN]", "body": '{"operation":"health"}'}},
        {"sender": {"login": OWNER}, "issue": {"number": 6, "title": "[ONEAI-RUN]", "body": "not-json"}},
    ]
    for event in rejected:
        try:
            parse_event(event)
        except ValueError:
            continue
        raise AssertionError("A malformed, unauthorized, or unsupported request was accepted.")
    versioned = {
        "sender": {"login": OWNER},
        "issue": {
            "number": 8,
            "title": "[ONEAI-RUN] versioned self-test",
            "body": json.dumps({
                "schema_version": 1,
                "correlation_id": "selftest_123456789",
                "operation": "health",
                "requested_at": datetime.now().astimezone().isoformat(),
            }),
        },
    }
    if parse_event(versioned) != (8, "health", "selftest_123456789"):
        raise AssertionError("A valid versioned task envelope was not accepted.")
    invalid_versioned = [
        {**versioned, "issue": {**versioned["issue"], "body": json.dumps({
            "schema_version": 1, "correlation_id": "x", "operation": "health",
            "requested_at": datetime.now().astimezone().isoformat(),
        })}},
        {**versioned, "issue": {**versioned["issue"], "body": json.dumps({
            "schema_version": 1, "correlation_id": "selftest_123456789", "operation": "health",
            "requested_at": "2026-11-09T03:00:00",
        })}},
        {**versioned, "issue": {**versioned["issue"], "body": json.dumps({
            "schema_version": 1, "correlation_id": "selftest_123456789", "operation": "health",
            "requested_at": datetime.now().astimezone().isoformat(), "command": "whoami",
        })}},
    ]
    for event in invalid_versioned:
        try:
            parse_event(event)
        except ValueError:
            continue
        raise AssertionError("An invalid versioned task envelope was accepted.")
    return "Self-test passed: legacy and versioned schemas, correlation ID validation, timezone validation, unknown-key rejection, owner/title gates, operation allow-list, issue number, and malformed payload rejection."


def code_audit() -> str:
    root = pathlib.Path(".")
    files = [p for p in root.rglob("*.py") if not p.is_symlink() and not any(part in IGNORED_DIRS for part in p.parts)]
    errors = []
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    if errors:
        return "Python syntax audit FAILED:\n" + "\n".join(f"- {x}" for x in errors[:30])
    return f"Python syntax audit passed: {len(files)} Python files parsed successfully."


def repo_integrity() -> str:
    root = pathlib.Path(".")
    bad_paths = []
    secret_hits = []
    scanned = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):
            continue
        if is_sensitive_path(path):
            bad_paths.append(path.as_posix())
        try:
            if path.stat().st_size > 2_000_000:
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        scanned += 1
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(content):
                secret_hits.append((path.as_posix(), label))
    if bad_paths or secret_hits:
        lines = ["Potential repository hygiene issue detected; no secret values are shown."]
        lines.extend(f"- Sensitive-looking file path: {p}" for p in sorted(set(bad_paths))[:20])
        lines.extend(f"- Possible {label} pattern in: {p}" for p, label in sorted(set(secret_hits))[:20])
        return "\n".join(lines)
    return (
        "Repository integrity scan passed.\n"
        f"- Text files scanned: {scanned}\n"
        "- No known credential/database filenames detected\n"
        "- No high-confidence token/private-key patterns detected\n"
        "- Scan reports paths and pattern labels only; it never prints matching values"
    )


def operation_failed(operation: str, result: str) -> bool:
    """Return a failing process status when a diagnostic operation finds a problem."""
    if operation == "code_audit":
        return result.startswith("Python syntax audit FAILED:")
    if operation == "repo_integrity":
        return result.startswith("Potential repository hygiene issue detected")
    return False


def post_comment(issue_number: int, body: str) -> None:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    data = json.dumps({"body": body[:60000]}).encode()
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "oneai-safe-runner",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"GitHub comment API returned HTTP {response.status}")


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("Missing GitHub event payload.", file=sys.stderr)
        return 2
    try:
        event = json.loads(pathlib.Path(event_path).read_text(encoding="utf-8"))
        issue_number, operation, correlation_id = parse_event(event)
        handlers = {"health": health, "self_test": self_test, "code_audit": code_audit, "repo_integrity": repo_integrity}
        result = handlers[operation]()
        server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
        run_url = f"{server_url}/{repository}/actions/runs/{run_id}" if repository and run_id else ""
        body = (
            "## One AI Cloud Runner\n\n"
            f"**Operation:** {operation}\n"
            + (f"**Correlation ID:** `{correlation_id}`\n" if correlation_id else "")
            + (f"**Workflow run:** {run_url}\n" if run_url else "")
            + (f"**Run ID / attempt:** `{run_id}` / `{run_attempt}`\n" if run_id else "")
            + f"\n{result}\n\n"
            "_Bounded, stateless GitHub Actions job. It did not access private One AI files, "
            "credentials, or local services._"
        )
        post_comment(issue_number, body)
        print(body)
        return 1 if operation_failed(operation, result) else 0
    except Exception as exc:
        print(f"Runner failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
